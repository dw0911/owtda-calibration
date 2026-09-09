"""Canonical serialization contracts (Plan §15.2).

Rules enforced here:
  * canonical JSON: UTF-8, sorted keys, no whitespace, ``ensure_ascii=False``,
    ``allow_nan=False``; field names limited to ASCII; keys/strings NFC;
    value types limited to ``null/bool/int/str/list/dict`` plus ``Decimal``
    (auto-converted to canonical decimal text); bare ``float`` rejected.
  * canonical decimal text: no exponent, no leading ``+``, no redundant
    leading/trailing zeros, ``-0`` normalised to ``0``.  Accepts ``int``,
    ``Decimal`` and already-canonical ``str``.
  * single-object content hash:
    ``SHA256(canonical_json(obj).encode("utf-8") + b"\\n").hexdigest()``.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from decimal import Decimal
from typing import Any

_ELEMENT_TYPES = (type(None), bool, int, str, list, dict)
_MAX_DEPTH = 128


class CanonicalizationError(ValueError):
    """Object cannot be represented under the canonical contracts."""


def canonical_decimal_text(value: Any) -> str:
    """Return the canonical decimal text for int/Decimal/canonical str.

    ``float`` is always rejected: a binary64 cannot be unambiguously mapped to
    a canonical decimal string (Plan §15.2 requires config reals to enter via
    ``Decimal`` / decimal text).
    """
    if isinstance(value, bool):
        raise CanonicalizationError("bool is not a canonical decimal")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalizationError(f"non-finite Decimal: {value}")
        if value.is_zero():
            return "0"
        sign = "-" if value.is_signed() else ""
        s = format(abs(value), "f")  # plain decimal, never exponent
        if "." in s:
            ip, fp = s.split(".", 1)
        else:
            ip, fp = s, ""
        ip = ip.lstrip("0") or "0"
        fp = fp.rstrip("0")
        body = ip if not fp else f"{ip}.{fp}"
        if body == "0":
            return "0"
        return sign + body
    if isinstance(value, str):
        if value == "" or value != value.strip():
            raise CanonicalizationError(f"non-canonical decimal text: {value!r}")
        if not value.isascii():
            raise CanonicalizationError(f"non-ASCII decimal text: {value!r}")
        try:
            d = Decimal(value)
        except Exception as exc:
            raise CanonicalizationError(f"unparseable decimal text: {value!r}") from exc
        if not d.is_finite():
            raise CanonicalizationError(f"non-finite decimal text: {value!r}")
        canon = canonical_decimal_text(d)
        if canon != value:
            raise CanonicalizationError(
                f"non-canonical decimal text (would normalise to {canon!r}): {value!r}"
            )
        return canon
    raise CanonicalizationError(
        "canonical decimal accepts int/Decimal/canonical str, not "
        f"{type(value).__name__}"
    )


def _normalize(obj: Any, *, _depth: int = 0) -> Any:
    if _depth > _MAX_DEPTH:
        raise CanonicalizationError("object nesting too deep")
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, Decimal):
        return canonical_decimal_text(obj)
    if isinstance(obj, float):
        raise CanonicalizationError(
            "bare float forbidden in canonical payload; pass canonical decimal "
            "text (Decimal/str) instead"
        )
    if isinstance(obj, (list, tuple)):
        return [_normalize(x, _depth=_depth + 1) for x in obj]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, val in obj.items():
            if not isinstance(key, str):
                raise CanonicalizationError(f"dict key must be str: {key!r}")
            if not key.isascii():
                raise CanonicalizationError(
                    f"dict field name must be ASCII: {key!r}"
                )
            nkey = unicodedata.normalize("NFC", key)
            if nkey in out:
                raise CanonicalizationError(
                    f"canonical key collision (after NFC): {nkey!r}"
                )
            out[nkey] = _normalize(val, _depth=_depth + 1)
        return out
    raise CanonicalizationError(
        f"unsupported canonical value type: {type(obj).__name__}"
    )


def canonical_json(obj: Any) -> str:
    """Strict canonical JSON text (Plan §15.2)."""
    normalized = _normalize(obj)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_json_bytes(obj: Any) -> bytes:
    """canonical_json as UTF-8 bytes."""
    return canonical_json(obj).encode("utf-8")


def single_object_content_hash(obj: Any) -> str:
    """SHA256(canonical_json(obj).encode('utf-8') + b'\\n') (64 lowercase hex)."""
    payload = canonical_json_bytes(obj) + b"\n"
    return hashlib.sha256(payload).hexdigest()
