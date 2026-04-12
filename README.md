# measure.bio species sheets

This version is intentionally simple:

- the deployed site lives at the repo root
- the webpage itself is just `index.html`, `styles.css`, and `app.js`
- species content lives in `species_sheets/*.json`
- photos live in `img/`
- there is **no `dist/` folder** to think about

The only generated file the webpage needs is:

- `species_sheets/index.json`

That index is already included in this project, and can be refreshed with:

```bash
python scripts/build_site_data.py
```

## Folder structure

```text
measurebio_species_site_static/
  index.html
  styles.css
  app.js
  netlify.toml
  requirements.txt
  README.md
  species_sheets/
    index.json
    Sarcosoma_globosum.json
  img/
    Sarcosoma_globosum_1.jpeg
    Sarcosoma_globosum_2.jpeg
  data/
    Rodlistearbete_2025_alla_filer.xlsx
    swedish_redlist_2025_index.json
  scripts/
    build_site_data.py
    resolve_gbif_taxonomy.py
    update_field_record.py
  skills/
    species-sheet-builder/
      ...
```

## How the site works

### 1. Species sheets
Each species lives in its own JSON file inside `species_sheets/`.

### 2. Image linking
Photos are matched by slug prefix. Example:

- `species_sheets/Sarcosoma_globosum.json`
- `img/Sarcosoma_globosum_1.jpeg`
- `img/Sarcosoma_globosum_2.jpeg`

If you add more photos with the same prefix, `python scripts/build_site_data.py` will auto-link them.

### 3. Species index
A static site cannot truly list files in a folder on Netlify, so the webpage reads from `species_sheets/index.json`.

That file is rebuilt by:

```bash
python scripts/build_site_data.py
```

### 4. Default person name
Each sheet uses `defaults.personName`, and the project default is:

```json
"Tobias Andermann"
```

If a specific page author, observer, or photographer is not filled in, the site falls back to that default name.

## Local preview

Because the page fetches JSON files, do **not** open `index.html` directly as a `file://` URL.

Instead run:

```bash
python -m http.server 8000
```

Then open:

```text
http://127.0.0.1:8000
```

## Netlify deployment

This project is ready for a GitHub + Netlify workflow.

### Recommended settings

- **Build command**
  ```bash
  python -m pip install -r requirements.txt && python scripts/build_site_data.py
  ```

- **Publish directory**
  ```bash
  .
  ```

The included `netlify.toml` already sets this up.

### Why there is no `dist/` folder
The previous `dist/` approach was a generated deploy folder. This version removes that layer so the site is easier to understand and edit manually.

Netlify now publishes the repo root directly, and only runs the build script to refresh `species_sheets/index.json` and local helper data before deployment.

## Swedish red-list lookup

The project uses the bundled workbook:

- `data/Rodlistearbete_2025_alla_filer.xlsx`

and builds:

- `data/swedish_redlist_2025_index.json`

This gives a local fallback for Swedish Red List lookups, so species pages can be generated even when live lookup is unreliable.

## GBIF occurrence map behavior

The site currently shows **one global GBIF hex-summary map** near the top of the page.

Filters applied in the current sheet configuration:

- `basisOfRecord = HUMAN_OBSERVATION`
- `basisOfRecord = MACHINE_OBSERVATION`
- `year >= 2000`
- `occurrenceStatus = PRESENT`

The map uses GBIF's hex-density tile style rather than plotting individual points, which scales better for species with many records.

## Artfakta and Swedish context

For Swedish species pages, treat **Artfakta** as the primary Swedish species-information source.

For the bundled `Sarcosoma_globosum.json`, the Swedish section includes:

- the Artfakta taxon URL
- the 2025 Swedish Red List category from the local workbook
- the SLU reporting call
- Naturvårdsverket action-program context

When generating new species sheets, always include an `artfakta` block under `swedishContext` and use the species-specific Artfakta taxon page whenever available.

## Fast field-record editing

Each species JSON has a top-level `fieldRecord` block near the beginning of the file.

You can edit it manually, or use:

