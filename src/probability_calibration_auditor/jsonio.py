"""Bounded strict JSON with stable serialization; no scoring imports."""
import json
import math
import sys

MAX_BYTES = 1048576


def number(token, integer=False):
    if len(token) > 64:
        raise ValueError("invalid input")
    value = int(token) if integer else float(token)
    if not integer and not math.isfinite(value):
        raise ValueError("invalid input")
    return value


def reject_constant(token):
    raise ValueError("invalid input")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid input")
        result[key] = value
    return result


def loads(raw, max_depth=4):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("invalid input")
    text = raw.decode("utf-8")
    stack = []
    quoted = False
    escape = False
    for char in text:
        if quoted:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            stack.append(char)
            if len(stack) > max_depth:
                raise ValueError("invalid input")
        elif char in "]}":
            if not stack or stack.pop() != ({"}": "{", "]": "["}[char]):
                raise ValueError("invalid input")
    if stack or quoted:
        raise ValueError("invalid input")
    return json.loads(text, parse_int=lambda t: number(t, True),
                      parse_float=number, parse_constant=reject_constant,
                      object_pairs_hook=unique_object)


def dump(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def quiet_close(stream):
    """Prevent another buffered flush at shutdown after an I/O failure."""
    try:
        stream.close()
    except (OSError, ValueError):
        pass


def diagnostic(message, status):
    """Return I/O failure if stderr itself is unavailable; never recurse."""
    try:
        sys.stderr.write(message)
        sys.stderr.flush()
    except (OSError, ValueError):
        quiet_close(sys.stderr)
        return 1
    return status


def write_output(text):
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except OSError:
        quiet_close(sys.stdout)
        raise
