"""JSON Schema (draft 2020-12) parser for schemacheck.

A SECOND parser, not a second validation path. It reads a flat JSON Schema
document and produces the very same :class:`~schemacheck.schema.Schema` /
:class:`~schemacheck.schema.FieldSpec` objects that
:func:`schemacheck.schema.load_schema` produces from YAML — so
:mod:`schemacheck.validate` and the violation reporter are untouched. The two
schema formats stay at constraint parity: whatever one expresses, the other
expresses too.

The supported document shape is a flat object schema:

.. code-block:: json

    {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "type": "object",
      "properties": {
        "id":     {"type": "integer"},
        "age":    {"type": "integer", "minimum": 0, "maximum": 120},
        "name":   {"type": "string", "minLength": 1, "maxLength": 50},
        "email":  {"type": "string", "pattern": "^.+@.+$"},
        "status": {"type": "string", "enum": ["active", "inactive"]}
      },
      "required": ["id"]
    }

Keyword mapping onto the internal model:

- ``type`` (``string``/``integer``/``number``/``boolean``) -> ``FieldSpec.type``
- root-level ``required`` array -> ``required: True`` on the named fields
- ``minimum``/``maximum`` -> ``min``/``max``
- ``minLength``/``maxLength`` -> ``minLength``/``maxLength``
- ``pattern`` -> ``regex``
- ``enum`` -> ``enum``

**Unsupported keywords are rejected, never ignored.** Anything out of scope
(``$ref``, ``$id``, ``$defs``, the ``allOf``/``anyOf``/``oneOf``/``not``
combinators, nested object/array schemas) or otherwise unrecognised raises a
:class:`~schemacheck.schema.SchemaError` that NAMES the offending keyword. The
CLI surfaces that as exit 2 — exactly as the YAML parser rejects an unknown
constraint. Silently dropping a constraint the user wrote is the worst outcome
this tool can produce, so it does not happen. Malformed (unparseable) JSON also
raises :class:`~schemacheck.schema.SchemaError`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schemacheck.schema import FieldSpec, Schema, SchemaError

__all__ = ["load_json_schema"]

# The scalar JSON Schema types we map onto the internal type model. A nested
# ``object``/``array`` type is deliberately absent: the field set stays flat.
_SUPPORTED_TYPES = frozenset({"string", "integer", "number", "boolean"})

# Per-property JSON Schema keywords -> internal constraint keys. ``type`` is
# handled separately (it maps to FieldSpec.type, not a constraint).
_KEYWORD_TO_CONSTRAINT = {
    "minimum": "min",
    "maximum": "max",
    "minLength": "minLength",
    "maxLength": "maxLength",
    "pattern": "regex",
    "enum": "enum",
}

# Root-level keywords we accept. ``$schema`` is the dialect declaration and is
# advisory here. Everything else at the root (``$id``, ``$defs``, combinators,
# ``$ref``, ...) is out of scope and rejected by name.
_ALLOWED_ROOT_KEYS = frozenset({"$schema", "type", "properties", "required"})

# The keywords a single property may carry: ``type`` plus every mapped keyword.
_ALLOWED_PROPERTY_KEYS = frozenset({"type"}) | frozenset(_KEYWORD_TO_CONSTRAINT)


def load_json_schema(path: str | Path) -> Schema:
    """Load and model a JSON Schema (draft 2020-12) document from ``path``.

    Raises :class:`~schemacheck.schema.SchemaError` for malformed JSON, an
    unexpected document shape, or any unsupported / unrecognised keyword.
    """
    text = Path(path).read_text()
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"could not parse JSON schema: {exc}") from exc
    return _parse_document(document)


def _parse_document(document: Any) -> Schema:
    if not isinstance(document, dict):
        raise SchemaError(
            f"JSON Schema root must be an object, got {type(document).__name__}"
        )

    unknown_root = set(document) - _ALLOWED_ROOT_KEYS
    if unknown_root:
        raise SchemaError(
            f"JSON Schema uses unsupported keyword(s) {sorted(unknown_root)} at the "
            f"root; supported root keywords are {sorted(_ALLOWED_ROOT_KEYS)}"
        )

    root_type = document.get("type")
    if root_type != "object":
        raise SchemaError(
            f"JSON Schema root 'type' must be 'object', got {root_type!r}"
        )

    properties = document.get("properties")
    if not isinstance(properties, dict):
        raise SchemaError(
            "JSON Schema must declare a 'properties' object at the root"
        )

    required_names = _parse_required(document.get("required", []))

    specs = [
        _parse_property(name, subschema, name in required_names)
        for name, subschema in properties.items()
    ]
    return Schema(fields=specs)


def _parse_required(raw: Any) -> set[str]:
    if not isinstance(raw, list):
        raise SchemaError(
            f"JSON Schema 'required' must be an array, got {type(raw).__name__}"
        )
    names: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise SchemaError(
                f"JSON Schema 'required' entries must be strings, got {item!r}"
            )
        names.add(item)
    return names


def _parse_property(name: str, subschema: Any, required: bool) -> FieldSpec:
    if not isinstance(subschema, dict):
        raise SchemaError(
            f"property {name!r} must be a schema object, "
            f"got {type(subschema).__name__}"
        )

    unknown = set(subschema) - _ALLOWED_PROPERTY_KEYS
    if unknown:
        raise SchemaError(
            f"property {name!r} uses unsupported keyword(s) {sorted(unknown)}; "
            f"supported keywords are {sorted(_ALLOWED_PROPERTY_KEYS)}"
        )

    field_type = subschema.get("type")
    if field_type not in _SUPPORTED_TYPES:
        raise SchemaError(
            f"property {name!r} declares unsupported type {field_type!r}; "
            f"supported types are {sorted(_SUPPORTED_TYPES)}"
        )

    constraints: dict[str, Any] = {}
    for keyword, target in _KEYWORD_TO_CONSTRAINT.items():
        if keyword in subschema:
            constraints[target] = subschema[keyword]

    return FieldSpec(
        name=name,
        type=field_type,
        required=required,
        constraints=constraints,
    )
