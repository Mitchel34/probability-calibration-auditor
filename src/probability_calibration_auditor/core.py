"""Pure binary-probability audit and fixed synthetic evaluation.

Importing this module never runs the evaluation. evaluate() is a separately
admitted workload, not a demo or an ordinary test entry point.
"""
import math
import random

SEEDS = (7, 23, 101)
METHODS = ("oracle", "shrink", "expand", "reversed")
SCORES = ("brier", "log_loss", "gap", "ece")
EDGES = (0.0, 0.25, 0.5, 0.75, 1.0)


def audit(probabilities, outcomes):
    """Audit 1..10000 probabilities paired with integer binary outcomes.

    Reject wrong types, nonfinite values, and out-of-range probabilities.
    Inputs are not modified. Only log loss clips endpoint probabilities.
    """
    if (type(probabilities) is not list or type(outcomes) is not list
            or not 1 <= len(probabilities) <= 10000
            or len(probabilities) != len(outcomes)):
        raise ValueError("invalid input")
    bins = [
        {"lower": EDGES[b], "upper": EDGES[b + 1],
         "upper_inclusive": b == 3, "count": 0, "sum_p": 0.0, "sum_y": 0,
         "mean_p": None, "mean_y": None} for b in range(4)
    ]
    brier_sum = 0.0
    loss_sum = 0.0
    sum_p = 0.0
    sum_y = 0
    for raw_p, y in zip(probabilities, outcomes):
        if (type(raw_p) not in (int, float) or not 0 <= raw_p <= 1
                or type(y) is not int or y not in (0, 1)):
            raise ValueError("invalid input")
        p = float(raw_p)
        if not math.isfinite(p):
            raise ValueError("invalid input")
        residual = p - y
        brier_sum += residual * residual
        c = min(1.0 - 1e-12, max(1e-12, p))
        loss_sum += -(y * math.log(c) + (1 - y) * math.log(1.0 - c))
        sum_p += p
        sum_y += y
        b = 0 if p < 0.25 else 1 if p < 0.5 else 2 if p < 0.75 else 3
        row = bins[b]
        row["count"] += 1
        row["sum_p"] += p
        row["sum_y"] += y
    n = len(probabilities)
    ece = 0.0
    for row in bins:
        count = row["count"]
        if count:
            row["mean_p"] = row["sum_p"] / count
            row["mean_y"] = row["sum_y"] / count
            ece += (count / n) * abs(row["mean_p"] - row["mean_y"])
    return {"schema": "probability-audit/1", "n": n, "bins": bins,
            "scores": {"brier": brier_sum / n, "log_loss": loss_sum / n,
                       "gap": abs(sum_p / n - sum_y / n), "ece": ece}}


def metric_names():
    return ([f"s{s}_{m}_{k}" for s in SEEDS for m in METHODS for k in SCORES]
            + [f"{m}_b{b}_{k}" for m in METHODS for b in range(4)
               for k in ("count", "sum_p", "sum_y")]
            + ["outcome_count", "method_count", "first_pass_forecast_records",
               "total_processed_forecast_records"])


def check_names():
    return (["metric_schema_exact", "all_metrics_finite", "accounting_exact",
             "repeat_equal"]
            + [f"s{s}_{m}_integrity" for s in SEEDS for m in METHODS]
            + [f"{m}_pooled_integrity" for m in METHODS]
            + ["paired_labels_equal", "oracle_shrink_expand_reversed_definitions"])


def near(a, b):
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


def audit_integrity(result, probabilities, outcomes):
    n = len(probabilities)
    rows = result["bins"]
    if result["n"] != n or len(rows) != 4:
        return False
    if sum(row["count"] for row in rows) != n:
        return False
    if sum(row["sum_y"] for row in rows) != sum(outcomes):
        return False
    if not near(sum(row["sum_p"] for row in rows), sum(probabilities)):
        return False
    ece = 0.0
    for b, row in enumerate(rows):
        count, sp, sy = row["count"], row["sum_p"], row["sum_y"]
        if (type(count) is not int or type(sy) is not int
                or not 0 <= sy <= count or not 0 <= count <= n
                or not math.isfinite(sp)
                or sp < count * EDGES[b] - 1e-12
                or sp > count * EDGES[b + 1] + 1e-12):
            return False
        if row["lower"] != EDGES[b] or row["upper"] != EDGES[b + 1]:
            return False
        if row["upper_inclusive"] != (b == 3):
            return False
        if count:
            if not near(row["mean_p"], sp / count) or not near(row["mean_y"], sy / count):
                return False
            ece += (count / n) * abs(sp / count - sy / count)
        elif sp != 0.0 or sy != 0 or row["mean_p"] is not None or row["mean_y"] is not None:
            return False
    for key in SCORES:
        value = result["scores"][key]
        upper = 28.0 if key == "log_loss" else 1.0
        if type(value) is not float or not math.isfinite(value) or not -1e-12 <= value <= upper + 1e-12:
            return False
    return (near(result["scores"]["ece"], ece)
            and near(result["scores"]["gap"],
                     abs(sum(probabilities) / n - sum(outcomes) / n)))


