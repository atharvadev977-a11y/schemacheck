"""Tests for the validation engine and the CSV/JSON loaders.

These tests exercise the end-to-end path a real run takes: load records from a
file, validate them against a ``Schema`` model, and inspect the structured
violations. Each constraint arm has a fixture that genuinely crosses its
boundary, and a fully-valid dataset proves the engine does not cry wolf.
"""

from __future__ import annotations

import json

# Import the validation engine and loaders through the package root. This is the
# stable surface the CLI slice consumes, and it also makes the red-first proof
# robust: the public API is re-exported from ``schemacheck/__init__.py`` (a file
# that exists on the base branch), so reverting this slice's changes removes the
# re-exports and this import fails — the whole module goes RED, not merely green.
from schemacheck import FieldSpec, Schema, Violation, load_records, validate


def _schema() -> Schema:
    """A schema touching every constraint type the engine understands."""
    return Schema(
        fields=[
            FieldSpec(name="id", type="integer", required=True),
            FieldSpec(name="age", type="integer", constraints={"min": 0, "max": 120}),
            FieldSpec(name="email", type="string", constraints={"regex": r"^.+@.+$"}),
            FieldSpec(
                name="color",
                type="string",
                constraints={"enum": ["red", "green", "blue"]},
            ),
        ]
    )


def test_schema_import() -> None:
    """The predecessor `schema` slice API imports and a Schema fixture builds."""
    schema = _schema()
    assert isinstance(schema, Schema)
    assert [f.name for f in schema.fields] == ["id", "age", "email", "color"]


def test_public_api_surface() -> None:
    """The engine + loader are reachable from the package root for the CLI slice.

    This is the interface later slices import; it also anchors the red-first
    proof to ``schemacheck/__init__.py`` (present on base), so reverting this
    slice drops the re-exports and the import above fails loudly.
    """
    import schemacheck

    for name in ("validate", "load_records", "Violation"):
        assert name in schemacheck.__all__, f"{name!r} missing from public API"
        assert hasattr(schemacheck, name), f"schemacheck.{name} not exported"
    # The exported symbols are the real callables/types, not placeholders.
    assert schemacheck.validate is validate
    assert schemacheck.load_records is load_records
    assert schemacheck.Violation is Violation


def test_loaders_csv_json_equivalent(tmp_path) -> None:
    """CSV and JSON loaders yield the same list-of-dicts shape for equal data."""
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,age\n1,30\n")
    json_path = tmp_path / "data.json"
    json_path.write_text(json.dumps([{"id": "1", "age": "30"}]))

    csv_records = load_records(csv_path)
    json_records = load_records(json_path)

    assert csv_records == [{"id": "1", "age": "30"}]
    assert json_records == [{"id": "1", "age": "30"}]
    assert csv_records == json_records


def test_loaders_json_single_object_wrapped(tmp_path) -> None:
    """A top-level JSON object is wrapped into a 1-element list."""
    json_path = tmp_path / "one.json"
    json_path.write_text(json.dumps({"id": "1", "age": "30"}))
    assert load_records(json_path) == [{"id": "1", "age": "30"}]


def test_each_constraint_flags() -> None:
    """Wrong-type, out-of-range, bad-regex, and non-enum each flag correctly."""
    records = [
        {
            "id": "notanint",  # type violation: not an integer
            "age": "200",  # max violation: 200 > 120
            "email": "nope",  # regex violation: no '@'
            "color": "purple",  # enum violation: not in allowed list
        }
    ]
    violations = validate(records, _schema())
    by_field = {v.field: v for v in violations}

    # Row is 1-based; the single record is row 1.
    assert all(v.row == 1 for v in violations), violations

    assert "id" in by_field, f"expected an id type violation, got {violations!r}"
    assert "int" in by_field["id"].message.lower(), by_field["id"].message

    assert "age" in by_field, f"expected an age max violation, got {violations!r}"
    assert "max" in by_field["age"].message.lower(), by_field["age"].message

    assert "email" in by_field, f"expected an email regex violation, got {violations!r}"
    assert (
        "regex" in by_field["email"].message.lower()
        or "pattern" in by_field["email"].message.lower()
    ), by_field["email"].message

    assert "color" in by_field, f"expected a color enum violation, got {violations!r}"
    assert "enum" in by_field["color"].message.lower(), by_field["color"].message


