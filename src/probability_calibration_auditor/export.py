"""Export retained receipt measurements. Never imports the scoring module."""
import hashlib
import math
import re
import sys
from .jsonio import MAX_BYTES, loads, dump, diagnostic, quiet_close, write_output

SEEDS = (7, 23, 101)
METHODS = ("oracle", "shrink", "expand", "reversed")
SCORES = ("brier", "log_loss", "gap", "ece")
EDGES = (0.0, 0.25, 0.5, 0.75, 1.0)
ACCOUNTING = {"outcome_count": 600, "method_count": 4,
              "first_pass_forecast_records": 2400, "total_processed_forecast_records": 4800}
METRICS = ([f"s{s}_{m}_{k}" for s in SEEDS for m in METHODS for k in SCORES]
           + [f"{m}_b{b}_{k}" for m in METHODS for b in range(4)
              for k in ("count", "sum_p", "sum_y")] + list(ACCOUNTING))
CHECKS = (["metric_schema_exact", "all_metrics_finite", "accounting_exact", "repeat_equal"]
          + [f"s{s}_{m}_integrity" for s in SEEDS for m in METHODS]
          + [f"{m}_pooled_integrity" for m in METHODS]
          + ["paired_labels_equal", "oracle_shrink_expand_reversed_definitions"])


def require(condition):
    if not condition:
        raise ValueError("invalid input")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def export_receipt(raw, receipt_sha256, source_sha256, runner_sha256):
    """Validate supplied digest pins and export only an explicit public allowlist.

    Pins are supplied by the caller: this does not authenticate the caller,
    independently verify scientific checks, or prove registry closeout.
    """
    for pin in (receipt_sha256, source_sha256, runner_sha256):
        require(type(pin) is str and re.fullmatch("[0-9a-f]{64}", pin) is not None)
    require(type(raw) is bytes and len(raw) <= MAX_BYTES)
    require(hashlib.sha256(raw).hexdigest() == receipt_sha256)
    receipt = loads(raw, 16)
    require(type(receipt) is dict)
    constants = {
        "kind": "benchmark-receipt", "control_mode": "trusted-local-python-operational-v1",
        "outcome": "pass", "reason": "passed", "source_sha256": source_sha256,
        "runner_sha256": runner_sha256, "process_tree_stopped": True,
        "owned_child_reaped": True, "descendants_allowed": False,
        "compute_threads": 1, "monitor_threads": 0, "supervisor_threads": 1,
        "memory_hard_limit": False,
        "cpu_accounting": "at_least_full_reservation_and_observed_usage_no_refund",
        "measured_cpu_is_lower_bound_before_final_receipt_and_db": True,
    }
    for key, expected in constants.items():
        actual = receipt.get(key)
        require(type(actual) is type(expected) and actual == expected)
    for key in ("cpu_seconds", "measured_cpu_before_closeout_seconds",
                "peak_memory_bytes", "wall_seconds"):
        require(finite(receipt.get(key)) and receipt[key] >= 0)
    require(type(receipt["peak_memory_bytes"]) is int)
    require(receipt["cpu_seconds"] >= receipt["measured_cpu_before_closeout_seconds"])
    result = receipt.get("result")
    require(type(result) is dict and set(result) == {"metrics", "checks"})
    metrics, checks = result["metrics"], result["checks"]
    require(type(metrics) is dict and set(metrics) == set(METRICS))
    require(type(checks) is list and len(checks) == len(CHECKS))
    for record, name in zip(checks, CHECKS):
        require(type(record) is dict and set(record) == {"name", "passed"})
        require(record["name"] == name and record["passed"] is True)
    for key, value in metrics.items():
        integer = key in ACCOUNTING or key.endswith("_count") or key.endswith("_sum_y")
        require(type(value) is (int if integer else float) and math.isfinite(value))
    for key, expected in ACCOUNTING.items():
        require(metrics[key] == expected)
    for seed in SEEDS:
        for method in METHODS:
            for score in SCORES:
                upper = 28.0 if score == "log_loss" else 1.0
                require(-1e-12 <= metrics[f"s{seed}_{method}_{score}"] <= upper + 1e-12)

    summary = {}
    pooled = {}
    label_totals = []
    for method in METHODS:
        summary[method] = {}
        for score in SCORES:
            values = [metrics[f"s{s}_{method}_{score}"] for s in SEEDS]
            mean = sum(values) / 3
            sd = math.sqrt(sum((value - mean) ** 2 for value in values) / 2)
            require(math.isfinite(mean) and math.isfinite(sd))
            summary[method][score] = {"mean": mean, "sample_sd": sd}
        rows = []
        ece = 0.0
        for b in range(4):
            count = metrics[f"{method}_b{b}_count"]
            sp = metrics[f"{method}_b{b}_sum_p"]
            sy = metrics[f"{method}_b{b}_sum_y"]
            require(0 <= count <= 600 and 0 <= sy <= count)
            require(count * EDGES[b] - 1e-12 <= sp <= count * EDGES[b + 1] + 1e-12)
            if count == 0:
                require(sp == 0.0 and sy == 0)
            mp, my = (sp / count, sy / count) if count else (None, None)
            rows.append({"lower": EDGES[b], "upper": EDGES[b + 1],
                         "upper_inclusive": b == 3, "count": count, "sum_p": sp,
                         "sum_y": sy, "mean_p": mp, "mean_y": my})
            if count:
                ece += (count / 600) * abs(mp - my)
        require(sum(row["count"] for row in rows) == 600)
        label_totals.append(sum(row["sum_y"] for row in rows))
        pooled[method] = {"n": 600, "ece": ece, "bins": rows}
    require(len(set(label_totals)) == 1)
    return {
        "schema": "probability-evaluation/1", "metrics": dict(metrics),
        "checks": [dict(check) for check in checks],
        "derived": {"seed_summary": summary, "pooled_reliability": pooled},
        "resources": {
            "charged_cpu_seconds": receipt["cpu_seconds"],
            "measured_precloseout_cpu_seconds": receipt["measured_cpu_before_closeout_seconds"],
            "peak_memory_bytes": receipt["peak_memory_bytes"],
            "wall_seconds": receipt["wall_seconds"],
            "memory_scope": "sum_of_process_high_water_marks",
            "cpu_scope": "measured_before_final_closeout; charged_at_least_reservation",
            "memory_hard_limit": False,
        },
    }


