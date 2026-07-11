# schemacheck

A small, sharp command-line validator: point it at a CSV or JSON data file and
a YAML schema, and it tells you — with a meaningful exit code — whether the data
conforms.

## Usage

```console
$ schemacheck validate DATA --schema SCHEMA.yaml
```

- `DATA` — a `.csv` or `.json` file. The format is chosen by extension.
- `--schema` — a YAML schema definition (see below).

### Exit codes

The contract every CI job and shell pipeline can branch on:

| Code | Meaning                                                                                                                                           |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `0`  | The data is valid.                                                                                                                                |
| `1`  | The data was checked and violations were found.                                                                                                   |
| `2`  | Usage / input error — missing or unreadable file, malformed or unsupported schema, unsupported data-file extension. The data was never validated. |

### Example

`people.yaml`:

```yaml
fields:
  - name: id
    type: integer
    required: true
  - name: age
    type: integer
    constraints: { min: 0, max: 120 }
  - name: email
    type: string
    constraints: { regex: "^.+@.+$" }
  - name: color
    type: string
    constraints: { enum: [red, green, blue] }
```

`people.csv`:

```csv
id,age,email,color
1,200,alice@example.com,red
```

```console
$ schemacheck validate people.csv --schema people.yaml
row 1, field 'age': value 200 exceeds the max 120
1 violation found
$ echo $?
1
```

Each violation line names the **row** (1-based), the **field**, and the
**reason** the value failed, so you can jump straight to the offending cell.

## Schema format

The schema is a YAML mapping with a `fields` list. Each entry declares:

- `name` — the field name (required).
- `type` — one of `string`, `integer`, `number`, `boolean` (required).
- `required` — `true` if the field must be present and non-empty (default `false`).
- `constraints` — an optional mapping of per-field rules:
  - `min` / `max` — numeric bounds (inclusive).
  - `minLength` / `maxLength` — string length bounds (inclusive).
  - `regex` — a pattern the value must match.
  - `enum` — a list of allowed values.

An unknown type or constraint, a missing `name`, or a non-mapping root is a
malformed schema and exits `2` — a constraint you wrote is never silently
ignored.

## Architecture

The core is a library; the CLI is a thin shell over it. The layers are
separable and pass a defined `Violation` object between them:

- `schemacheck.schema` — parse a YAML schema into a `Schema` model.
- `schemacheck.loaders` — read a CSV or JSON file into records.
- `schemacheck.validate` — check records against the schema, emitting `Violation`s.
- `schemacheck.cli` — wire the above together and map the result to an exit code.
