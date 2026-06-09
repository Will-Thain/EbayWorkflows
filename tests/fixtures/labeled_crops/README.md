# Labeled crop fixtures

**Canonical location:** [`../mtg-card-recognition/tests/fixtures/labeled_crops/`](../mtg-card-recognition/tests/fixtures/labeled_crops/)

Golden crop images for regression-testing the strict verification gate and panel v2 eval live in the recognition package repo only.

Curate from production:

```powershell
.\.venv\Scripts\python.exe scripts\curate_labeled_crops.py
```

Output is written to the sibling `mtg-card-recognition` clone. See `docs/adr/0003-eval-brief.md` in that repo (or the stub pointer in `docs/card-recognition-architecture.md`).
