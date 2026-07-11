"""Data-loading layer for schemacheck.

Reads a CSV or JSON data file into a uniform ``list[dict]`` shape that the
validation engine consumes. The file format is chosen by extension:

- ``.csv`` — parsed with :class:`csv.DictReader`; every value is a ``str``.
- ``.json`` — parsed with :func:`json.load`; the document must be either a
  top-level array of objects, or a single object (wrapped into a 1-element
  list).

The validation engine is responsible for type coercion; this layer only
turns bytes on disk into records.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

__all__ = ["load_records", "LoaderError"]


class LoaderError(Exception):
    """Raised when a data file cannot be read or has an unexpected shape."""


def load_records(path: str | Path) -> list[dict]:
    """Load ``path`` into a list of record dicts.

    Dispatches on the file extension. Raises :class:`LoaderError` for an
    unsupported extension or a JSON document that is neither an object nor an
    array of objects.
    """
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix == ".csv":
        return _load_csv(p)
    if suffix == ".json":
        return _load_json(p)
    raise LoaderError(
        f"unsupported data file extension {suffix!r}; expected .csv or .json"
    )


def _load_csv(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        # DictReader yields OrderedDict-like rows; normalise to plain dict so
        # equality comparisons in tests and downstream code are predictable.
        return [dict(row) for row in reader]


def _load_json(path: Path) -> list[dict]:
    document = json.loads(path.read_text())

    if isinstance(document, dict):
        return [document]
    if isinstance(document, list):
        for i, item in enumerate(document):
            if not isinstance(item, dict):
                raise LoaderError(
                    f"JSON array element #{i} must be an object, "
                    f"got {type(item).__name__}"
                )
        return document
    raise LoaderError(
        f"JSON root must be an object or an array of objects, "
        f"got {type(document).__name__}"
    )
