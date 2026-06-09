# Packages

The card recognition library is **not** vendored in this repo.

| Package | Location |
|---------|----------|
| **mtg-card-recognition** | Sibling clone: [`../mtg-card-recognition`](https://github.com/Will-Thain/mtg-card-recognition) |

`pyproject.toml` pins `mtg-card-recognition` from GitHub for CI and fresh installs. Local development should still use the sibling editable clone via `install-dev.ps1` (sibling install wins over the git pin when both are present).

Install the sibling clone first, then this repo:

Clone next to this repo if you have not already:

```powershell
cd d:\
git clone https://github.com/Will-Thain/mtg-card-recognition.git
cd EbayWorkflows
.\scripts\install-dev.ps1
```

`install-dev.ps1` runs `pip install -e ../mtg-card-recognition` then `pip install -e ".[dev]"` so Python loads **one editable copy** from the sibling clone (not a wheel copy in site-packages).

Develop recognition features in `mtg-card-recognition` only; push there, then rerun tests in both repos.
