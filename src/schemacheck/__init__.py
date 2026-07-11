"""schemacheck — validate CSV/JSON data files against a YAML schema.

The public API is re-exported here so callers (the CLI slice, tests, and any
program importing the package) have one stable import surface:

.. code-block:: python

    from schemacheck import load_schema, load_records, validate

- :func:`load_schema` / :class:`Schema` / :class:`FieldSpec` / :class:`SchemaError`
  — the schema-definition layer (parse a YAML schema into a model).
- :func:`load_records` / :class:`LoaderError` — the data-loading layer
  (read a CSV or JSON file into a list of record dicts).
- :func:`validate` / :class:`Violation` — the validation engine (check records
  against a schema and emit structured violations).

Keeping the surface here means later slices import from ``schemacheck`` without
depending on the internal module layout.
"""

from schemacheck.loaders import LoaderError, load_records
from schemacheck.schema import FieldSpec, Schema, SchemaError, load_schema
from schemacheck.validate import Violation, validate

__all__ = [
    "FieldSpec",
    "LoaderError",
    "Schema",
    "SchemaError",
    "Violation",
    "load_records",
    "load_schema",
    "validate",
]
