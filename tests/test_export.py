"""Invented receipt fixtures only: these are not evaluation observations."""
import copy
import hashlib
import io
import json
import math
import sys
import unittest
from unittest.mock import patch
from probability_calibration_auditor import export
from probability_calibration_auditor.jsonio import dump


def fixture():
    # Hand-derived constant-p=0.5 case: 200 rows per seed, 100 positive
    # labels each. No rows are generated or scored here. Every method uses
    # this invented vector; these are exporter fixtures, not workload claims.
    metrics = {}
    for seed in export.SEEDS:
        for method in export.METHODS:
            for score in export.SCORES:
                metrics[f"s{seed}_{method}_{score}"] = {
                    "brier": .25, "log_loss": math.log(2), "gap": 0.0, "ece": 0.0
                }[score]
    for method in export.METHODS:
        for b in range(4):
            metrics[f"{method}_b{b}_count"] = 600 if b == 2 else 0
            metrics[f"{method}_b{b}_sum_p"] = 300.0 if b == 2 else 0.0
            metrics[f"{method}_b{b}_sum_y"] = 300 if b == 2 else 0
    metrics.update(export.ACCOUNTING)
    return {
        "kind": "benchmark-receipt", "control_mode": "trusted-local-python-operational-v1",
        "outcome": "pass", "reason": "passed", "source_sha256": "a"*64, "runner_sha256": "b"*64,
        "process_tree_stopped": True, "owned_child_reaped": True, "descendants_allowed": False,
        "compute_threads": 1, "monitor_threads": 0, "supervisor_threads": 1,
        "memory_hard_limit": False,
        "cpu_accounting": "at_least_full_reservation_and_observed_usage_no_refund",
        "measured_cpu_is_lower_bound_before_final_receipt_and_db": True,
        "cpu_seconds": 60.0, "measured_cpu_before_closeout_seconds": .1,
        "peak_memory_bytes": 1000000, "wall_seconds": .2,
        "private_extra": "INVENTED_PRIVATE_SENTINEL",
        "result": {"metrics": metrics, "checks": [{"name": n, "passed": True} for n in export.CHECKS]},
    }


def run_fixture(value):
    raw = dump(value).encode()
    return export.export_receipt(raw, hashlib.sha256(raw).hexdigest(), "a"*64, "b"*64)


