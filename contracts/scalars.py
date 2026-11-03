"""Exact synthetic source values. No floats, inferred units, trimming or locale."""

import re
from datetime import UTC, datetime, timedelta, timezone

from contracts.codec import INT64_MAX, INT64_MIN, InputError

AMOUNT = re.compile(r"([+-]?)([0-9]+)(?:\.([0-9]+))?", re.ASCII)
TIMESTAMP = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]{1,6}))?(Z|[+-][0-9]{2}:[0-9]{2})", re.ASCII)


def amount_minor(text: str, *, unit: str, exponent: int) -> int:
    if unit not in ("integer_minor", "decimal_major"):
        raise InputError("UNKNOWN_UNIT")
    if type(exponent) is not int or not 0 <= exponent <= 9:
        raise InputError("INVALID_CURRENCY_EXPONENT")
    if type(text) is not str or not 1 <= len(text) <= 4096:
        raise InputError("INVALID_AMOUNT")
    match = AMOUNT.fullmatch(text)
    if not match:
        raise InputError("INVALID_AMOUNT")
    sign, whole, fraction = match.groups()
    if unit == "integer_minor":
        if fraction is not None:
            raise InputError("INVALID_AMOUNT")
        value = int(whole)
    else:
        if fraction is not None and len(fraction) > exponent:
            raise InputError("INVALID_AMOUNT")
        value = int(whole) * 10**exponent + int((fraction or "").ljust(exponent, "0") or "0")
    if sign == "-":
        value = -value
    if not INT64_MIN <= value <= INT64_MAX:
        raise InputError("INVALID_AMOUNT")
    return value


def timestamp_utc(text: str) -> str:
    if type(text) is not str or len(text) > 32:
        raise InputError("INVALID_TIMESTAMP")
    match = TIMESTAMP.fullmatch(text)
    if not match:
        raise InputError("INVALID_TIMESTAMP")
    year, month, day, hour, minute, second = (int(v) for v in match.groups()[:6])
    fraction, offset = match.groups()[6:]
    if offset == "Z":
        zone = UTC
    else:
        offset_hour, offset_minute = int(offset[1:3]), int(offset[4:6])
        # -00:00 convention expresses an unknown local offset, not an explicit one.
        if offset == "-00:00" or offset_hour > 23 or offset_minute > 59:
            raise InputError("INVALID_TIMESTAMP")
        delta = timedelta(hours=offset_hour, minutes=offset_minute)
        zone = timezone(-delta if offset[0] == "-" else delta)
    try:
        instant = datetime(year, month, day, hour, minute, second,
                           int((fraction or "").ljust(6, "0")), tzinfo=zone).astimezone(UTC)
    except (ValueError, OverflowError):
        raise InputError("INVALID_TIMESTAMP") from None
    return instant.isoformat(timespec="microseconds").replace("+00:00", "Z")