def forecasts(q):
    return (q, 0.5 + 0.5 * (q - 0.5),
            min(0.99, max(0.01, 0.5 + 1.5 * (q - 0.5))), 1.0 - q)


def evaluation_pass():
    records = []
    metrics = {}
    pooled = {m: [[0, 0.0, 0] for b in range(4)] for m in METHODS}
    for seed in SEEDS:
        rng = random.Random(seed)
        labels = []
        latent = []
        vectors = [[] for m in METHODS]
        for i in range(10):
            q = (2 * i + 1) / 20.0
            for j in range(20):
                y = 1 if rng.random() < q else 0
                latent.append(q)
                labels.append(y)
                for values, p in zip(vectors, forecasts(q)):
                    values.append(p)
        for m, values in zip(METHODS, vectors):
            paired_labels = list(labels)
            result = audit(values, paired_labels)
            records.append((seed, m, latent, values, paired_labels, result))
            for key in SCORES:
                metrics[f"s{seed}_{m}_{key}"] = result["scores"][key]
            for b, row in enumerate(result["bins"]):
                pooled[m][b][0] += row["count"]
                pooled[m][b][1] += row["sum_p"]
                pooled[m][b][2] += row["sum_y"]
    for m in METHODS:
        for b in range(4):
            for key, value in zip(("count", "sum_p", "sum_y"), pooled[m][b]):
                metrics[f"{m}_b{b}_{key}"] = value
    metrics.update(outcome_count=600, method_count=4,
                   first_pass_forecast_records=2400, total_processed_forecast_records=4800)
    return records, metrics


def evaluate():
    """Run the full fixed two-pass workload only under evaluation admission."""
    first, metrics = evaluation_pass()
    repeat, repeat_metrics = evaluation_pass()
    checks = []
    checks.append({"name": "metric_schema_exact",
                   "passed": len(metrics) == 100 and set(metrics) == set(metric_names())})
    checks.append({"name": "all_metrics_finite",
                   "passed": all(type(v) in (int, float) and math.isfinite(v) for v in metrics.values())})
    checks.append({"name": "accounting_exact", "passed":
                   len(first) == len(repeat) == 12
                   and sum(len(r[4]) for r in first) == 2400
                   and sum(len(r[4]) for r in first + repeat) == 4800
                   and sum(len(first[i][4]) for i in (0, 4, 8)) == 600
                   and len(METHODS) == 4})
    checks.append({"name": "repeat_equal", "passed":
                   first == repeat and metrics == repeat_metrics})
    for seed, m, latent, values, labels, result in first:
        checks.append({"name": f"s{seed}_{m}_integrity",
                       "passed": len(values) == 200 and audit_integrity(result, values, labels)})
    for m in METHODS:
        selected = [r for r in first if r[1] == m]
        valid = sum(metrics[f"{m}_b{b}_count"] for b in range(4)) == 600
        for b in range(4):
            count = metrics[f"{m}_b{b}_count"]
            sp = metrics[f"{m}_b{b}_sum_p"]
            sy = metrics[f"{m}_b{b}_sum_y"]
            valid = valid and (type(count) is int and type(sy) is int and 0 <= sy <= count
                              and count * EDGES[b] - 1e-12 <= sp <= count * EDGES[b + 1] + 1e-12)
            for key in ("count", "sum_p", "sum_y"):
                valid = valid and metrics[f"{m}_b{b}_{key}"] == sum(r[5]["bins"][b][key] for r in selected)
            if count == 0:
                valid = valid and sp == 0 and sy == 0
        checks.append({"name": f"{m}_pooled_integrity", "passed": bool(valid)})
    paired = True
    transforms = True
    for records in (first, repeat):
        for start in (0, 4, 8):
            for row in records[start:start + 4]:
                paired = paired and row[4] == records[start][4]
        for seed, m, latent, values, labels, result in records:
            index = METHODS.index(m)
            for q, p in zip(latent, values):
                transforms = transforms and p == forecasts(q)[index] and 0 <= p <= 1
    checks.append({"name": "paired_labels_equal", "passed": bool(paired)})
    checks.append({"name": "oracle_shrink_expand_reversed_definitions", "passed": bool(transforms)})
    return {"checks": checks, "metrics": metrics}
