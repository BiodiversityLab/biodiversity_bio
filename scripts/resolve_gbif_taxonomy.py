#!/usr/bin/env python3
"""Resolve a species against GBIF using the Catalogue of Life checklistKey workflow.

This script mirrors the logic of the uploaded clean_species_names.py:
- use pygbif.species.name_backbone(scientificName=..., checklistKey=...)
- prefer acceptedUsage.canonicalName where available
- extract taxonomy from the classification array
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Dict

from pygbif import species

GBIF_CHECKLIST_KEY = "7ddf754f-d193-4cc9-b351-99906754a03b"


def normalize_species_name(name: Any) -> str | None:
    if not name:
        return None
    parts = str(name).split()
    if not parts:
        return None
    return " ".join(parts[:2])


def extract_species_name(match_row: Dict[str, Any]) -> str | None:
    accepted_usage = match_row.get("acceptedUsage")
    if isinstance(accepted_usage, dict):
        accepted_name = normalize_species_name(accepted_usage.get("canonicalName"))
        if accepted_name:
            return accepted_name
    usage = match_row.get("usage")
    if isinstance(usage, dict):
        usage_name = normalize_species_name(usage.get("canonicalName"))
        if usage_name:
            return usage_name
        usage_name = normalize_species_name(usage.get("name"))
        if usage_name:
            return usage_name
    canonical_name = normalize_species_name(match_row.get("canonicalName"))
    if canonical_name:
        return canonical_name
    return normalize_species_name(match_row.get("scientificName"))


def extract_taxonomy(classification: Any) -> Dict[str, Any]:
    taxonomy: Dict[str, Any] = {}
    if not isinstance(classification, list):
        return taxonomy
    for item in classification:
        if not isinstance(item, dict):
            continue
        rank = item.get("rank")
        name = item.get("name")
        if not rank or not name:
            continue
        taxonomy[str(rank).strip().lower().replace(" ", "_")] = name
    return taxonomy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scientific_name")
    parser.add_argument("--checklist-key", default=GBIF_CHECKLIST_KEY)
    args = parser.parse_args()

    query = {"scientificName": args.scientific_name}
    if args.checklist_key:
        query["checklistKey"] = args.checklist_key

    matched = species.name_backbone(**query)
    matched = {k: v for k, v in matched.items() if k not in {"alternatives", "note"}}
    payload = {
        "queryScientificName": args.scientific_name,
        "resolvedAgainstChecklistKey": args.checklist_key,
        "acceptedName": extract_species_name(matched),
        "taxonomy": extract_taxonomy(matched.get("classification")),
        "raw": matched,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
