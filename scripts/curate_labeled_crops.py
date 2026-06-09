"""Curate labeled crop fixtures from production cache + Postgres evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
MTG_ROOT = ROOT.parent / "mtg-card-recognition"
FIXTURE_ROOT = MTG_ROOT / "tests" / "fixtures" / "labeled_crops"
EXAMPLES = FIXTURE_ROOT / "examples"
ZONE_SUFFIXES = ("bottom", "name", "type_line", "set_symbol", "mana_cost", "art")


@dataclass(slots=True)
class CropCase:
    id: str
    category: str
    region_path: str
    listing_image_path: str | None
    zone_paths: dict[str, str]
    title: str | None
    source_method: str | None
    image_verified: bool
    expected_set: str | None
    expected_collector: str | None
    expected_name: str | None
    verify_expect: str
    align_confidence: float | None = None
    name_ocr: str | None = None
    type_line_ocr: str | None = None
    bottom_parsed: dict[str, Any] | None = None
    set_symbol_match: dict[str, Any] | None = None
    mana_cost: dict[str, Any] | None = None
    faiss_top: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""


def _db_url() -> str:
    load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def zone_stem_for_region(region_file: Path) -> str:
    return hashlib.sha256(region_file.read_bytes()).hexdigest()[:16]


def find_zone_paths(region_file: Path, zone_dir: Path) -> dict[str, str]:
    stem = zone_stem_for_region(region_file)
    found: dict[str, str] = {}
    for suffix in ZONE_SUFFIXES:
        candidate = zone_dir / f"{stem}_{suffix}.jpg"
        if candidate.is_file():
            found[suffix] = str(candidate.relative_to(ROOT)).replace("\\", "/")
    aligned = zone_dir / "aligned" / f"{stem}_aligned.jpg"
    if aligned.is_file():
        found["aligned"] = str(aligned.relative_to(ROOT)).replace("\\", "/")
    return found


def copy_case_assets(case_id: str, region: Path, listing: Path | None, zones: dict[str, str]) -> dict[str, str]:
    dest_dir = EXAMPLES / case_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}

    region_dest = dest_dir / "region.jpg"
    shutil.copy2(region, region_dest)
    out["region"] = str(region_dest.relative_to(FIXTURE_ROOT)).replace("\\", "/")

    if listing and listing.is_file():
        listing_dest = dest_dir / "listing.jpg"
        shutil.copy2(listing, listing_dest)
        out["listing"] = str(listing_dest.relative_to(FIXTURE_ROOT)).replace("\\", "/")

    for suffix, src_rel in zones.items():
        src = ROOT / src_rel.replace("/", os.sep)
        if not src.is_file():
            continue
        zone_dest = dest_dir / f"{suffix}.jpg"
        shutil.copy2(src, zone_dest)
        out[suffix] = str(zone_dest.relative_to(FIXTURE_ROOT)).replace("\\", "/")

    return out


def fetch_verified_cases(engine) -> list[CropCase]:
    query = text(
        """
        SELECT lcc.source_method, lcc.evidence_json, l.title,
               sc.name, sc.set_code, sc.collector_number,
               li.local_path AS listing_image
        FROM listing_card_candidates lcc
        JOIN listings l ON l.id = lcc.listing_id
        LEFT JOIN scryfall_cards sc ON sc.id = lcc.scryfall_id
        LEFT JOIN listing_images li ON li.id::text = lcc.evidence_json->>'verification_listing_image_id'
        WHERE lcc.evidence_json->>'image_verified' = 'true'
        """
    )
    cases: list[CropCase] = []
    with engine.connect() as conn:
        rows = conn.execute(query).mappings().all()
    for index, row in enumerate(rows, start=1):
        evidence = row["evidence_json"] or {}
        zone = evidence.get("zone_evidence") or {}
        region_rel = zone.get("region_image_path") or evidence.get("verification_region_path")
        if not region_rel:
            continue
        region = ROOT / str(region_rel).replace("\\", "/")
        if not region.is_file():
            continue
        zone_dir = ROOT / ".cache" / "images" / "crops" / "zones"
        zones = find_zone_paths(region, zone_dir)
        for key, path in list(zones.items()):
            if key in zone and isinstance(zone[key], str):
                zones[key] = zone[key]
        faiss = evidence.get("faiss_matches") or []
        cases.append(
            CropCase(
                id=f"verified-{index:02d}-{row['set_code'] or 'unk'}",
                category="verified_production",
                region_path=str(region.relative_to(ROOT)).replace("\\", "/"),
                listing_image_path=(ROOT / row["listing_image"]).relative_to(ROOT).as_posix()
                if row.get("listing_image") and (ROOT / row["listing_image"]).is_file()
                else None,
                zone_paths=zones,
                title=row["title"],
                source_method=row["source_method"],
                image_verified=True,
                expected_set=row["set_code"],
                expected_collector=str(row["collector_number"]) if row["collector_number"] else None,
                expected_name=row["name"],
                verify_expect="pass",
                align_confidence=float(zone.get("align_confidence")) if zone.get("align_confidence") is not None else None,
                name_ocr=zone.get("name_ocr"),
                type_line_ocr=zone.get("type_line_ocr"),
                bottom_parsed=zone.get("bottom_parsed"),
                set_symbol_match=zone.get("set_symbol_match"),
                mana_cost=zone.get("mana_cost"),
                faiss_top=faiss[:5],
                notes=(
                    f"Production verified via {evidence.get('image_verification_source')}; "
                    f"name_ocr={zone.get('name_ocr')!r}; bulk lot listing."
                ),
            )
        )
    return cases


def fetch_title_match_singles(engine, limit: int) -> list[CropCase]:
    query = text(
        """
        SELECT l.title, sc.name, sc.set_code, sc.collector_number,
               lcc.source_method, lcc.evidence_json, li.local_path
        FROM listing_card_candidates lcc
        JOIN listings l ON l.id = lcc.listing_id
        JOIN scryfall_cards sc ON sc.id = lcc.scryfall_id
        JOIN listing_images li ON li.listing_id = l.id
        WHERE lcc.source_method = 'title_match'
          AND lcc.rank_position = 1
          AND COALESCE(lcc.evidence_json->>'image_verified', 'false') = 'false'
          AND l.title NOT ILIKE '%lot%'
          AND l.title NOT ILIKE '%bulk%'
          AND li.local_path IS NOT NULL
        ORDER BY lcc.match_score DESC
        LIMIT :limit
        """
    )
    cases: list[CropCase] = []
    crop_dir = ROOT / ".cache" / "images" / "crops"
    zone_dir = crop_dir / "zones"
    with engine.connect() as conn:
        rows = conn.execute(query, {"limit": limit * 3}).mappings().all()
    seen_listings: set[str] = set()
    for row in rows:
        listing_path = ROOT / str(row["local_path"]).replace("\\", "/")
        if not listing_path.is_file() or row["title"] in seen_listings:
            continue
        regions = sorted(crop_dir.glob(f"{listing_path.stem[:16]}_*.jpg"))
        if not regions:
            # listing hash is full sha256; crop names use first 16 chars of listing file stem
            stem16 = listing_path.stem[:16]
            regions = sorted(crop_dir.glob(f"{stem16}_*.jpg"))
        if not regions:
            continue
        region = regions[0]
        zones = find_zone_paths(region, zone_dir)
        if not zones:
            continue
        seen_listings.add(row["title"])
        cases.append(
            CropCase(
                id=f"title-single-{len(cases) + 1:02d}",
                category="title_match_single",
                region_path=str(region.relative_to(ROOT)).replace("\\", "/"),
                listing_image_path=str(listing_path.relative_to(ROOT)).replace("\\", "/"),
                zone_paths=zones,
                title=row["title"],
                source_method=row["source_method"],
                image_verified=False,
                expected_set=row["set_code"],
                expected_collector=str(row["collector_number"]) if row["collector_number"] else None,
                expected_name=row["name"],
                verify_expect="fail",
                notes="Title match only; strict gate should not verify without zone evidence.",
            )
        )
        if len(cases) >= limit:
            break
    return cases


def sample_filesystem_cases(limit: int) -> list[CropCase]:
    crop_dir = ROOT / ".cache" / "images" / "crops"
    zone_dir = crop_dir / "zones"
    cases: list[CropCase] = []
    categories = [
        ("bulk-multi-region", lambda z, r: "_1." in r.name or "_2." in r.name, "Bulk lot region; proposal cap stress"),
        ("has-bottom-zone", lambda z, r: "bottom" in z, "Bottom strip crop present"),
        ("has-symbol-zone", lambda z, r: "set_symbol" in z, "Set symbol zone present"),
        ("low-zone-count", lambda z, r: len(z) <= 2, "Degraded / partial zones"),
        ("rich-zones", lambda z, r: len(z) >= 5, "Full modern zone set"),
    ]
    seen_stems: set[str] = set()
    for region in sorted(crop_dir.glob("*_*.jpg")):
        if region.parent.name == "zones":
            continue
        stem = zone_stem_for_region(region)
        if stem in seen_stems:
            continue
        zones = find_zone_paths(region, zone_dir)
        if not zones:
            continue
        seen_stems.add(stem)
        for cat_id, predicate, note in categories:
            if len([c for c in cases if c.category == cat_id]) >= limit // len(categories) + 2:
                continue
            if not predicate(zones, region):
                continue
            cases.append(
                CropCase(
                    id=f"fs-{cat_id}-{len(cases) + 1:03d}",
                    category=cat_id,
                    region_path=str(region.relative_to(ROOT)).replace("\\", "/"),
                    listing_image_path=None,
                    zone_paths=zones,
                    title=None,
                    source_method=None,
                    image_verified=False,
                    expected_set=None,
                    expected_collector=None,
                    expected_name=None,
                    verify_expect="fail",
                    notes=f"Filesystem sample: {note}. No ground-truth printing label.",
                )
            )
            break
        if len(cases) >= limit:
            break
    return cases


def fetch_high_proposal_listings(engine, per_listing: int, max_listings: int) -> list[CropCase]:
    query = text(
        """
        SELECT l.id, l.title, COUNT(lcc.id) AS proposal_count
        FROM listings l
        JOIN listing_card_candidates lcc ON lcc.listing_id = l.id
        GROUP BY l.id, l.title
        HAVING COUNT(lcc.id) >= 30
        ORDER BY COUNT(lcc.id) DESC
        LIMIT :max_listings
        """
    )
    cases: list[CropCase] = []
    crop_dir = ROOT / ".cache" / "images" / "crops"
    zone_dir = crop_dir / "zones"
    with engine.connect() as conn:
        listings = conn.execute(query, {"max_listings": max_listings}).mappings().all()
        for listing in listings:
            images = conn.execute(
                text(
                    """
                    SELECT local_path FROM listing_images
                    WHERE listing_id = :lid AND local_path IS NOT NULL
                    LIMIT 3
                    """
                ),
                {"lid": listing["id"]},
            ).scalars().all()
            added = 0
            for image_path in images:
                path = ROOT / str(image_path).replace("\\", "/")
                if not path.is_file():
                    continue
                stem16 = path.stem[:16]
                for region in sorted(crop_dir.glob(f"{stem16}_*.jpg"))[:2]:
                    zones = find_zone_paths(region, zone_dir)
                    cases.append(
                        CropCase(
                            id=f"proposal-heavy-{len(cases) + 1:03d}",
                            category="high_proposal_listing",
                            region_path=str(region.relative_to(ROOT)).replace("\\", "/"),
                            listing_image_path=str(path.relative_to(ROOT)).replace("\\", "/"),
                            zone_paths=zones,
                            title=listing["title"],
                            source_method="faiss_proposal",
                            image_verified=False,
                            expected_set=None,
                            expected_collector=None,
                            expected_name=None,
                            verify_expect="fail",
                            notes=(
                                f"Listing has {listing['proposal_count']} candidates; "
                                "panel v2 caps (≤2/region, ≤5/listing) apply here."
                            ),
                        )
                    )
                    added += 1
                    if added >= per_listing:
                        break
                if added >= per_listing:
                    break
    return cases


def build_manifest(cases: list[CropCase], asset_map: dict[str, dict[str, str]]) -> dict[str, Any]:
    entries = []
    for case in cases:
        assets = asset_map[case.id]
        entry: dict[str, Any] = {
            "id": case.id,
            "path": assets["region"],
            "verify_expect": case.verify_expect,
        }
        if case.expected_set:
            entry["expected_set"] = case.expected_set
        if case.expected_collector:
            entry["expected_collector"] = case.expected_collector
        if case.expected_name:
            entry["expected_name"] = case.expected_name
        entry["notes"] = case.notes
        entries.append(entry)
    return {"version": 1, "entries": entries}


def build_cases_json(cases: list[CropCase], asset_map: dict[str, dict[str, str]]) -> dict[str, Any]:
    return {
        "version": 1,
        "source": "scripts/curate_labeled_crops.py",
        "case_count": len(cases),
        "cases": [
            {
                **asdict(case),
                "assets": asset_map[case.id],
            }
            for case in cases
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Curate labeled crop fixtures from production data.")
    parser.add_argument("--fs-limit", type=int, default=25, help="Max filesystem-sampled regions")
    parser.add_argument("--title-limit", type=int, default=8, help="Max title-match single-card cases")
    parser.add_argument("--proposal-listings", type=int, default=6, help="Max high-proposal listings")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not (MTG_ROOT / "pyproject.toml").is_file():
        raise SystemExit(
            f"Expected mtg-card-recognition clone at {MTG_ROOT} — "
            "git clone https://github.com/Will-Thain/mtg-card-recognition.git"
        )
    FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)

    engine = create_engine(_db_url())
    cases: list[CropCase] = []
    cases.extend(fetch_verified_cases(engine))
    cases.extend(fetch_title_match_singles(engine, args.title_limit))
    cases.extend(fetch_high_proposal_listings(engine, per_listing=2, max_listings=args.proposal_listings))
    cases.extend(sample_filesystem_cases(args.fs_limit))

    # Dedupe by region path
    seen_regions: set[str] = set()
    unique: list[CropCase] = []
    for case in cases:
        if case.region_path in seen_regions:
            continue
        seen_regions.add(case.region_path)
        unique.append(case)
    cases = unique[:50]

    asset_map: dict[str, dict[str, str]] = {}
    if not args.dry_run:
        if EXAMPLES.exists():
            for child in EXAMPLES.iterdir():
                if child.is_dir() and child.name not in {"minimal.png"}:
                    shutil.rmtree(child, ignore_errors=True)
        for case in cases:
            region = ROOT / case.region_path.replace("/", os.sep)
            listing = ROOT / case.listing_image_path.replace("/", os.sep) if case.listing_image_path else None
            asset_map[case.id] = copy_case_assets(case.id, region, listing, case.zone_paths)

    manifest = build_manifest(cases, asset_map or {c.id: {"region": c.region_path} for c in cases})
    cases_doc = build_cases_json(cases, asset_map or {c.id: {"region": c.region_path} for c in cases})

    FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = FIXTURE_ROOT / "manifest.json"
    cases_path = FIXTURE_ROOT / "cases.json"
    if not args.dry_run:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        cases_path.write_text(json.dumps(cases_doc, indent=2) + "\n", encoding="utf-8")

    print(f"Curated {len(cases)} cases")
    by_cat: dict[str, int] = {}
    for case in cases:
        by_cat[case.category] = by_cat.get(case.category, 0) + 1
    for cat, count in sorted(by_cat.items()):
        print(f"  {cat}: {count}")
    if not args.dry_run:
        print(f"Wrote {manifest_path}")
        print(f"Wrote {cases_path}")


if __name__ == "__main__":
    main()
