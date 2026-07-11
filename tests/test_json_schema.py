"""Tests for the JSON Schema (draft 2020-12) parser.

This is a SECOND parser, not a second validation path: it must produce the same
:class:`~schemacheck.schema.Schema` / :class:`~schemacheck.schema.FieldSpec`
objects the YAML parser produces, so :mod:`schemacheck.validate` and the
reporter never see the difference. These tests assert the concrete keyword
mapping and that out-of-scope / unknown keywords are REJECTED (never silently
dropped), naming the offending keyword.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from schemacheck.json_schema import load_json_schema
from schemacheck.schema import SchemaError


def _write(tmp_path: Path, doc: dict) -> Path:
    p = tmp_path / "schema.json"
    p.write_text(json.dumps(doc))
    return p


def test_keyword_mapping(tmp_path: Path) -> None:
    """The six supported keyword groups map onto FieldSpec type/required/constraints.

    Each field carries a DISTINCT constraint set so a swapped or dropped mapping
    yields a caught, wrong result.
    """
    doc = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "age": {"type": "integer", "minimum": 0, "maximum": 120},
            "name": {"type": "string", "minLength": 1, "maxLength": 50},
            "email": {"type": "string", "pattern": "^.+@.+$"},
            "status": {"type": "string", "enum": ["active", "inactive"]},
        },
        "required": ["id", "age"],
    }
    schema = load_json_schema(_write(tmp_path, doc))
    by_name = {f.name: f for f in schema.fields}

    # type mapping
    assert by_name["id"].type == "integer", by_name["id"]
    assert by_name["name"].type == "string", by_name["name"]

    # root-level `required` array -> required flag on exactly those fields
    assert by_name["id"].required is True, "id is in required[]"
    assert by_name["age"].required is True, "age is in required[]"
    assert by_name["name"].required is False, "name is NOT in required[]"
    assert by_name["email"].required is False, "email is NOT in required[]"

    # minimum/maximum -> min/max
    assert by_name["age"].constraints == {"min": 0, "max": 120}, by_name["age"]
    # minLength/maxLength -> minLength/maxLength
    assert by_name["name"].constraints == {
        "minLength": 1,
        "maxLength": 50,
    }, by_name["name"]
    # pattern -> regex
    assert by_name["email"].constraints == {"regex": "^.+@.+$"}, by_name["email"]
    # enum -> enum
    assert by_name["status"].constraints == {
        "enum": ["active", "inactive"]
    }, by_name["status"]


def test_unsupported_property_keyword_is_named(tmp_path: Path) -> None:
    """An unrecognised per-property keyword is rejected and named, not ignored."""
    doc = {
        "type": "object",
        "properties": {"email": {"type": "string", "format": "email"}},
    }
    with pytest.raises(SchemaError) as exc:
        load_json_schema(_write(tmp_path, doc))
    assert "format" in str(exc.value), exc.value


def test_ref_keyword_rejected_and_named(tmp_path: Path) -> None:
    """`$ref` is out of scope: rejected with the keyword named."""
    doc = {"type": "object", "properties": {"x": {"$ref": "#/$defs/Y"}}}
    with pytest.raises(SchemaError) as exc:
        load_json_schema(_write(tmp_path, doc))
    assert "$ref" in str(exc.value), exc.value


def test_combinator_keyword_rejected_and_named(tmp_path: Path) -> None:
    """`allOf`/`anyOf`/`oneOf`/`not` combinators are out of scope and named."""
    doc = {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "allOf": [{"type": "object"}],
    }
    with pytest.raises(SchemaError) as exc:
        load_json_schema(_write(tmp_path, doc))
    assert "allOf" in str(exc.value), exc.value


def test_nested_object_type_rejected(tmp_path: Path) -> None:
    """A nested object/array field type is out of scope (flat, one level only)."""
    doc = {"type": "object", "properties": {"addr": {"type": "object"}}}
    with pytest.raises(SchemaError) as exc:
        load_json_schema(_write(tmp_path, doc))
    assert "object" in str(exc.value), exc.value


def test_malformed_json_raises_schema_error(tmp_path: Path) -> None:
    """Unparseable JSON is a SchemaError (surfaced by the CLI as exit 2)."""
    p = tmp_path / "schema.json"
    p.write_text("{not valid json")
    with pytest.raises(SchemaError):
        load_json_schema(p)