class ExportTests(unittest.TestCase):
    def test_export_stdout_flush_and_diagnostic_failures(self):
        raw = dump(fixture()).encode()
        args = ["invented.json", "--receipt-sha256", hashlib.sha256(raw).hexdigest(),
                "--source-sha256", "a"*64, "--runner-sha256", "b"*64]
        for operation in ("write", "flush"):
            for failure in (BrokenPipeError, OSError):
                with self.subTest(operation=operation, failure=failure), \
                        patch("builtins.open", return_value=io.BytesIO(raw)), \
                        patch("sys.stdout") as out, patch("sys.stderr"):
                    getattr(out, operation).side_effect = failure("invented output failure")
                    out.close.side_effect = failure("invented close failure")
                    self.assertEqual(export.main(args), 1)
                    out.close.assert_called()
                with patch("sys.stderr") as err:
                    getattr(err, operation).side_effect = failure("invented diagnostic failure")
                    err.close.side_effect = failure("invented close failure")
                    self.assertEqual(export.main([]), 1)
                    err.close.assert_called_once()
                    self.assertEqual(err.write.call_count, 1)
                with patch("builtins.open", side_effect=OSError("invented input failure")), \
                        patch("sys.stderr") as err:
                    getattr(err, operation).side_effect = failure("invented diagnostic failure")
                    self.assertEqual(export.main(args), 1)

    def test_export_cli_success_and_failure(self):
        raw = dump(fixture()).encode()
        args = ["invented.json", "--receipt-sha256", hashlib.sha256(raw).hexdigest(),
                "--source-sha256", "a"*64, "--runner-sha256", "b"*64]
        with patch("builtins.open", return_value=io.BytesIO(raw)), \
                patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(export.main(args), 0)
            self.assertEqual(json.loads(out.getvalue()), run_fixture(fixture()))
        for args in ([], ["bad"], ["x"]*7):
            with patch("sys.stderr", new_callable=io.StringIO) as err, \
                    patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(export.main(args), 2)
                self.assertEqual(out.getvalue(), "")
                self.assertEqual(err.getvalue(), "error: invalid input\n")

    def test_exact_derived_shape_and_redaction(self):
        source = fixture()
        original = copy.deepcopy(source)
        result = run_fixture(source)
        self.assertEqual(source, original)
        self.assertEqual(set(result), {"schema", "metrics", "checks", "derived", "resources"})
        self.assertEqual(result["metrics"], source["result"]["metrics"])
        self.assertEqual(result["checks"], source["result"]["checks"])
        self.assertEqual(set(result["derived"]), {"seed_summary", "pooled_reliability"})
        for method in export.METHODS:
            summary = result["derived"]["seed_summary"][method]
            self.assertEqual(set(summary), set(export.SCORES))
            for row in summary.values():
                self.assertEqual(set(row), {"mean", "sample_sd"})
                self.assertAlmostEqual(row["sample_sd"], 0.0, delta=1e-15)
            pooled = result["derived"]["pooled_reliability"][method]
            self.assertEqual(set(pooled), {"n", "ece", "bins"})
            self.assertEqual((pooled["n"], pooled["ece"]), (600, 0.0))
            self.assertEqual(len(pooled["bins"]), 4)
            for row in pooled["bins"]:
                self.assertEqual(set(row), {"lower", "upper", "upper_inclusive", "count",
                                           "sum_p", "sum_y", "mean_p", "mean_y"})
            self.assertIsNone(pooled["bins"][0]["mean_p"])
            self.assertEqual(pooled["bins"][2]["mean_p"], .5)
        self.assertNotIn("INVENTED_PRIVATE_SENTINEL", dump(result))
        text = export.render_markdown(result)
        self.assertIn("Derived oracle pooled ECE: 0.0", text)
        self.assertEqual(sum(text.count(f"| {s} |") for s in export.SEEDS), 12)

    def test_check_cardinality_order_and_types(self):
        for mode in ("duplicate", "missing", "reordered", "false", "integer", "extra"):
            data = fixture()
            checks = data["result"]["checks"]
            if mode == "duplicate": checks[1] = checks[0].copy()
            if mode == "missing": checks.pop()
            if mode == "reordered": checks[0], checks[1] = checks[1], checks[0]
            if mode == "false": checks[0]["passed"] = False
            if mode == "integer": checks[0]["passed"] = 1
            if mode == "extra": checks.append(checks[0].copy())
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                run_fixture(data)

    def test_metric_integrity_rejections(self):
        changes = [
            ("oracle_b2_count", True), ("oracle_b2_count", 600.0),
            ("oracle_b2_count", 599), ("oracle_b2_count", -1),
            ("oracle_b2_sum_y", 601), ("oracle_b2_sum_y", 299),
            ("oracle_b0_sum_p", 1e-13), ("oracle_b0_sum_y", 1),
            ("oracle_b2_sum_p", 299.0), ("oracle_b2_sum_p", 451.0),
            ("oracle_b2_sum_p", 300), ("s7_oracle_brier", 1),
            ("s7_oracle_brier", 1.1), ("s7_oracle_log_loss", 29.0),
            ("total_processed_forecast_records", 2400), ("method_count", 4.0),
        ]
        for key, value in changes:
            data = fixture()
            data["result"]["metrics"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                run_fixture(data)
        for mode in ("extra", "missing"):
            data = fixture()
            if mode == "extra": data["result"]["metrics"]["extra"] = 0
            else: del data["result"]["metrics"]["method_count"]
            with self.assertRaises(ValueError): run_fixture(data)

    def test_receipt_resource_digest_and_json_rejections(self):
        for key, value in [
            ("outcome", "fail"), ("owned_child_reaped", 1), ("compute_threads", True),
            ("cpu_seconds", 0.0), ("wall_seconds", -1), ("peak_memory_bytes", 1.0),
            ("memory_hard_limit", True), ("source_sha256", "c"*64),
        ]:
            data = fixture()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): run_fixture(data)
        raw = dump(fixture()).encode()
        with self.assertRaises(ValueError):
            export.export_receipt(raw, "c"*64, "a"*64, "b"*64)
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b" " * 1048577):
            with self.assertRaises(ValueError):
                export.export_receipt(raw, hashlib.sha256(raw).hexdigest(), "a"*64, "b"*64)

    def test_pooled_ece_not_seed_mean_and_sd_formula(self):
        data = fixture()
        # Hand-derived variation: 80/100/120 positives in the three seeds.
        # Constant p=0.5 preserves Brier=.25 and log_loss=log(2). Gaps and
        # ECEs are .1/0/.1; pooled positives remain 300, pooled ECE remains 0.
        for method in export.METHODS:
            for seed, value in zip(export.SEEDS, (.1, 0.0, .1)):
                for score in ("gap", "ece"):
                    data["result"]["metrics"][f"s{seed}_{method}_{score}"] = value
        result = run_fixture(data)
        self.assertAlmostEqual(result["derived"]["seed_summary"]["oracle"]["gap"]["mean"], 1/15)
        self.assertAlmostEqual(result["derived"]["seed_summary"]["oracle"]["gap"]["sample_sd"], math.sqrt(1/300))
        self.assertEqual(result["derived"]["pooled_reliability"]["oracle"]["ece"], 0.0)
        self.assertAlmostEqual(result["derived"]["seed_summary"]["oracle"]["ece"]["mean"], 1/15)