def test_min_boundary_out_of_range() -> None:
    """A value below the declared minimum flags a min violation; the boundary passes."""
    schema = Schema(
        fields=[FieldSpec(name="age", type="integer", constraints={"min": 0, "max": 120})]
    )
    # Just outside the low boundary.
    below = validate([{"age": "-1"}], schema)
    assert len(below) == 1, below
    assert below[0].field == "age"
    assert "min" in below[0].message.lower(), below[0].message

    # The boundary value itself is valid — no violation.
    assert validate([{"age": "0"}], schema) == []
    assert validate([{"age": "120"}], schema) == []


def test_boolean_and_number_coercion() -> None:
    """boolean and number arms coerce valid strings and flag invalid ones."""
    schema = Schema(
        fields=[
            FieldSpec(name="active", type="boolean"),
            FieldSpec(name="score", type="number", constraints={"min": 0.0}),
        ]
    )
    # Valid: "true" coerces to bool, "3.5" coerces to float in range.
    assert validate([{"active": "true", "score": "3.5"}], schema) == []

    # Invalid boolean string flags a type violation naming the field.
    bad_bool = validate([{"active": "maybe", "score": "1"}], schema)
    assert [v.field for v in bad_bool] == ["active"], bad_bool
    assert "boolean" in bad_bool[0].message.lower(), bad_bool[0].message

    # Non-numeric string flags a number type violation, not a range one.
    bad_num = validate([{"active": "false", "score": "high"}], schema)
    assert [v.field for v in bad_num] == ["score"], bad_num
    assert "number" in bad_num[0].message.lower(), bad_num[0].message


def test_native_json_types_validate() -> None:
    """Native (JSON) ints/floats/bools validate without string coercion."""
    schema = Schema(
        fields=[
            FieldSpec(name="age", type="integer", constraints={"max": 120}),
            FieldSpec(name="active", type="boolean"),
        ]
    )
    assert validate([{"age": 30, "active": True}], schema) == []
    over = validate([{"age": 200, "active": False}], schema)
    assert [v.field for v in over] == ["age"], over
    assert "max" in over[0].message.lower(), over[0].message


def test_required_missing() -> None:
    """A required field left blank produces exactly one violation naming it."""
    records = [{"id": "", "age": "30", "email": "a@b", "color": "red"}]
    violations = validate(records, _schema())
    required = [v for v in violations if v.field == "id"]
    assert len(required) == 1, violations
    assert required[0].row == 1
    assert "required" in required[0].message.lower(), required[0].message


def test_row_index_is_one_based_for_second_record() -> None:
    """The second bad record reports row 2, distinguishing 0- from 1-based."""
    schema = Schema(fields=[FieldSpec(name="age", type="integer", constraints={"max": 10})])
    records = [{"age": "5"}, {"age": "99"}]
    violations = validate(records, schema)
    assert len(violations) == 1, violations
    assert violations[0].row == 2, violations[0]


def test_valid_dataset_no_violations() -> None:
    """A fully-valid dataset yields zero violations."""
    records = [
        {"id": "1", "age": "30", "email": "a@b.com", "color": "green"},
        {"id": "2", "age": "0", "email": "x@y", "color": "blue"},
    ]
    assert validate(records, _schema()) == []


def test_violation_is_structured() -> None:
    """Violation carries the row, field, and a message — the report's inputs."""
    v = Violation(row=1, field="age", message="value 200 exceeds max 120")
    assert v.row == 1
    assert v.field == "age"
    assert "max" in v.message
