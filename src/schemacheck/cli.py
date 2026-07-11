"""Command-line entry point for schemacheck.

This is the thin shell the sprint goal delivers: ``schemacheck validate <file>
--schema <schema.yaml>``. It wires the three separable core layers together and
translates their result into a Unix-correct exit code — nothing more. Parsing,
loading and validation live in :mod:`schemacheck.schema`,
:mod:`schemacheck.loaders` and :mod:`schemacheck.validate`; the CLI never
reimplements any of them.

Exit codes (the contract CI and shell pipelines branch on):

- ``0`` — the data satisfies the schema.
- ``1`` — the data was checked and violations were found.
- ``2`` — a usage / input error: an unreadable or missing file, a malformed or
  unsupported schema, or an unsupported data-file extension. The data was never
  actually validated, so this is deliberately distinct from ``1``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from schemacheck.json_schema import load_json_schema
from schemacheck.loaders import LoaderError, load_records
from schemacheck.schema import Schema, SchemaError, load_schema
from schemacheck.validate import Violation, validate

# Exit codes, named so the mapping is explicit at every return site.
EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_USAGE = 2

# Data-file extensions the loader understands. Kept here so an unsupported
# extension is caught as a clear usage error BEFORE we try to read the file,
# rather than surfacing as a lower-level LoaderError.
SUPPORTED_EXTENSIONS = frozenset({".csv", ".json"})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schemacheck",
        description="Validate a CSV or JSON data file against a YAML schema.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate_cmd = sub.add_parser(
        "validate",
        help="Validate a data file against a schema and exit non-zero on failure.",
    )
    validate_cmd.add_argument("file", help="Path to the CSV or JSON data file.")
    validate_cmd.add_argument(
        "--schema",
        required=True,
        metavar="SCHEMA",
        help=(
            "Path to the schema definition. A '.json' file is read as a JSON "
            "Schema (draft 2020-12); '.yaml'/'.yml' as the YAML format."
        ),
    )
    return parser


def _load_schema_by_extension(schema_path: str) -> Schema:
    """Dispatch to the schema parser chosen by the ``--schema`` file extension.

    ``.json`` selects the JSON Schema (draft 2020-12) parser; ``.yaml``/``.yml``
    — and any other extension, for backward compatibility — selects the YAML
    parser. Both parsers return the same :class:`~schemacheck.schema.Schema`
    model and raise :class:`~schemacheck.schema.SchemaError` on a bad document,
    so the caller's error handling is identical either way. The data-file
    loader is independent of this choice.
    """
    if Path(schema_path).suffix.lower() == ".json":
        return load_json_schema(schema_path)
    return load_schema(schema_path)


def _render_report(violations: list[Violation]) -> str:
    """Render violations as a human-readable report.

    One line per violation naming the row, the field and the reason, followed by
    a summary count. The row/field prefix is the location the vision demands so a
    reader can jump straight to the offending cell.
    """
    lines = [
        f"row {v.row}, field '{v.field}': {v.message}" for v in violations
    ]
    count = len(violations)
    plural = "" if count == 1 else "s"
    lines.append(f"{count} violation{plural} found")
    return "\n".join(lines)


def _validate(file: str, schema_path: str) -> int:
    """Run the whole path for one ``validate`` invocation; return an exit code."""
    data_path = Path(file)

    suffix = data_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        print(
            f"error: unsupported data file extension {suffix!r} for {file!r}; "
            f"expected one of {sorted(SUPPORTED_EXTENSIONS)}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    # Parse the schema first: a malformed or unreadable schema is a usage error,
    # and there is no point reading data we cannot check.
    try:
        schema = _load_schema_by_extension(schema_path)
    except FileNotFoundError:
        print(f"error: schema file not found: {schema_path!r}", file=sys.stderr)
        return EXIT_USAGE
    except SchemaError as exc:
        print(f"error: malformed schema {schema_path!r}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"error: could not read schema {schema_path!r}: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        records = load_records(data_path)
    except FileNotFoundError:
        print(f"error: data file not found: {file!r}", file=sys.stderr)
        return EXIT_USAGE
    except LoaderError as exc:
        print(f"error: could not read data file {file!r}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"error: could not read data file {file!r}: {exc}", file=sys.stderr)
        return EXIT_USAGE

    violations = validate(records, schema)

    if not violations:
        print(f"{file}: valid ({len(records)} record(s) checked)")
        return EXIT_OK

    print(_render_report(violations))
    return EXIT_VIOLATIONS


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code (also testable in-process).

    ``argv`` defaults to ``sys.argv[1:]`` when ``None`` so the ``[project.scripts]``
    console-script wrapper can call ``main()`` with no arguments.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits 2 on a usage error; normalise to our int-returning
        # contract so callers (and tests) get a code instead of a raised exit.
        return EXIT_USAGE if exc.code else EXIT_OK

    if args.command == "validate":
        return _validate(args.file, args.schema)

    # argparse's `required=True` subparser guarantees we never fall through, but
    # be explicit rather than returning None.
    parser.print_usage(sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover - exercised via the console script
    raise SystemExit(main())
