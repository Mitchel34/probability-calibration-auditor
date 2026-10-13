import io
import json
import unittest
from unittest.mock import patch
from probability_calibration_auditor.cli import main
from probability_calibration_auditor.jsonio import loads, MAX_BYTES


def invoke(raw=b"", argv=None):
    stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch("sys.stdin", stdin), patch("sys.stdout", stdout), patch("sys.stderr", stderr):
        code = main([] if argv is None else argv)
    return code, stdout.getvalue(), stderr.getvalue()


class CliTests(unittest.TestCase):
    def test_success_canonical_output(self):
        raw = b'{"probabilities":[0.25,0.75],"outcomes":[0,1]}'
        code, out, err = invoke(raw)
        self.assertEqual((code, err), (0, ""))
        value = json.loads(out)
        self.assertEqual(value["scores"]["brier"], .0625)
        self.assertEqual(out, json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n")
        self.assertEqual(invoke(raw)[1], out)

    def test_demo_help_arguments(self):
        self.assertEqual(json.loads(invoke(argv=["--demo"])[1])["scores"]["brier"], .28125)
        self.assertEqual(invoke(argv=["--help"])[0], 0)
        self.assertEqual(invoke(argv=["--wat"]), (2, "", "error: invalid input\n"))

    def test_malformed_inputs(self):
        cases = [
            b"", b"null", b"[]", b"{}", b"\xff", b"\xef\xbb\xbf{}",
            b'{"probabilities":[.5],"outcomes":[0]}',
            b'{"probabilities":[0.5],"outcomes":[0]} {}',
            b'{"probabilities":[0.5],"outcomes":[0],"outcomes":[1]}',
            b'{"probabilities":[0.5],"outcomes":[0],"extra":0}',
            b'{"probabilities":[NaN],"outcomes":[0]}',
            b'{"probabilities":[Infinity],"outcomes":[0]}',
            b'{"probabilities":[1e999],"outcomes":[0]}',
            b'{"probabilities":[true],"outcomes":[0]}',
            b'{"probabilities":[0.5],"outcomes":[true]}',
            b'{"probabilities":[0.5],"outcomes":[1.0]}',
            b'{"probabilities":[0.5],"outcomes":[0,1]}',
            b'{"probabilities":[],"outcomes":[]}',
            b'{"probabilities":[[[[[0]]]]],"outcomes":[0]}',
            b'{"probabilities":[' + b"0"*65 + b'],"outcomes":[0]}',
            b'{"probabilities":[' + b"1"*65 + b'],"outcomes":[0]}',
            b" "* (MAX_BYTES+1),
        ]
        for raw in cases:
            with self.subTest(prefix=raw[:40]):
                self.assertEqual(invoke(raw), (2, "", "error: invalid input\n"))

    def test_byte_depth_token_boundaries(self):
        raw = b'{"probabilities":[0.5],"outcomes":[0]}'
        self.assertEqual(invoke(raw + b" "*(MAX_BYTES-len(raw)))[0], 0)
        self.assertEqual(invoke(raw + b" "*(MAX_BYTES+1-len(raw)))[0], 2)
        self.assertEqual(loads(b"[[[[]]]]"), [[[[]]]])
        with self.assertRaises(ValueError):
            loads(b"[[[[[]]]]]")
        self.assertEqual(loads(('1' * 64).encode()), int('1'*64))
        with self.assertRaises(ValueError):
            loads(('1' * 65).encode())
        self.assertEqual(loads(b'{"x":"[}\\\""}'), {"x": '[}"'})
        with self.assertRaises(ValueError):
            loads(b'{"x":[}')

    def test_io_and_broken_pipe(self):
        with patch("sys.stdout") as out:
            out.write.side_effect = BrokenPipeError()
            self.assertEqual(main(["--help"]), 1)
        with patch("sys.stdin") as inp, patch("sys.stderr", new_callable=io.StringIO) as err:
            inp.buffer.read.side_effect = OSError()
            self.assertEqual(main([]), 1)
            self.assertEqual(err.getvalue(), "error: I/O failure\n")

    def test_stdout_flush_and_diagnostic_failures(self):
        for argv in (["--help"], ["--demo"]):
            for failure in (BrokenPipeError, OSError):
                with self.subTest(argv=argv, failure=failure), patch("sys.stdout") as out, \
                        patch("sys.stderr") as err:
                    out.flush.side_effect = failure("invented flush failure")
                    out.close.side_effect = failure("invented close failure")
                    self.assertEqual(main(argv), 1)
                    out.close.assert_called()
        for operation in ("write", "flush"):
            for failure in (BrokenPipeError, OSError):
                with self.subTest(operation=operation, failure=failure), \
                        patch("sys.stderr") as err:
                    getattr(err, operation).side_effect = failure("invented diagnostic failure")
                    err.close.side_effect = failure("invented close failure")
                    self.assertEqual(main(["--invalid"]), 1)
                    err.close.assert_called_once()
                    self.assertEqual(err.write.call_count, 1)
                with patch("sys.stdin") as inp, patch("sys.stderr") as err:
                    inp.buffer.read.side_effect = OSError("invented input failure")
                    getattr(err, operation).side_effect = failure("invented diagnostic failure")
                    self.assertEqual(main([]), 1)