def render_markdown(public):
    """Render a validated public export without loading a receipt or scoring."""
    lines = ["# Synthetic evaluation", "",
             "All measurements below are retained first-pass receipt values.",
             "Three fixed seeds are descriptive, not a real-world validity claim.", "",
             "| Seed | Transform | Brier | Log loss | Gap | ECE |",
             "| --- | --- | --- | --- | --- | --- |"]
    for seed in SEEDS:
        for method in METHODS:
            values = [repr(public["metrics"][f"s{seed}_{method}_{score}"]) for score in SCORES]
            lines.append("| " + " | ".join([str(seed), method] + values) + " |")
    lines += ["", "## Derived seed summaries", "",
              "Mean and sample standard deviation are derived from three retained seed scores.",
              "", "| Transform | Score | Mean | Sample SD |", "| --- | --- | --- | --- |"]
    for method in METHODS:
        for score in SCORES:
            row = public["derived"]["seed_summary"][method][score]
            lines.append(f"| {method} | {score} | {row['mean']!r} | {row['sample_sd']!r} |")
    lines += ["", "## Derived pooled reliability", "",
              "Only first-pass counts and sums are pooled. Pooled ECE is not generally mean seed ECE.",
              "", "| Transform | Bin | Count | Sum p | Sum y | Mean p | Mean y |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for method in METHODS:
        for b, row in enumerate(public["derived"]["pooled_reliability"][method]["bins"]):
            values = [str(row[key]) for key in ("count", "sum_p", "sum_y", "mean_p", "mean_y")]
            lines.append("| " + " | ".join([method, str(b)] + values) + " |")
    for method in METHODS:
        lines += ["", f"Derived {method} pooled ECE: "
                  f"{public['derived']['pooled_reliability'][method]['ece']!r}.", ""]
    lines += ["## Resource scope", "",
              "Measured CPU excludes final closeout; charged CPU is at least the reservation.",
              "Memory is a conservative sum of process high-water marks, not hard containment.", ""]
    for key, value in public["resources"].items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        require(len(argv) == 7)
        require(argv[1::2] == ["--receipt-sha256", "--source-sha256", "--runner-sha256"])
        with open(argv[0], "rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        value = export_receipt(raw, argv[2], argv[4], argv[6])
        write_output(dump(value))
        return 0
    except BrokenPipeError:
        quiet_close(sys.stdout)
        return 1
    except (ValueError, UnicodeError, TypeError, KeyError, RecursionError, OverflowError):
        return diagnostic("error: invalid input\n", 2)
    except OSError:
        return diagnostic("error: I/O failure\n", 1)


if __name__ == "__main__":
    raise SystemExit(main())
