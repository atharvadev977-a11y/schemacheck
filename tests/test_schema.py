"""Tests for the YAML schema-definition parser (schemacheck.schema)."""

import textwrap

import pytest

from schemacheck.schema import FieldSpec, Schema, SchemaError, load_schema

EXAMPLE_YAML = textwrap.dedent(
    """\
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
    """
)


def _write(tmp_path, text):
    path = tmp_path / "schema.yaml"
    path.write_text(text)
    return path


def test_load_basic_schema(tmp_path):
    schema = load_schema(_write(tmp_path, EXAMPLE_YAML))

    assert isinstance(schema, Schema)
    assert len(schema.fields) == 3
    # Order is preserved from the document.
    assert [f.name for f in schema.fields] == ["id", "age", "email"]
    assert all(isinstance(f, FieldSpec) for f in schema.fields)


def test_fieldspec_constraints(tmp_path):
    schema = load_schema(_write(tmp_path, EXAMPLE_YAML))
    by_name = {f.name: f for f in schema.fields}

    id_spec = by_name["id"]
    assert id_spec.type == "integer"
    assert id_spec.required is True
    assert id_spec.constraints == {}

    age_spec = by_name["age"]
    assert age_spec.type == "integer"
    assert age_spec.required is False  # default when omitted
    assert age_spec.constraints == {"min": 0, "max": 120}

    email_spec = by_name["email"]
    assert email_spec.type == "string"
    assert email_spec.constraints == {"regex": "^.+@.+$"}


def test_unknown_type_raises(tmp_path):
    bad = textwrap.dedent(
        """\
        fields:
          - name: weight
            type: float
        """
    )
    with pytest.raises(SchemaError) as excinfo:
        load_schema(_write(tmp_path, bad))
    # Message must name the offending field and the bad type.
    assert "weight" in str(excinfo.value)


def test_malformed_schema_raises(tmp_path):
    # Non-mapping root (a bare list, not a mapping with `fields`).
    non_mapping = "- just\n- a\n- list\n"
    with pytest.raises(SchemaError):
        load_schema(_write(tmp_path, non_mapping))

    # A field missing its `name`.
    missing_name = textwrap.dedent(
        """\
        fields:
          - type: integer
            required: true
        """
    )
    with pytest.raises(SchemaError):
        load_schema(_write(tmp_path, missing_name))
