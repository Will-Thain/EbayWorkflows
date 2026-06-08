# Labeled crop fixtures

Golden crop images for regression-testing card recognition (Phase 5/6 strict gate).

## Layout

- `manifest.example.json` — sample entries (no binary images required for CI)
- `manifest.schema.json` — JSON Schema for manifest rows
- `examples/` — optional PNG/JPG crops referenced by manifest `path`

## Manifest row fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Stable fixture id |
| `path` | yes | Relative path under this directory |
| `expected_set` | no | Expected Scryfall set code |
| `expected_collector` | no | Expected collector number |
| `expected_name` | no | Expected card name substring |
| `verify_expect` | yes | `pass` or `fail` — whether strict gate should verify |
| `notes` | no | Operator context |

Add real crop PNGs under `examples/` as you curate failures from production runs.