```bash
python scripts/update_field_record.py species_sheets/Sarcosoma_globosum.json \
  --date 2026-04-11 \
  --time 08:42 \
  --locality-name "Uppsala län" \
  --lat 59.85057 \
  --lon 17.62895
```

Those values are used by the page for:

- the field-record card
- the locality mini-map
- the OpenStreetMap location link

## GBIF taxonomy helper

To follow the GBIF + Catalogue of Life workflow closely, use:

```bash
python scripts/resolve_gbif_taxonomy.py "Sarcosoma globosum"
```

That script mirrors the logic from your earlier name-cleaning workflow:

- `pygbif.species.name_backbone(scientificName=..., checklistKey=...)`
- prefer `acceptedUsage.canonicalName`
- extract taxonomy from the `classification` array

The checklist key is set to:

```text
7ddf754f-d193-4cc9-b351-99906754a03b
```

## Prompt for Codex or another local LLM

Use the prompt below whenever you want your local model to create a new species sheet JSON.

```text
You are working inside the measure.bio species-sheet project.

Your task is to create exactly one new species sheet JSON file in `species_sheets/` for the focal species, and to make it immediately usable by the static webpage.

Before writing anything:
1. Read `skills/species-sheet-builder/SKILL.md`.
2. Read:
   - `skills/species-sheet-builder/references/output-template.md`
   - `skills/species-sheet-builder/references/research-standards.md`
   - `skills/species-sheet-builder/references/model-portability.md`
3. Use the local helper scripts when appropriate:
   - `python scripts/resolve_gbif_taxonomy.py "SCIENTIFIC NAME"`
   - `python scripts/build_site_data.py`

Requirements for the new species sheet:
- Save it as `species_sheets/<Scientific_name_with_underscores>.json`
- The default person name must be `"Tobias Andermann"` unless I explicitly provide another name
- The main display name on the page must be the English common name when a solid English common name exists
- Store the Swedish common name under `identity.commonNames.sv`
- Use GBIF taxonomy only
- Resolve taxonomy using the Catalogue of Life checklist workflow through GBIF, i.e. use checklistKey:
  `7ddf754f-d193-4cc9-b351-99906754a03b`
- Do not use NCBI taxonomy
- Build the Swedish section primarily from Artfakta
- Include an `artfakta` block under `swedishContext` with the species-specific Artfakta URL
- Use the local workbook `data/Rodlistearbete_2025_alla_filer.xlsx` for the Swedish Red List category if live lookup is unreliable
- Include a global IUCN status separately from the Swedish status when available
- Include DOI-checked literature only
- Keep international context and Swedish context separate
- Include a GBIF map configuration that uses:
  - `basisOfRecord = HUMAN_OBSERVATION`
  - `basisOfRecord = MACHINE_OBSERVATION`
  - `year >= 2000`
  - `occurrenceStatus = PRESENT`
  - hex summary map style
- Mention GBIF sampling bias explicitly
- Fill the top-level `fieldRecord` block if I gave you date, time, locality or coordinates
- Link any matching images from `img/` that follow the species slug pattern, e.g.:
  `img/Sarcosoma_globosum_1.jpeg`, `img/Sarcosoma_globosum_2.jpeg`
- If matching images exist, add them to the `media` array
- Preserve a clean, valid JSON structure that the webpage can render directly

After creating the JSON file:
1. Run `python scripts/build_site_data.py`
2. Ensure `species_sheets/index.json` now includes the new sheet
3. Do not modify `index.html`, `styles.css` or `app.js` unless I explicitly ask
4. Report back with:
   - the created JSON file path
   - the English main name
   - the Swedish name
   - the GBIF taxon key
   - the Swedish Red List category
   - the Artfakta URL
   - the linked photo filenames

Focus on producing a complete, evidence-based, visitor-friendly species sheet rather than generic filler text.
```

## Recommended workflow for adding a new species

1. Put your photos into `img/` using the species slug prefix.
2. Ask Codex to generate the new JSON using the prompt above.
3. Run:
   ```bash
   python scripts/build_site_data.py
   ```
4. Commit and push to GitHub.
5. Netlify redeploys automatically.

