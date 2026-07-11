# schemacheck

A small, sharp command-line validator: point it at a CSV or JSON data file and
a schema — in either YAML or JSON Schema — and it tells you, with a meaningful
exit code, whether the data conforms.

## Usage

```console
$ schemacheck validate DATA --schema SCHEMA
```

- `DATA` — a `.csv` or `.json` file. The format is chosen by extension.
- `--schema` — a schema definition. The format is chosen by extension:
  - `.json` → a **JSON Schema** document (draft 2020-12).
  - `.yaml` / `.yml` → the native **YAML** format.

  All four combinations of {CSV, JSON} data × {YAML, JSON Schema} schema work.

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

## Schema formats

schemacheck reads **two** schema formats. Both describe the same thing — a flat,
one-level set of fields — and are parsed into the same internal model, so they
stay at **constraint parity**: whatever one can express, the other can. The
format is selected by the `--schema` file extension:

- `.json` → **JSON Schema** (draft 2020-12).
- `.yaml` / `.yml` → the native **YAML** format.

The two are described side by side below with the same example, followed by one
shared constraints table.

### YAML format

The schema is a YAML mapping with a `fields` list. Each entry declares a `name`
(required), a `type` (required), an optional `required` flag (default `false`),
and an optional `constraints` mapping.

```yaml
fields:
  - name: id
    type: integer
    required: true
  - name: age
    type: integer
    constraints: { min: 0, max: 120 }
  - name: name
    type: string
    constraints: { minLength: 1, maxLength: 50 }
  - name: email
    type: string
    constraints: { regex: "^.+@.+$" }
  - name: color
    type: string
    constraints: { enum: [red, green, blue] }
```

### JSON Schema format (draft 2020-12)

A JSON Schema document with `"type": "object"` and a flat `properties` object.
Field requiredness comes from the root-level `required` array. The same schema
as above:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "id": { "type": "integer" },
    "age": { "type": "integer", "minimum": 0, "maximum": 120 },
    "name": { "type": "string", "minLength": 1, "maxLength": 50 },
    "email": { "type": "string", "pattern": "^.+@.+$" },
    "color": { "type": "string", "enum": ["red", "green", "blue"] }
  },
  "required": ["id"]
}
```

### Constraints (one set, both formats)

The formats express exactly the same constraints. This is the single set — there
is no second, divergent dialect:

| Constraint  | YAML key                | JSON Schema keyword   | Meaning                                     |
| ----------- | ----------------------- | --------------------- | ------------------------------------------- |
| type        | `type`                  | `type`                | `string` / `integer` / `number` / `boolean` |
| required    | `required: true`        | root `required` array | field must be present and non-empty         |
| enum        | `constraints.enum`      | `enum`                | value must be one of a list                 |
| numeric min | `constraints.min`       | `minimum`             | inclusive lower numeric bound               |
| numeric max | `constraints.max`       | `maximum`             | inclusive upper numeric bound               |
| min length  | `constraints.minLength` | `minLength`           | inclusive lower string-length bound         |
| max length  | `constraints.maxLength` | `maxLength`           | inclusive upper string-length bound         |
| pattern     | `constraints.regex`     | `pattern`             | regex the value must match                  |

### Errors in the schema are errors

An unknown type or constraint, a missing `name`, or the wrong root shape is a
malformed schema and exits `2` — a constraint you wrote is **never** silently
ignored, whichever format you use.

For JSON Schema specifically, the following are **out of scope and rejected
loudly** (exit `2`, naming the offending keyword) rather than ignored:

- `$ref` (and `$id` / `$defs`) — reference resolution.
- Remote schema fetching.
- The `allOf` / `anyOf` / `oneOf` / `not` combinators.
- Nested object/array schemas — the field set stays flat, one level.

Silently dropping a constraint you wrote — and then reporting "valid" on data
nobody actually checked — is the worst outcome this tool can produce, so it
refuses to run instead.

## Architecture

The core is a library; the CLI is a thin shell over it. The layers are
separable and pass a defined `Violation` object between them:

- `schemacheck.schema` — parse a YAML schema into a `Schema` model.
- `schemacheck.json_schema` — parse a JSON Schema document into the **same** `Schema` model (a second parser, not a second validation path).
- `schemacheck.loaders` — read a CSV or JSON file into records.
- `schemacheck.validate` — check records against the schema, emitting `Violation`s.
- `schemacheck.cli` — wire the above together and map the result to an exit code.
