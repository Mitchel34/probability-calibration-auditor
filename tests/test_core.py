import copy
import math
import unittest
from probability_calibration_auditor import audit
from probability_calibration_auditor.core import audit_integrity


class AuditTests(unittest.TestCase):
    def assertScores(self, p, y, expected):
        result = audit(p, y)
        self.assertEqual(set(result), {"schema", "n", "scores", "bins"})
        self.assertEqual(result["schema"], "probability-audit/1")
        self.assertEqual(result["n"], len(p))
        for key, value in zip(("brier", "log_loss", "gap", "ece"), expected):
            self.assertTrue(math.isclose(result["scores"][key], value, rel_tol=1e-12, abs_tol=1e-12),
                            (key, result["scores"][key], value))
        return result

    def test_perfect_endpoints(self):
        result = self.assertScores([0, 1], [0, 1], [0, -math.log(1-1e-12), 0, 0])
        self.assertEqual([r["count"] for r in result["bins"]], [1, 0, 0, 1])
        for row in result["bins"][1:3]:
            self.assertEqual([row[k] for k in ("count", "sum_p", "sum_y", "mean_p", "mean_y")],
                             [0, 0.0, 0, None, None])

    def test_wrong_endpoints_preserve_clipping_asymmetry(self):
        loss = -(math.log(1e-12) + math.log(1-(1-1e-12))) / 2
        self.assertScores([0, 1], [1, 0], [1, loss, 0, 1])

    def test_hand_oracles(self):
        for p, y, expected in [
            ([.25, .75], [0, 1], [.0625, -math.log(.75), 0, .25]),
            ([.25, .25], [0, 1], [.3125, -(math.log(.75)+math.log(.25))/2, .25, .25]),
            ([.5, .5], [0, 1], [.25, math.log(2), 0, 0]),
            ([0, .25, .75, 1], [0, 1, 0, 1],
             [.28125, -(2*math.log(1-1e-12)+2*math.log(.25))/4, 0, .375]),
        ]:
            with self.subTest(p=p, y=y):
                self.assertScores(p, y, expected)

    def test_exact_edges_and_neighbors(self):
        result = audit([0, .25, .5, .75, 1], [0]*5)
        self.assertEqual([r["count"] for r in result["bins"]], [1, 1, 1, 2])
        for i, edge in enumerate((.25, .5, .75)):
            result = audit([math.nextafter(edge, 0), edge, math.nextafter(edge, 1)], [0]*3)
            counts = [0]*4
            counts[i], counts[i+1] = 1, 2
            self.assertEqual([r["count"] for r in result["bins"]], counts)
        self.assertEqual([r["upper_inclusive"] for r in result["bins"]], [False, False, False, True])

    def test_validation(self):
        bad = [
            ([], []), ([.5], []), ((.5,), [0]), ([.5], (0,)),
            ([True], [0]), ([.5], [False]), ([.5], [1.0]),
            ([.5], [2]), ([".5"], [0]), ([None], [0]),
            ([float("nan")], [0]), ([float("inf")], [0]),
            ([-.001], [0]), ([1.001], [0]), ([10**1000], [0]),
            ([.5]*10001, [0]*10001), (None, None),
        ]
        for p, y in bad:
            with self.subTest(kind=type(p)):
                with self.assertRaisesRegex(ValueError, "^invalid input$"):
                    audit(p, y)

    def test_deterministic_no_mutation_and_row_limit(self):
        p, y = [0, .2, .8, 1], [0, 1, 0, 1]
        original = copy.deepcopy((p, y))
        self.assertEqual(audit(p, y), audit(p, y))
        self.assertEqual((p, y), original)
        self.assertEqual(audit([.5]*10000, [0]*10000)["n"], 10000)
        self.assertEqual(audit([-0.0], [0])["bins"][0]["sum_p"], 0.0)

    def test_integrity_detects_corrupted_scores_and_bins(self):
        p, y = [.25, .75], [0, 1]
        result = audit(p, y)
        self.assertTrue(audit_integrity(result, p, y))
        result["scores"]["ece"] = 0.0
        self.assertFalse(audit_integrity(result, p, y))
        result = audit(p, y)
        result["bins"][0]["sum_p"] = 1.0
        self.assertFalse(audit_integrity(result, p, y))
