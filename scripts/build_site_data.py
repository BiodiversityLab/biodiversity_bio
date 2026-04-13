#!/usr/bin/env python3
"""Refresh site metadata in-place for static hosting.

This script:
1. optionally rebuilds a Swedish red-list lookup from data/Rodlistearbete_2025_alla_filer.xlsx
2. scans species_sheets/*.json
3. injects sensible defaults (including Tobias Andermann as the default name)
4. auto-links matching images from img/ using the slug prefix and harvests EXIF date/GPS metadata when available
5. rebuilds species_sheets/index.json

Run it locally after adding or editing species sheets:
    python scripts/build_site_data.py
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import openpyxl
except Exception:
    openpyxl = None

try:
    from PIL import Image
    from PIL.ExifTags import IFD
except Exception:
    Image = None
    IFD = None

ROOT = Path(__file__).resolve().parents[1]
SPECIES_DIR = ROOT / "species_sheets"
IMG_DIR = ROOT / "img"
DATA_DIR = ROOT / "data"
REDLIST_XLSX = DATA_DIR / "Rodlistearbete_2025_alla_filer.xlsx"
REDLIST_JSON = DATA_DIR / "swedish_redlist_2025_index.json"
REVERSE_GEOCODE_JSON = DATA_DIR / "reverse_geocode_cache.json"
DEFAULT_PERSON_NAME = "Tobias Andermann"
SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_USER_AGENT = "biodiversity.bio-site-builder/1.0"


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


def load_optional_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}


def is_blank(value: Any) -> bool:
    return value is None or value == ""


def set_if_blank(mapping: Dict[str, Any], key: str, value: Any) -> None:
    if not is_blank(value) and is_blank(mapping.get(key)):
        mapping[key] = value


def first_non_blank(*values: Any) -> Any:
    for value in values:
        if not is_blank(value):
            return value
    return None


def unique_non_blank(values: List[Any]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        if is_blank(value):
            continue
        text = str(value).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def to_relative_image_path(path: Path) -> str:
    return f"img/{path.name}"


def media_image_path(item: Dict[str, Any]) -> str | None:
    for key in ("file", "src"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    filename = item.get("filename")
    if isinstance(filename, str) and filename:
        return f"img/{filename}"
    return None


def media_uses_legacy_shape(item: Dict[str, Any], sheet: Dict[str, Any]) -> bool:
    if any(key in item for key in ("src", "filename", "capturedAtDate", "coordinates")):
        return True
    schema_version = str(sheet.get("schemaVersion") or "")
    return schema_version.startswith("measure.bio/")


def dms_to_decimal(parts: Any, ref: Any) -> float | None:
    if not isinstance(parts, (tuple, list)) or len(parts) != 3:
        return None
    try:
        degrees = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
    if str(ref).upper() in {"S", "W"}:
        decimal *= -1
    return round(decimal, 6)


def parse_exif_datetime(raw_value: Any) -> tuple[str | None, str | None]:
    if not isinstance(raw_value, str):
        return None, None
    parts = raw_value.strip().split(" ", 1)
    date_part = parts[0].replace(":", "-") if parts else None
    time_part = parts[1] if len(parts) > 1 else None
    return date_part or None, time_part or None


def parse_gps_date(gps_info: Dict[Any, Any]) -> str | None:
    raw_value = gps_info.get(29)
    if not isinstance(raw_value, str):
        return None
    return raw_value.replace(":", "-")


def parse_gps_time(gps_info: Dict[Any, Any]) -> str | None:
    raw_value = gps_info.get(7)
    if not isinstance(raw_value, (tuple, list)) or len(raw_value) != 3:
        return None
    try:
        hours = int(float(raw_value[0]))
        minutes = int(float(raw_value[1]))
        seconds = int(round(float(raw_value[2])))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if seconds == 60:
        seconds = 59
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def extract_image_metadata(path: Path) -> Dict[str, Any]:
    payload = {
        "observedAtDate": None,
        "observedAtTime": None,
        "decimalLatitude": None,
        "decimalLongitude": None,
        "coordinateUncertaintyMeters": None,
    }
    if Image is None or IFD is None or not path.exists():
        return payload

    try:
        with Image.open(path) as image:
            exif = image.getexif()
    except Exception:
        return payload

    if not exif:
        return payload

    gps_info: Dict[Any, Any] = {}
    try:
        gps_info = exif.get_ifd(IFD.GPSInfo) or {}
    except Exception:
        gps_info = {}

    for tag_id in (36867, 306):
        if tag_id in exif:
            date_value, time_value = parse_exif_datetime(exif.get(tag_id))
            if date_value:
                payload["observedAtDate"] = date_value
            if time_value:
                payload["observedAtTime"] = time_value
            break

    gps_date = parse_gps_date(gps_info)
    gps_time = parse_gps_time(gps_info)
    if gps_date and payload["observedAtDate"] is None:
        payload["observedAtDate"] = gps_date
    if gps_time and payload["observedAtTime"] is None:
        payload["observedAtTime"] = gps_time

    latitude = dms_to_decimal(gps_info.get(2), gps_info.get(1))
    longitude = dms_to_decimal(gps_info.get(4), gps_info.get(3))
    if latitude is not None:
        payload["decimalLatitude"] = latitude
    if longitude is not None:
        payload["decimalLongitude"] = longitude

    positioning_error = gps_info.get(31)
    if positioning_error is not None:
        try:
            payload["coordinateUncertaintyMeters"] = round(float(positioning_error), 2)
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    return payload


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


def match_images(slug: str) -> List[Path]:
    matches = []
    for path in sorted(IMG_DIR.iterdir()):
        if path.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
            continue
        if path.stem.startswith(slug):
            matches.append(path)
    return matches


def ensure_field_record_defaults(field_record: Dict[str, Any], country: str) -> None:
    field_record.setdefault("observer", None)
    field_record.setdefault("date", "")
    field_record.setdefault("time", "")
    field_record.setdefault("observedAtDate", field_record.get("date") or "")
    field_record.setdefault("observedAtTime", field_record.get("time"))
    field_record.setdefault("siteName", field_record.get("localityName"))
    field_record.setdefault("locationLabel", None)
    field_record.setdefault("localityName", "")
    field_record.setdefault("municipality", "")
    field_record.setdefault("county", "")
    field_record.setdefault("country", country)
    field_record.setdefault("decimalLatitude", None)
    field_record.setdefault("decimalLongitude", None)
    field_record.setdefault("coordinateUncertaintyMeters", None)
    field_record.setdefault("samplingMethod", "Field photography")
    field_record.setdefault("habitatNote", "")
    field_record.setdefault("notes", "")
    field_record.setdefault("observationNote", "")

    if is_blank(field_record.get("observedAtDate")) and not is_blank(field_record.get("date")):
        field_record["observedAtDate"] = field_record.get("date")
    if is_blank(field_record.get("date")) and not is_blank(field_record.get("observedAtDate")):
        field_record["date"] = field_record.get("observedAtDate")
    if is_blank(field_record.get("observedAtTime")) and not is_blank(field_record.get("time")):
        field_record["observedAtTime"] = field_record.get("time")
    if is_blank(field_record.get("time")) and not is_blank(field_record.get("observedAtTime")):
        field_record["time"] = field_record.get("observedAtTime")


def merge_media_items(target: Dict[str, Any], incoming: Dict[str, Any], sheet: Dict[str, Any], country: str) -> None:
    legacy_shape = media_uses_legacy_shape(target, sheet)
    if legacy_shape:
        keys = ("src", "filename", "alt", "caption", "credit", "siteName", "locationLabel", "municipality", "county", "country", "notes")
    else:
        keys = ("file", "caption", "credit", "photographer", "country")
    for key in keys:
        set_if_blank(target, key, incoming.get(key))

    if "coordinates" in incoming or "coordinates" in target:
        coordinates = target.setdefault("coordinates", {"lat": None, "lon": None})
        incoming_coordinates = incoming.get("coordinates")
        if isinstance(incoming_coordinates, dict):
            set_if_blank(coordinates, "lat", incoming_coordinates.get("lat"))
            set_if_blank(coordinates, "lon", incoming_coordinates.get("lon"))

    if not legacy_shape and ("capturedAt" in incoming or "capturedAt" in target):
        captured_at = target.setdefault(
            "capturedAt",
            {
                "date": "",
                "time": "",
                "localityName": "",
                "decimalLatitude": None,
                "decimalLongitude": None,
            },
        )
        incoming_captured_at = incoming.get("capturedAt")
        if isinstance(incoming_captured_at, dict):
            for key in ("date", "time", "localityName", "decimalLatitude", "decimalLongitude"):
                set_if_blank(captured_at, key, incoming_captured_at.get(key))

    if "capturedAtDate" in incoming or "capturedAtDate" in target:
        set_if_blank(target, "capturedAtDate", incoming.get("capturedAtDate"))
        set_if_blank(target, "capturedAtTime", incoming.get("capturedAtTime"))

    set_if_blank(target, "country", country)


def make_media_item(relative_path: str, legacy_shape: bool, country: str) -> Dict[str, Any]:
    filename = Path(relative_path).name
    if legacy_shape:
        return {
            "src": relative_path,
            "filename": filename,
            "alt": "",
            "caption": "",
            "credit": "",
            "capturedAtDate": None,
            "capturedAtTime": None,
            "siteName": None,
            "locationLabel": None,
            "municipality": None,
            "county": None,
            "country": country,
            "coordinates": {
                "lat": None,
                "lon": None,
            },
            "notes": "",
        }
    return {
        "file": relative_path,
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


def hydrate_media_item(item: Dict[str, Any], relative_path: str, metadata: Dict[str, Any], sheet: Dict[str, Any], country: str) -> None:
    legacy_shape = media_uses_legacy_shape(item, sheet)
    if legacy_shape:
        item.pop("file", None)
        item.pop("capturedAt", None)
        item.setdefault("src", relative_path)
        item.setdefault("filename", Path(relative_path).name)
        item.setdefault("coordinates", {"lat": None, "lon": None})
        set_if_blank(item, "country", country)
        set_if_blank(item, "capturedAtDate", metadata.get("observedAtDate"))
        set_if_blank(item, "capturedAtTime", metadata.get("observedAtTime"))
        coordinates = item["coordinates"]
        if isinstance(coordinates, dict):
            set_if_blank(coordinates, "lat", metadata.get("decimalLatitude"))
            set_if_blank(coordinates, "lon", metadata.get("decimalLongitude"))
        return

    for key in ("src", "filename", "capturedAtDate", "capturedAtTime", "coordinates", "siteName", "locationLabel", "municipality", "county", "notes"):
        item.pop(key, None)
    item.setdefault("file", relative_path)
    captured_at = item.setdefault(
        "capturedAt",
        {
            "date": "",
            "time": "",
            "localityName": "",
            "decimalLatitude": None,
            "decimalLongitude": None,
        },
    )
    if isinstance(captured_at, dict):
        set_if_blank(captured_at, "date", metadata.get("observedAtDate"))
        set_if_blank(captured_at, "time", metadata.get("observedAtTime"))
        set_if_blank(captured_at, "decimalLatitude", metadata.get("decimalLatitude"))
        set_if_blank(captured_at, "decimalLongitude", metadata.get("decimalLongitude"))


def populate_field_record_from_metadata(field_record: Dict[str, Any], metadata: Dict[str, Any]) -> None:
    set_if_blank(field_record, "observedAtDate", metadata.get("observedAtDate"))
    set_if_blank(field_record, "date", metadata.get("observedAtDate"))
    set_if_blank(field_record, "observedAtTime", metadata.get("observedAtTime"))
    set_if_blank(field_record, "time", metadata.get("observedAtTime"))
    set_if_blank(field_record, "decimalLatitude", metadata.get("decimalLatitude"))
    set_if_blank(field_record, "decimalLongitude", metadata.get("decimalLongitude"))
    set_if_blank(field_record, "coordinateUncertaintyMeters", metadata.get("coordinateUncertaintyMeters"))


def ensure_media(sheet: Dict[str, Any], slug: str, field_record: Dict[str, Any], country: str) -> None:
    media = sheet.get("media")
    matched = match_images(slug)
    if not matched:
        return

    if isinstance(media, list):
        deduped_media: List[Dict[str, Any]] = []
        media_lookup: Dict[str, Dict[str, Any]] = {}
        for item in media:
            if not isinstance(item, dict):
                continue
            relative_path = media_image_path(item)
            if relative_path and relative_path in media_lookup:
                merge_media_items(media_lookup[relative_path], item, sheet, country)
                continue
            deduped_media.append(item)
            if relative_path:
                media_lookup[relative_path] = item
        media = deduped_media
        sheet["media"] = media
    else:
        media = []
        sheet["media"] = media

    prefer_legacy_shape = any(media_uses_legacy_shape(item, sheet) for item in media if isinstance(item, dict))
    first_metadata = None
    for image_path in matched:
        relative_path = to_relative_image_path(image_path)
        item = next((entry for entry in media if isinstance(entry, dict) and media_image_path(entry) == relative_path), None)
        if item is None:
            item = make_media_item(relative_path, prefer_legacy_shape, country)
            media.append(item)
        metadata = extract_image_metadata(image_path)
        hydrate_media_item(item, relative_path, metadata, sheet, country)
        if first_metadata is None and any(metadata.get(key) is not None for key in ("observedAtDate", "decimalLatitude", "decimalLongitude")):
            first_metadata = metadata

    if first_metadata:
        populate_field_record_from_metadata(field_record, first_metadata)


def coordinate_cache_key(latitude: float, longitude: float) -> str:
    return f"{latitude:.5f},{longitude:.5f}"


def parse_reverse_geocode(payload: Dict[str, Any]) -> Dict[str, Any]:
    address = payload.get("address") if isinstance(payload.get("address"), dict) else {}
    locality_name = first_non_blank(
        payload.get("name"),
        address.get("tourism"),
        address.get("attraction"),
        address.get("natural"),
        address.get("leisure"),
        address.get("historic"),
        address.get("amenity"),
        address.get("building"),
        address.get("farm"),
        address.get("isolated_dwelling"),
        address.get("hamlet"),
        address.get("suburb"),
        address.get("neighbourhood"),
        address.get("quarter"),
        address.get("residential"),
        address.get("village"),
        address.get("locality"),
        address.get("town"),
        address.get("city"),
        address.get("municipality"),
    )
    municipality = first_non_blank(
        address.get("municipality"),
        address.get("city"),
        address.get("town"),
        address.get("village"),
    )
    county = first_non_blank(address.get("county"), address.get("state"))
    country = address.get("country")
    location_label_parts = unique_non_blank([locality_name, municipality, county, country])
    return {
        "localityName": locality_name,
        "siteName": locality_name,
        "locationLabel": ", ".join(location_label_parts) if location_label_parts else None,
        "municipality": municipality,
        "county": county,
        "country": country,
    }


def reverse_geocode(latitude: float, longitude: float, cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    cache_key = coordinate_cache_key(latitude, longitude)
    cached = cache.get(cache_key)
    if isinstance(cached, dict) and cached:
        return cached

    query = urlencode(
        {
            "format": "jsonv2",
            "lat": f"{latitude:.6f}",
            "lon": f"{longitude:.6f}",
            "zoom": 18,
            "addressdetails": 1,
            "accept-language": "sv",
        }
    )
    request = Request(
        f"{NOMINATIM_URL}?{query}",
        headers={
            "User-Agent": NOMINATIM_USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}

    parsed = parse_reverse_geocode(payload)
    if parsed:
        cache[cache_key] = parsed
        time.sleep(1.0)
    return parsed


def ensure_reverse_geocoded_location(field_record: Dict[str, Any], cache: Dict[str, Dict[str, Any]]) -> None:
    latitude = field_record.get("decimalLatitude")
    longitude = field_record.get("decimalLongitude")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return
    if not any(is_blank(field_record.get(key)) for key in ("localityName", "municipality", "county", "locationLabel", "siteName")):
        return
    resolved = reverse_geocode(float(latitude), float(longitude), cache)
    if not resolved:
        return
    for key in ("localityName", "siteName", "locationLabel", "municipality", "county", "country"):
        set_if_blank(field_record, key, resolved.get(key))


def first_common_name(names: Any) -> str | None:
    if isinstance(names, list) and names:
        return str(names[0])
    if isinstance(names, str) and names.strip():
        return names.strip()
    return None


def ensure_defaults(sheet: Dict[str, Any], redlist_lookup: Dict[str, Dict[str, Any]], geocode_cache: Dict[str, Dict[str, Any]]) -> None:
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
    ensure_field_record_defaults(field_record, defaults.get("country", "Sweden"))

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

    ensure_media(sheet, slug, field_record, defaults.get("country", "Sweden"))
    ensure_reverse_geocoded_location(field_record, geocode_cache)


def build_index() -> Dict[str, Any]:
    redlist_lookup = build_redlist_lookup()
    geocode_cache = load_optional_json(REVERSE_GEOCODE_JSON)
    entries: List[Dict[str, Any]] = []

    for sheet_path in sorted(SPECIES_DIR.glob("*.json")):
        if sheet_path.name == "index.json":
            continue
        sheet = load_json(sheet_path)
        ensure_defaults(sheet, redlist_lookup, geocode_cache)
        save_json(sheet_path, sheet)

        identity = sheet["identity"]
        media = sheet.get("media") or []
        hero_image = None
        if media and isinstance(media[0], dict):
            hero_image = media_image_path(media[0])
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
    save_json(REVERSE_GEOCODE_JSON, geocode_cache)
    save_json(SPECIES_DIR / "index.json", payload)
    return payload


if __name__ == "__main__":
    index = build_index()
    print(f"Built species_sheets/index.json with {index['count']} species.")
