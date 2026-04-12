#!/usr/bin/env python3
"""Small helper for fast field-record edits.

Examples:
  python scripts/update_field_record.py species_sheets/Sarcosoma_globosum.json --date 2026-04-11 --time 08:42 --locality-name "Uppsala" --lat 59.85 --lon 17.63
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload):
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sheet")
    parser.add_argument("--date")
    parser.add_argument("--time")
    parser.add_argument("--locality-name")
    parser.add_argument("--municipality")
    parser.add_argument("--county")
    parser.add_argument("--country")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--uncertainty", type=float)
    parser.add_argument("--habitat-note")
    parser.add_argument("--observation-note")
    parser.add_argument("--observer")
    args = parser.parse_args()

    path = Path(args.sheet)
    payload = load_json(path)
    field = payload.setdefault("fieldRecord", {})

    if args.date is not None:
        field["date"] = args.date
    if args.time is not None:
        field["time"] = args.time
    if args.locality_name is not None:
        field["localityName"] = args.locality_name
    if args.municipality is not None:
        field["municipality"] = args.municipality
    if args.county is not None:
        field["county"] = args.county
    if args.country is not None:
        field["country"] = args.country
    if args.lat is not None:
        field["decimalLatitude"] = args.lat
    if args.lon is not None:
        field["decimalLongitude"] = args.lon
    if args.uncertainty is not None:
        field["coordinateUncertaintyMeters"] = args.uncertainty
    if args.habitat_note is not None:
        field["habitatNote"] = args.habitat_note
    if args.observation_note is not None:
        field["observationNote"] = args.observation_note
    if args.observer is not None:
        field["observer"] = args.observer

    save_json(path, payload)
    print(f"Updated {path}")


if __name__ == "__main__":
    main()
