# Archived migration scripts

One-off helpers used during ADR 0002 (M1–M7) package restructure. **Not used at runtime.**

| Script | Purpose |
|--------|---------|
| `fix_migration_imports.py` | Bulk rewrite `services/` imports to new packages |
| `migrate_imports_m7.py` | M7 import pass after shim removal |
| `split_cli.py` | Split monolithic `cli.py` into `cli/` package |

Safe to delete after the restructure is committed on `main`.
