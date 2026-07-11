"""Schema-definition layer for schemacheck.

Parses a YAML schema file into an in-memory model that the validation engine
consumes. The expected YAML shape is a mapping with a ``fields`` list, each
entry declaring a field's ``name``, ``type`` and optional ``required`` flag and
``constraints``:

.. code-block:: yaml

    fields:
      - name: id
        type: integer
        required: true
      - name: age
        type: integer
        constraints: {min: 0, max: 120}
      - name: email
        type: string
        constraints: {regex: "^.+@.+$"}

Supported ``type`` values: ``string``, ``integer``, ``number``, ``boolean``.
Supported ``constraints``: ``min``/``max`` (numeric), ``regex`` (string),
``enum`` (list of allowed values).

Malformed input (unknown type, non-mapping root, a field missing ``name``)
raises :class:`SchemaError` with a message naming the offending field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = ["FieldSpec", "Schema", "SchemaError", "load_schema"]

# The concrete field types the schema layer understands.
SUPPORTED_TYPES = frozenset({"string", "integer", "number", "boolean"})

# Constraint keys the schema layer understands. The validation engine (a later
# slice) is responsible for applying them; this layer only parses and models.
SUPPORTED_CONSTRAINTS = frozenset({"min", "max", "regex", "enum"})


class SchemaError(Exception):
    """Raised when a schema document is malformed or declares an unknown type."""


@dataclass(frozen=True)
class FieldSpec:
    """A single field declaration from the schema document."""

    name: str
    type: str
    required: bool = False
    constraints: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Schema:
    """An ordered collection of :class:`FieldSpec` entries."""

    fields: list[FieldSpec]


def _parse_field(raw: Any, index: int) -> FieldSpec:
    if not isinstance(raw, dict):
        raise SchemaError(
            f"field #{index} must be a mapping, got {type(raw).__name__}"
        )

    name = raw.get("name")
    if name is None:
        raise SchemaError(f"field #{index} is missing required key 'name'")
    if not isinstance(name, str):
        raise SchemaError(f"field #{index} 'name' must be a string, got {name!r}")

    field_type = raw.get("type")
    if field_type not in SUPPORTED_TYPES:
        raise SchemaError(
            f"field {name!r} declares unknown type {field_type!r}; "
            f"supported types are {sorted(SUPPORTED_TYPES)}"
        )

    required = bool(raw.get("required", False))

    constraints = raw.get("constraints", {})
    if constraints is None:
        constraints = {}
    if not isinstance(constraints, dict):
        raise SchemaError(
            f"field {name!r} 'constraints' must be a mapping, "
            f"got {type(constraints).__name__}"
        )
    unknown = set(constraints) - SUPPORTED_CONSTRAINTS
    if unknown:
        raise SchemaError(
            f"field {name!r} declares unknown constraint(s) {sorted(unknown)}; "
            f"supported constraints are {sorted(SUPPORTED_CONSTRAINTS)}"
        )

    return FieldSpec(
        name=name,
        type=field_type,
        required=required,
        constraints=dict(constraints),
    )


def load_schema(path: str | Path) -> Schema:
    """Load and model a YAML schema definition from ``path``.

    Raises :class:`SchemaError` if the document is malformed.
    """
    text = Path(path).read_text()
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise SchemaError(f"could not parse YAML: {exc}") from exc

    if not isinstance(document, dict):
        raise SchemaError(
            f"schema root must be a mapping with a 'fields' list, "
            f"got {type(document).__name__}"
        )

    raw_fields = document.get("fields")
    if not isinstance(raw_fields, list):
        raise SchemaError(
            "schema must declare a 'fields' list at the root"
        )

    specs = [_parse_field(raw, i) for i, raw in enumerate(raw_fields)]
    return Schema(fields=specs)
