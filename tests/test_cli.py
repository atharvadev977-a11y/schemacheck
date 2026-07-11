"""Tests for the ``schemacheck validate`` CLI layer.

The CLI is a thin shell over the parser (:func:`load_schema`), the loader
(:func:`load_records`) and the engine (:func:`validate`). These tests exercise
the WHOLE path a real invocation takes — parse args, read a real schema and a
real data file, run the real engine, render the report, and map the result to a
process exit code — not each layer in isolation.

Every fixture writes real files to a ``tmp_path`` so the loaders and parser run
for real; nothing here mocks schemacheck's own core.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from schemacheck.cli import main

_SCHEMA_YAML = """\
fields:
  - name: id
    type: integer
    required: true
  - name: age
    type: integer
    constraints: {min: 0, max: 120}
"""


def _write_schema(tmp_path: Path) -> Path:
    schema = tmp_path / "schema.yaml"
    schema.write_text(_SCHEMA_YAML)
    return schema


def _write_valid_csv(tmp_path: Path) -> Path:
    data = tmp_path / "good.csv"
    data.write_text("id,age\n1,30\n2,45\n")
    return data


def _write_invalid_csv(tmp_path: Path) -> Path:
    # Row 1 has age 200 (exceeds max 120); row 2 is fine. Only row 1 violates.
    data = tmp_path / "bad.csv"
    data.write_text("id,age\n1,200\n2,45\n")
    return data


def test_entrypoint_wired(tmp_path: Path) -> None:
    """`pyproject` maps the script AND `main([...])` returns an int end-to-end."""
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    scripts = pyproject["project"]["scripts"]
    assert scripts.get("schemacheck") == "schemacheck.cli:main", scripts

    schema = _write_schema(tmp_path)
    data = _write_valid_csv(tmp_path)
    rc = main(["validate", str(data), "--schema", str(schema)])
    assert isinstance(rc, int), f"main must return an int exit code, got {rc!r}"
    assert rc == 0, f"valid data must exit 0, got {rc}"


def test_unsupported_extension(tmp_path: Path, capsys) -> None:
    """An unsupported data-file extension exits 2 and names the extension."""
    schema = _write_schema(tmp_path)
    data = tmp_path / "data.txt"
    data.write_text("id,age\n1,30\n")

    rc = main(["validate", str(data), "--schema", str(schema)])
    assert rc == 2, f"unsupported extension must exit 2, got {rc}"
    err = capsys.readouterr().err
    assert ".txt" in err, f"stderr must name the offending extension, got: {err!r}"


def test_report_lines(tmp_path: Path, capsys) -> None:
    """A real bad row prints a `row N, field '...'` line naming the reason."""
    schema = _write_schema(tmp_path)
    data = _write_invalid_csv(tmp_path)

    rc = main(["validate", str(data), "--schema", str(schema)])
    assert rc == 1, f"violations must exit 1, got {rc}"
    out = capsys.readouterr().out
    assert "row 1, field 'age'" in out, f"report must locate the violation, got: {out!r}"
    # The reason (the failed constraint) must be rendered, not just the location.
    assert "120" in out, f"report must name the failed constraint/value, got: {out!r}"


def test_end_to_end_exit_codes(tmp_path: Path, capsys) -> None:
    """Valid file -> 0 + success message; invalid file -> 1 + violation text."""
    schema = _write_schema(tmp_path)

    good = _write_valid_csv(tmp_path)
    rc_good = main(["validate", str(good), "--schema", str(schema)])
    out_good = capsys.readouterr().out
    assert rc_good == 0, f"valid CSV must exit 0, got {rc_good}"
    assert "valid" in out_good.lower(), f"success message expected, got: {out_good!r}"

    bad = _write_invalid_csv(tmp_path)
    rc_bad = main(["validate", str(bad), "--schema", str(schema)])
    out_bad = capsys.readouterr().out
    assert rc_bad == 1, f"invalid CSV must exit 1, got {rc_bad}"
    assert "field 'age'" in out_bad, f"violation text expected in stdout, got: {out_bad!r}"


def test_missing_inputs_usage_error(tmp_path: Path, capsys) -> None:
    """A missing data file OR a missing schema exits 2 without a traceback."""
    schema = _write_schema(tmp_path)
    data = _write_valid_csv(tmp_path)

    # Case 1: data file does not exist.
    rc_missing_data = main(
        ["validate", str(tmp_path / "nope.csv"), "--schema", str(schema)]
    )
    assert rc_missing_data == 2, f"missing data file must exit 2, got {rc_missing_data}"

    # Case 2: schema file does not exist.
    rc_missing_schema = main(
        ["validate", str(data), "--schema", str(tmp_path / "nope.yaml")]
    )
    assert rc_missing_schema == 2, f"missing schema must exit 2, got {rc_missing_schema}"

    err = capsys.readouterr().err
    assert "Traceback" not in err, f"must not leak a traceback, got: {err!r}"


def test_malformed_schema_usage_error(tmp_path: Path, capsys) -> None:
    """A malformed schema (SchemaError) exits 2 with a clear message, no traceback."""
    schema = tmp_path / "bad_schema.yaml"
    # 'fields' must be a list; a scalar makes load_schema raise SchemaError.
    schema.write_text("fields: 42\n")
    data = _write_valid_csv(tmp_path)

    rc = main(["validate", str(data), "--schema", str(schema)])
    assert rc == 2, f"malformed schema must exit 2, got {rc}"
    err = capsys.readouterr().err
    assert "Traceback" not in err, f"must not leak a traceback, got: {err!r}"
    assert err.strip(), "must print a diagnostic message for a malformed schema"
