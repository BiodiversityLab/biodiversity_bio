#!/usr/bin/env python3
"""Refresh site metadata in-place for static hosting.

This script:
1. optionally rebuilds a Swedish red-list lookup from data/Rodlistearbete_2025_alla_filer.xlsx
2. scans species_sheets/*.json
3. injects sensible defaults (including Tobias Andermann as the default name)
4. auto-links matching images from img/ using the slug prefix
5. rebuilds species_sheets/index.json

Run it locally after adding or editing species sheets:
    python scripts/build_site_data.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

try:
    import openpyxl
except Exception:
    openpyxl = None

ROOT = Path(__file__).resolve().parents[1]
SPECIES_DIR = ROOT / "species_sheets"
IMG_DIR = ROOT / "img"
DATA_DIR = ROOT / "data"
REDLIST_XLSX = DATA_DIR / "Rodlistearbete_2025_alla_filer.xlsx"
REDLIST_JSON = DATA_DIR / "swedish_redlist_2025_index.json"
DEFAULT_PERSON_NAME = "Tobias Andermann"
SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return value or "species"


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_redlist_lookup() -> Dict[str, Dict[str, Any]]:
    if openpyxl is None or not REDLIST_XLSX.exists():
        if REDLIST_JSON.exists():
            return load_json(REDLIST_JSON)
        return {}

    workbook = openpyxl.load_workbook(REDLIST_XLSX, read_only=True, data_only=True)
    sheet = workbook["1. Rödlistearbete_2025"]
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    index = {name: i for i, name in enumerate(header)}

    def cell(row, name):
        pos = index.get(name)
        if pos is None:
            return None
        return row[pos]

    lookup: Dict[str, Dict[str, Any]] = {}
    for row in rows[1:]:
        scientific_name = cell(row, "Vetenskapligt namn")
        if not scientific_name:
            continue
        scientific_name = str(scientific_name).strip()
        if not scientific_name:
            continue
        taxon_id = cell(row, "TaxonId")
        lookup[scientific_name] = {
            "taxonId": int(taxon_id) if taxon_id is not None else None,
            "scientificName": scientific_name,
            "swedishName": cell(row, "Svenskt namn"),
            "category": cell(row, "Kategori"),
            "criterion": cell(row, "Kriterium"),
            "documentation": cell(row, "Kriteriedokumentation"),
            "swedishOccurrence": cell(row, "Svensk_förekomst"),
            "immigrationHistory": cell(row, "Invandringshistoria"),
            "kingdom": cell(row, "Rike"),
            "phylum": cell(row, "Fylum"),
            "class": cell(row, "Klass"),
            "order": cell(row, "Ordning"),
            "family": cell(row, "Familj"),
            "genus": cell(row, "Släkte"),
            "organismGroup1": cell(row, "Organismgrupp1"),
            "organismGroup2": cell(row, "Organismgrupp2"),
        }
    save_json(REDLIST_JSON, lookup)
    return lookup


def match_images(slug: str) -> List[str]:
    matches = []
    for path in sorted(IMG_DIR.iterdir()):
        if path.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
            continue
        if path.stem.startswith(slug):
            matches.append(f"img/{path.name}")
    return matches


def ensure_media(sheet: Dict[str, Any], slug: str) -> None:
    media = sheet.get("media")
    matched = match_images(slug)
    if not matched:
        return

    existing_files = set()
    if isinstance(media, list):
        for item in media:
            if isinstance(item, dict) and item.get("file"):
                existing_files.add(item["file"])
    else:
        media = []
        sheet["media"] = media

    for image_path in matched:
        if image_path in existing_files:
            continue
        media.append(
            {
                "file": image_path,
                "caption": "",
                "credit": None,
                "photographer": None,
                "capturedAt": {
                    "date": "",
                    "time": "",
                    "localityName": "",
                    "decimalLatitude": None,
                    "decimalLongitude": None,
                },
            }
        )


def first_common_name(names: Any) -> str | None:
    if isinstance(names, list) and names:
        return str(names[0])
    if isinstance(names, str) and names.strip():
        return names.strip()
    return None


def ensure_defaults(sheet: Dict[str, Any], redlist_lookup: Dict[str, Dict[str, Any]]) -> None:
    sheet.setdefault("schemaVersion", "1.3.0")
    defaults = sheet.setdefault("defaults", {})
    defaults.setdefault("personName", DEFAULT_PERSON_NAME)
    defaults.setdefault("country", "Sweden")
    defaults.setdefault("language", "en")

    identity = sheet.setdefault("identity", {})
    scientific_name = identity.get("scientificName") or sheet.get("scientificName")
    if scientific_name:
        scientific_name = str(scientific_name).strip()
        identity["scientificName"] = scientific_name

    slug = identity.get("slug")
    if not slug:
        slug = slugify(scientific_name or "species")
        identity["slug"] = slug

    common_names = identity.setdefault("commonNames", {})
    english_name = first_common_name(common_names.get("en"))
    if english_name and not identity.get("mainName"):
        identity["mainName"] = english_name

    byline = sheet.setdefault("byline", {})
    byline.setdefault("pageAuthor", None)
    byline.setdefault("observer", None)
    byline.setdefault("photographer", None)

    field_record = sheet.setdefault("fieldRecord", {})
    field_record.setdefault("observer", None)
    field_record.setdefault("date", "")
    field_record.setdefault("time", "")
    field_record.setdefault("localityName", "")
    field_record.setdefault("municipality", "")
    field_record.setdefault("county", "")
    field_record.setdefault("country", defaults.get("country", "Sweden"))
    field_record.setdefault("decimalLatitude", None)
    field_record.setdefault("decimalLongitude", None)
    field_record.setdefault("coordinateUncertaintyMeters", None)
    field_record.setdefault("habitatNote", "")
    field_record.setdefault("observationNote", "")

    if scientific_name and scientific_name in redlist_lookup:
        rl = redlist_lookup[scientific_name]
        swedish = sheet.setdefault("swedishContext", {})
        redlist = swedish.setdefault("redList2025", {})
        redlist.setdefault("category", rl.get("category"))
        redlist.setdefault("criterion", rl.get("criterion"))
        redlist.setdefault("taxonId", rl.get("taxonId"))
        redlist.setdefault("swedishOccurrence", rl.get("swedishOccurrence"))
        redlist.setdefault("immigrationHistory", rl.get("immigrationHistory"))
        redlist.setdefault("documentation", rl.get("documentation"))

        identity_common = identity.setdefault("commonNames", {})
        identity_common.setdefault("sv", [])
        if rl.get("swedishName"):
            if isinstance(identity_common["sv"], list):
                if rl["swedishName"] not in identity_common["sv"]:
                    identity_common["sv"].insert(0, rl["swedishName"])
            elif not identity_common["sv"]:
                identity_common["sv"] = [rl["swedishName"]]

        taxonomy = sheet.setdefault("taxonomy", {})
        classification = taxonomy.setdefault("classification", {})
        for rank in ("kingdom", "phylum", "class", "order", "family", "genus"):
            if rl.get(rank) and not classification.get(rank):
                classification[rank] = rl[rank]

        taxon_id = rl.get("taxonId")
        artfakta = swedish.setdefault("artfakta", {})
        if taxon_id and not artfakta.get("url"):
            slug_fragment = scientific_name.lower().replace(" ", "-")
            artfakta["url"] = f"https://artfakta.se/naturvard/taxon/{slug_fragment}-{taxon_id}/"
            artfakta.setdefault("fallbackUrl", f"https://artfakta.se/artbestamning/taxon/{slug_fragment}-{taxon_id}")
            artfakta.setdefault("citation", f"SLU Artdatabanken. Artfakta: {rl.get('swedishName') or scientific_name}.")
            artfakta.setdefault("note", "Use Artfakta as the main Swedish species-information source when refreshing this page locally.")

    ensure_media(sheet, slug)


def build_index() -> Dict[str, Any]:
    redlist_lookup = build_redlist_lookup()
    entries: List[Dict[str, Any]] = []

    for sheet_path in sorted(SPECIES_DIR.glob("*.json")):
        if sheet_path.name == "index.json":
            continue
        sheet = load_json(sheet_path)
        ensure_defaults(sheet, redlist_lookup)
        save_json(sheet_path, sheet)

        identity = sheet["identity"]
        media = sheet.get("media") or []
        hero_image = None
        if media and isinstance(media[0], dict):
            hero_image = media[0].get("file")
        common_names = identity.get("commonNames", {})
        entries.append(
            {
                "slug": identity["slug"],
                "file": sheet_path.name,
                "mainName": identity.get("mainName") or identity.get("scientificName"),
                "scientificName": identity.get("scientificName"),
                "swedishName": first_common_name(common_names.get("sv")),
                "heroImage": hero_image,
                "defaultPersonName": sheet.get("defaults", {}).get("personName", DEFAULT_PERSON_NAME),
                "group": sheet.get("taxonomy", {}).get("classification", {}).get("kingdom"),
            }
        )

    payload = {
        "generatedBy": "scripts/build_site_data.py",
        "generatedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "count": len(entries),
        "species": entries,
    }
    save_json(SPECIES_DIR / "index.json", payload)
    return payload


if __name__ == "__main__":
    index = build_index()
    print(f"Built species_sheets/index.json with {index['count']} species.")
