"""Strict stdin JSON command-line interface."""
import sys
from .core import audit
from .jsonio import MAX_BYTES, loads, dump, diagnostic, quiet_close, write_output

DEMO = {"probabilities": [0.0, 0.25, 0.75, 1.0], "outcomes": [0, 1, 0, 1]}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv == ["--help"]:
            write_output("Usage: probability-calibration-auditor [--demo|--help]\n"
                             "Without arguments, read one bounded JSON object from stdin.\n")
            return 0
        if argv == ["--demo"]:
            payload = DEMO
        elif not argv:
            payload = loads(sys.stdin.buffer.read(MAX_BYTES + 1))
        else:
            raise ValueError("invalid input")
        if type(payload) is not dict or set(payload) != {"probabilities", "outcomes"}:
            raise ValueError("invalid input")
        result = audit(payload["probabilities"], payload["outcomes"])
        write_output(dump(result))
        return 0
    except BrokenPipeError:
        quiet_close(sys.stdout)
        return 1
    except (ValueError, UnicodeError, TypeError, RecursionError, OverflowError):
        return diagnostic("error: invalid input\n", 2)
    except OSError:
        return diagnostic("error: I/O failure\n", 1)
