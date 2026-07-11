"""Validation engine for schemacheck.

Checks each loaded record against a :class:`~schemacheck.schema.Schema` model
and emits a :class:`Violation` for every failed rule. This is where declared
types and constraints actually catch bad data; every violation the report
prints originates here.

The engine is deliberately independent of *how* records were loaded and *how*
violations are reported — it takes a plain ``list[dict]`` and a ``Schema`` and
returns a ``list[Violation]``. That keeps the reporting and CLI layers (later
slices) free to change without touching validation logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from schemacheck.schema import FieldSpec, Schema

__all__ = ["Violation", "validate"]


@dataclass(frozen=True)
class Violation:
    """A single failed check.

    ``row`` is the 1-based index of the offending record, ``field`` is the
    field name, and ``message`` describes the constraint that failed and the
    value that failed it.
    """

    row: int
    field: str
    message: str


def validate(records: list[dict], schema: Schema) -> list[Violation]:
    """Validate ``records`` against ``schema``, returning all violations.

    Records are numbered from 1. For each record, every field in the schema is
    checked in turn; a field that fails an earlier check (missing-required or
    uncoercible type) is not subjected to the later checks that depend on a
    usable value.
    """
    violations: list[Violation] = []
    for index, record in enumerate(records, start=1):
        for spec in schema.fields:
            violations.extend(_check_field(index, record, spec))
    return violations


def _check_field(row: int, record: dict, spec: FieldSpec) -> list[Violation]:
    raw = record.get(spec.name)
    missing = spec.name not in record or _is_empty(raw)

    if missing:
        if spec.required:
            return [
                Violation(
                    row=row,
                    field=spec.name,
                    message=f"required field {spec.name!r} is missing or empty",
                )
            ]
        # An optional, absent field has nothing to validate.
        return []

    coerced, ok = _coerce(raw, spec.type)
    if not ok:
        return [
            Violation(
                row=row,
                field=spec.name,
                message=(
                    f"value {raw!r} is not a valid {spec.type}"
                ),
            )
        ]

    return _check_constraints(row, spec, raw, coerced)


def _check_constraints(
    row: int, spec: FieldSpec, raw: Any, coerced: Any
) -> list[Violation]:
    out: list[Violation] = []
    constraints = spec.constraints

    if "min" in constraints and coerced < constraints["min"]:
        out.append(
            Violation(
                row=row,
                field=spec.name,
                message=f"value {coerced} is below the min {constraints['min']}",
            )
        )
    if "max" in constraints and coerced > constraints["max"]:
        out.append(
            Violation(
                row=row,
                field=spec.name,
                message=f"value {coerced} exceeds the max {constraints['max']}",
            )
        )
    if "minLength" in constraints and len(str(coerced)) < constraints["minLength"]:
        out.append(
            Violation(
                row=row,
                field=spec.name,
                message=(
                    f"value {raw!r} is shorter than the minLength "
                    f"{constraints['minLength']}"
                ),
            )
        )
    if "maxLength" in constraints and len(str(coerced)) > constraints["maxLength"]:
        out.append(
            Violation(
                row=row,
                field=spec.name,
                message=(
                    f"value {raw!r} is longer than the maxLength "
                    f"{constraints['maxLength']}"
                ),
            )
        )
    if "regex" in constraints:
        pattern = constraints["regex"]
        if re.search(pattern, str(coerced)) is None:
            out.append(
                Violation(
                    row=row,
                    field=spec.name,
                    message=f"value {raw!r} does not match regex {pattern!r}",
                )
            )
    if "enum" in constraints:
        allowed = constraints["enum"]
        if coerced not in allowed and raw not in allowed:
            out.append(
                Violation(
                    row=row,
                    field=spec.name,
                    message=(
                        f"value {raw!r} is not in the enum {list(allowed)!r}"
                    ),
                )
            )
    return out


def _is_empty(value: Any) -> bool:
    """Treat ``None`` and blank/whitespace-only strings as empty."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


_TRUE_STRINGS = frozenset({"true", "1", "yes"})
_FALSE_STRINGS = frozenset({"false", "0", "no"})


def _coerce(value: Any, declared_type: str) -> tuple[Any, bool]:
    """Coerce ``value`` to ``declared_type``.

    Returns ``(coerced_value, ok)``. CSV supplies every value as a ``str``;
    JSON may already supply native ints/floats/bools. Both are handled.
    """
    if declared_type == "string":
        return (value if isinstance(value, str) else str(value)), True

    if declared_type == "integer":
        if isinstance(value, bool):
            # bool is a subclass of int, but a boolean is not an integer value.
            return None, False
        if isinstance(value, int):
            return value, True
        try:
            return int(str(value).strip()), True
        except (TypeError, ValueError):
            return None, False

    if declared_type == "number":
        if isinstance(value, bool):
            return None, False
        if isinstance(value, (int, float)):
            return float(value), True
        try:
            return float(str(value).strip()), True
        except (TypeError, ValueError):
            return None, False

    if declared_type == "boolean":
        if isinstance(value, bool):
            return value, True
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _TRUE_STRINGS:
                return True, True
            if lowered in _FALSE_STRINGS:
                return False, True
        return None, False

    # Unknown types should have been rejected by the schema layer; treat as a
    # coercion failure rather than silently passing.
    return None, False
