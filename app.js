
const state = {
  index: [],
  filtered: [],
  activeSlug: null,
  activeSheet: null,
  galleryIndex: 0,
  maps: {}
};

const contentEl = document.getElementById("content");
const speciesListEl = document.getElementById("speciesList");
const speciesCountEl = document.getElementById("speciesCount");
const speciesSearchEl = document.getElementById("speciesSearch");

async function fetchJsonRelative(relativePath) {
  const candidates = [
    relativePath,
    `./${relativePath}`.replace("././", "./"),
    new URL(relativePath, window.location.href).toString()
  ];
  let lastError = null;
  for (const candidate of candidates) {
    try {
      const response = await fetch(candidate, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      return await response.json();
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error(`Could not load ${relativePath}`);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatList(items) {
  if (!Array.isArray(items) || !items.length) return '<p class="muted">No details yet.</p>';
  return `<ul class="list">${items.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function formatValue(value, fallback = "Not yet filled") {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "string" && !value.trim()) return fallback;
  return escapeHtml(value);
}

function getDisplayPerson(sheet, key) {
  const explicit = sheet?.byline?.[key];
  if (explicit) return explicit;
  return sheet?.defaults?.personName || "Tobias Andermann";
}

function getEnglishName(sheet) {
  const legacyCommonNames = Array.isArray(sheet?.commonNames)
    ? sheet.commonNames
        .filter(item => item?.lang === "en")
        .sort((a, b) => Number(Boolean(b?.preferred)) - Number(Boolean(a?.preferred)))
        .map(item => item?.name)
        .filter(Boolean)
    : [];
  return (
    sheet?.hero?.headline ||
    sheet?.identity?.mainName ||
    sheet?.identity?.commonNames?.en?.[0] ||
    legacyCommonNames[0] ||
    sheet?.commonName ||
    sheet?.scientificName ||
    sheet?.identity?.scientificName ||
    "Unknown species"
  );
}

function getSwedishName(sheet) {
  const legacySwedishNames = Array.isArray(sheet?.commonNames)
    ? sheet.commonNames
        .filter(item => item?.lang === "sv")
        .sort((a, b) => Number(Boolean(b?.preferred)) - Number(Boolean(a?.preferred)))
        .map(item => item?.name)
        .filter(Boolean)
    : [];
  return sheet?.identity?.commonNames?.sv?.[0] || legacySwedishNames[0] || sheet?.swedishContext?.commonName || "—";
}

function getScientificName(sheet) {
  return sheet?.identity?.scientificName || sheet?.scientificName || "";
}

function getTaxonomyClassification(sheet) {
  return sheet?.taxonomy?.classification || {
    kingdom: sheet?.taxonomy?.kingdom,
    phylum: sheet?.taxonomy?.phylum,
    class: sheet?.taxonomy?.class,
    order: sheet?.taxonomy?.order,
    family: sheet?.taxonomy?.family,
    genus: sheet?.taxonomy?.genus,
    species: sheet?.taxonomy?.species
  };
}

function getAcceptedScientificName(sheet) {
  return sheet?.taxonomy?.acceptedScientificName || sheet?.taxonomy?.acceptedName;
}

function getAcceptedTaxonKey(sheet) {
  return sheet?.taxonomy?.acceptedTaxonKey || sheet?.taxonomy?.gbifUsageKey;
}

function getChecklistKey(sheet) {
  return sheet?.taxonomy?.resolvedAgainstChecklistKey || sheet?.taxonomy?.gbifChecklistKey;
}

function getHeroLede(sheet) {
  return sheet?.hero?.lede || sheet?.hero?.strapline || sheet?.summary || "";
}

function getReturnReason(sheet) {
  return sheet?.hero?.returnReason || sheet?.whyReturn?.[0] || "";
}

function getSheetLiterature(sheet) {
  return sheet?.literature || sheet?.selectedLiterature || [];
}

function getMediaFile(item) {
  return item?.file || item?.src || (item?.filename ? `img/${item.filename}` : "");
}

function getMediaCaption(item, sheet) {
  return item?.caption || item?.alt || getEnglishName(sheet);
}

function getMediaCoordinates(item) {
  if (typeof item?.capturedAt?.decimalLatitude === "number" && typeof item?.capturedAt?.decimalLongitude === "number") {
    return {
      lat: item.capturedAt.decimalLatitude,
      lon: item.capturedAt.decimalLongitude,
      label: item?.capturedAt?.localityName || item?.caption || ""
    };
  }
  if (typeof item?.coordinates?.lat === "number" && typeof item?.coordinates?.lon === "number") {
    return {
      lat: item.coordinates.lat,
      lon: item.coordinates.lon,
      label: item?.siteName || item?.caption || ""
    };
  }
  return null;
}

function getSlugFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const slugParam = params.get("species");
  if (slugParam) return slugParam;
  if (window.location.hash.startsWith("#species=")) {
    return window.location.hash.replace("#species=", "");
  }
  return null;
}

function setActiveSlug(slug, push = true) {
  state.activeSlug = slug;
  if (push) {
    const url = new URL(window.location.href);
    url.searchParams.set("species", slug);
    history.replaceState({}, "", url);
  }
  renderSpeciesList();
  loadSpeciesSheet(slug);
}

function buildSheetPath(fileName) {
  return `species_sheets/${fileName}`;
}

async function loadIndex() {
  try {
    const indexPayload = await fetchJsonRelative("species_sheets/index.json");
    state.index = Array.isArray(indexPayload.species) ? indexPayload.species : [];
    state.filtered = [...state.index];
    speciesCountEl.textContent = `${state.index.length} sheet${state.index.length === 1 ? "" : "s"}`;
    renderSpeciesList();
    const initialSlug = getSlugFromLocation() || state.index[0]?.slug;
    if (initialSlug) {
      setActiveSlug(initialSlug, false);
    } else {
      contentEl.innerHTML = `<div class="empty-state"><h2>No species sheets found</h2><p>Add JSON files to <code>species_sheets/</code> and rebuild <code>species_sheets/index.json</code>.</p></div>`;
    }
  } catch (error) {
    contentEl.innerHTML = `
      <div class="empty-state">
        <p class="eyebrow">Load error</p>
        <h2>Could not load species index</h2>
        <p>${escapeHtml(error.message || "Unknown error")}</p>
        <p>Expected file: <code>species_sheets/index.json</code>.</p>
      </div>
    `;
    speciesCountEl.textContent = "0 sheets";
  }
}

function filterSpecies(query) {
  const q = query.trim().toLowerCase();
  if (!q) {
    state.filtered = [...state.index];
    renderSpeciesList();
    return;
  }
  state.filtered = state.index.filter(item => {
    return [
      item.mainName,
      item.scientificName,
      item.swedishName,
      item.slug
    ].filter(Boolean).some(value => String(value).toLowerCase().includes(q));
  });
  renderSpeciesList();
}

function renderSpeciesList() {
  if (!state.filtered.length) {
    speciesListEl.innerHTML = `<div class="sidebar-card"><p class="sidebar-title">No matches</p><p class="sidebar-count">Try a broader search term.</p></div>`;
    return;
  }
  speciesListEl.innerHTML = state.filtered.map(item => {
    const activeClass = item.slug === state.activeSlug ? "is-active" : "";
    const thumb = item.heroImage
      ? `<img src="${escapeHtml(item.heroImage)}" alt="${escapeHtml(item.mainName)}">`
      : "";
    return `
      <button type="button" data-slug="${escapeHtml(item.slug)}">
        <div class="species-pill ${activeClass}">
          <div class="species-pill__thumb">${thumb}</div>
          <div>
            <div class="species-pill__name">${escapeHtml(item.mainName || item.scientificName)}</div>
            <div class="species-pill__meta"><em>${escapeHtml(item.scientificName || "")}</em>${item.swedishName ? ` · ${escapeHtml(item.swedishName)}` : ""}</div>
          </div>
        </div>
      </button>
    `;
  }).join("");
  speciesListEl.querySelectorAll("button[data-slug]").forEach(button => {
    button.addEventListener("click", () => setActiveSlug(button.dataset.slug));
  });
}

async function loadSpeciesSheet(slug) {
  const item = state.index.find(entry => entry.slug === slug);
  if (!item) {
    contentEl.innerHTML = `<div class="empty-state"><h2>Species not found</h2><p>No index entry matched <code>${escapeHtml(slug)}</code>.</p></div>`;
    return;
  }
  try {
    const sheet = await fetchJsonRelative(buildSheetPath(item.file));
    state.activeSheet = sheet;
    state.galleryIndex = 0;
    renderSheet(sheet);
  } catch (error) {
    contentEl.innerHTML = `
      <div class="empty-state">
        <p class="eyebrow">Load error</p>
        <h2>Could not load species sheet</h2>
        <p>${escapeHtml(error.message || "Unknown error")}</p>
      </div>
    `;
  }
}

function buildGbifHexTileTemplate(sheet) {
  const gbif = sheet?.distribution?.gbif || {};
  const taxonKey = gbif.taxonKey || getAcceptedTaxonKey(sheet);
  if (!taxonKey) return null;
  const params = new URLSearchParams();
  params.set("srs", gbif.srs || "EPSG:3857");
  params.set("style", gbif.tileStyle || "classic.poly");
  params.set("bin", gbif.bin || "hex");
  params.set("hexPerTile", String(gbif.hexPerTile || 57));
  params.set("taxonKey", String(taxonKey));
  const filters = gbif.filters || {};
  const yearFrom = filters.yearFrom || 2000;
  const yearTo = new Date().getFullYear() + 1;
  params.set("year", `${yearFrom},${yearTo}`);
  if (filters.occurrenceStatus) {
    params.set("occurrenceStatus", filters.occurrenceStatus);
  }
  if (Array.isArray(filters.basisOfRecord)) {
    filters.basisOfRecord.forEach(value => params.append("basisOfRecord", value));
  }
  return `https://api.gbif.org/v2/map/occurrence/density/{z}/{x}/{y}@1x.png?${params.toString()}`;
}

function renderQuickFacts(sheet) {
  const facts = Array.isArray(sheet.quickFacts) ? sheet.quickFacts : [];
  if (!facts.length) return "";
  return `
    <div class="quick-facts">
      ${facts.map(item => `
        <div class="fact-chip">
          <span class="fact-chip__label">${escapeHtml(item.label)}</span>
          <span class="fact-chip__value">${escapeHtml(item.value)}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function renderFieldRecord(sheet) {
  const field = sheet.fieldRecord || {};
  const locality = field.localityName || field.siteName || field.locationLabel;
  return `
    <div class="panel">
      <p class="eyebrow">Field record</p>
      <h2 class="section-title">Quick entry block</h2>
      <div class="meta-grid">
        <div class="meta-row"><div class="meta-label">Observer</div><div>${formatValue(field.observer || sheet.defaults?.personName)}</div></div>
        <div class="meta-row"><div class="meta-label">Date</div><div>${formatValue(field.date)}</div></div>
        <div class="meta-row"><div class="meta-label">Time</div><div>${formatValue(field.time)}</div></div>
        <div class="meta-row"><div class="meta-label">Locality</div><div>${formatValue(locality)}</div></div>
        <div class="meta-row"><div class="meta-label">Municipality / county</div><div>${escapeHtml([field.municipality, field.county].filter(Boolean).join(" / ") || "Not yet filled")}</div></div>
        <div class="meta-row"><div class="meta-label">Coordinates</div><div>${field.decimalLatitude != null && field.decimalLongitude != null ? `${escapeHtml(field.decimalLatitude)}, ${escapeHtml(field.decimalLongitude)}` : "Not yet filled"}</div></div>
        <div class="meta-row"><div class="meta-label">Habitat note</div><div>${formatValue(field.habitatNote)}</div></div>
      </div>
      <p class="footer-note">Edit this directly in each species JSON under <code>fieldRecord</code>, or use <code>python scripts/update_field_record.py ...</code>.</p>
    </div>
  `;
}

function renderMediaGallery(sheet) {
  const media = Array.isArray(sheet.media) ? sheet.media : [];
  if (!media.length) {
    return `<div class="panel hero-media"><p class="muted">No images linked yet. Put photos in <code>img/</code> using the species slug prefix.</p></div>`;
  }
  const active = media[state.galleryIndex] || media[0];
  const thumbs = media.map((item, index) => {
    const isActive = index === state.galleryIndex ? "is-active" : "";
    const file = getMediaFile(item);
    return `
      <button type="button" class="thumbnail-button ${isActive}" data-index="${index}" aria-label="Show photo ${index + 1}">
        <img src="${escapeHtml(file)}" alt="${escapeHtml(getMediaCaption(item, sheet))}">
      </button>
    `;
  }).join("");

  return `
    <div class="panel hero-media">
      <div class="main-image-wrap">
        <img class="main-image" src="${escapeHtml(getMediaFile(active))}" alt="${escapeHtml(getMediaCaption(active, sheet))}">
      </div>
      <div class="thumbnail-row">${thumbs}</div>
      <div class="hero-caption">${escapeHtml(active.caption || "")}</div>
    </div>
  `;
}

function renderSourceList(sources) {
  if (!Array.isArray(sources) || !sources.length) return '<p class="muted">No sources listed yet.</p>';
  return `
    <div class="source-list">
      ${sources.map(source => `
        <div class="source-item">
          <div class="source-item__label">${escapeHtml(source.label || source.id || source.url || "Source")}</div>
          <div class="source-item__meta">
            ${source.type ? `<div>${escapeHtml(source.type)}</div>` : ""}
            ${source.url ? `<div><a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.url)}</a></div>` : ""}
            ${source.note ? `<div>${escapeHtml(source.note)}</div>` : ""}
            ${Array.isArray(source.usedFor) && source.usedFor.length ? `<div>${escapeHtml(source.usedFor.join(", "))}</div>` : ""}
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderLiterature(literature) {
  if (!Array.isArray(literature) || !literature.length) return '<p class="muted">No literature listed yet.</p>';
  return `
    <div class="literature-list">
      ${literature.map(item => `
        <div class="literature-item">
          <div class="literature-item__title">${escapeHtml(item.title || "Untitled reference")}</div>
          <div class="literature-item__meta">
            <div>${escapeHtml((item.authors || []).join(", "))}${item.year ? ` (${escapeHtml(item.year)})` : ""}</div>
            <div>${escapeHtml([item.journal, item.volume, item.issue ? `(${item.issue})` : "", item.pagesOrArticle || item.pages].filter(Boolean).join(" "))}</div>
            ${item.doi ? `<div>DOI: <a href="${escapeHtml(item.url || item.doi_url || `https://doi.org/${item.doi}`)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.doi)}</a></div>` : ""}
            ${item.whyRelevant || item.relevance ? `<div>${escapeHtml(item.whyRelevant || item.relevance)}</div>` : ""}
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderSheet(sheet) {
  const mainName = getEnglishName(sheet);
  const swedishName = getSwedishName(sheet);
  const scientificName = getScientificName(sheet);
  const taxonomy = getTaxonomyClassification(sheet);
  const swedish = sheet?.swedishContext || {};
  const redList = swedish.redList2025 || {};
  const gbifTileTemplate = buildGbifHexTileTemplate(sheet);
  const artfaktaUrl = swedish?.artfakta?.url || swedish?.artfakta?.fallbackUrl;

  contentEl.innerHTML = `
    <article class="sheet">
      <section class="hero">
        <div class="hero-copy">
          <div class="panel">
            <p class="eyebrow">${escapeHtml([taxonomy.kingdom, taxonomy.phylum].filter(Boolean).join(" · "))}</p>
            <h2 class="hero-title">${escapeHtml(mainName)}</h2>
            <p class="hero-scientific"><em>${escapeHtml(scientificName)}</em> · Swedish: ${escapeHtml(swedishName)}</p>
            <p class="byline">Default name: ${escapeHtml(sheet?.defaults?.personName || "Tobias Andermann")} · Page author: ${escapeHtml(getDisplayPerson(sheet, "pageAuthor"))}</p>
            <p class="hero-lede">${escapeHtml(getHeroLede(sheet))}</p>
            ${renderQuickFacts(sheet)}
            <div class="note-box">
              <strong>Return reason</strong>
              <div class="section-text">${escapeHtml(getReturnReason(sheet))}</div>
            </div>
          </div>
          ${renderFieldRecord(sheet)}
        </div>
        <div class="hero-media-wrap">${renderMediaGallery(sheet)}</div>
      </section>

      <section class="panel">
        <p class="eyebrow">Occurrence map</p>
        <h2 class="section-title">GBIF map — global occurrence summary</h2>
        <div class="map-grid">
          <div class="map-shell">
            <div id="globalGbifMap" class="map" data-tile-template="${escapeHtml(gbifTileTemplate || "")}"></div>
          </div>
          <div class="map-notes">
            <div class="info-card panel">
              <h3 class="section-title">Map filters</h3>
              <div class="badge-row">
                <span class="badge">Human observation</span>
                <span class="badge">Machine observation</span>
                <span class="badge">Year ≥ 2000</span>
                <span class="badge">Present only</span>
                <span class="badge">Hex summary</span>
              </div>
              <p class="section-text">${escapeHtml(sheet?.distribution?.samplingBiasNote || sheet?.distribution?.caveat || "")}</p>
            </div>
            <div class="info-card panel">
              <h3 class="section-title">Field locality mini-map</h3>
              <div id="fieldLocationMap" class="mini-map"></div>
              <p class="footer-note">If coordinates are filled in under <code>fieldRecord</code> or a photo's <code>capturedAt</code>, this map becomes clickable and centres on the observation.</p>
            </div>
          </div>
        </div>
      </section>

      <section class="two-up">
        <div class="panel">
          <p class="eyebrow">International context</p>
          <h2 class="section-title">Ecology and global perspective</h2>
          <p class="section-text">${escapeHtml(sheet?.internationalContext?.summary || sheet?.internationalContext?.overview || "")}</p>
          <h3 class="section-title">Ecology</h3>
          ${formatList(sheet?.internationalContext?.ecology || [])}
          <h3 class="section-title">Threats</h3>
          ${formatList(sheet?.internationalContext?.threats || [])}
          <h3 class="section-title">Phenology</h3>
          <div class="meta-grid">
            <div class="meta-row"><div class="meta-label">Northern Europe</div><div>${formatValue(sheet?.internationalContext?.phenology?.northernEurope)}</div></div>
            <div class="meta-row"><div class="meta-label">Note</div><div>${formatValue(sheet?.internationalContext?.phenology?.note)}</div></div>
          </div>
        </div>

        <div class="panel">
          <p class="eyebrow">Swedish context</p>
          <h2 class="section-title">Artfakta-led Swedish sheet</h2>
          <p class="section-text">${escapeHtml(swedish.summary || swedish.overview || "")}</p>
          <div class="meta-grid">
            <div class="meta-row"><div class="meta-label">Swedish name</div><div>${escapeHtml(swedishName)}</div></div>
            <div class="meta-row"><div class="meta-label">Swedish Red List 2025</div><div>${escapeHtml(redList.category || "—")} ${redList.criterion ? `(${escapeHtml(redList.criterion)})` : ""}</div></div>
            <div class="meta-row"><div class="meta-label">Taxon ID</div><div>${formatValue(redList.taxonId)}</div></div>
            <div class="meta-row"><div class="meta-label">Protected status</div><div>${escapeHtml((swedish.protectedStatus || []).join("; ") || "—")}</div></div>
            <div class="meta-row"><div class="meta-label">Artfakta</div><div>${artfaktaUrl ? `<a href="${escapeHtml(artfaktaUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(artfaktaUrl)}</a>` : "Not set"}</div></div>
          </div>
          <h3 class="section-title">Swedish key facts</h3>
          ${formatList(swedish.keyFacts || [])}
          <div class="note-box">
            <strong>2025 Red List documentation</strong>
            <div class="section-text">${escapeHtml(redList.documentation || "No local red-list documentation loaded.")}</div>
          </div>
        </div>
      </section>

      <section class="panel">
        <p class="eyebrow">Taxonomy</p>
          <h2 class="section-title">GBIF taxonomy</h2>
          <div class="meta-grid">
          <div class="meta-row"><div class="meta-label">Accepted scientific name</div><div>${formatValue(getAcceptedScientificName(sheet))}</div></div>
          <div class="meta-row"><div class="meta-label">GBIF taxon key</div><div>${formatValue(getAcceptedTaxonKey(sheet))}</div></div>
          <div class="meta-row"><div class="meta-label">Resolved against checklistKey</div><div>${formatValue(getChecklistKey(sheet))}</div></div>
          <div class="meta-row"><div class="meta-label">Kingdom → species</div><div>${escapeHtml([taxonomy.kingdom, taxonomy.phylum, taxonomy.class, taxonomy.order, taxonomy.family, taxonomy.genus, taxonomy.species].filter(Boolean).join(" → ") || "No classification loaded")}</div></div>
          <div class="meta-row"><div class="meta-label">Synonyms</div><div>${escapeHtml((sheet?.taxonomy?.synonyms || []).join("; ") || "—")}</div></div>
        </div>
      </section>

      <section class="two-up">
        <div class="panel">
          <p class="eyebrow">Literature</p>
          <h2 class="section-title">Cross-checked literature</h2>
          ${renderLiterature(getSheetLiterature(sheet))}
        </div>
        <div class="panel">
          <p class="eyebrow">Sources</p>
          <h2 class="section-title">Primary sources and links</h2>
          ${renderSourceList(sheet?.sources || [])}
        </div>
      </section>
    </article>
  `;

  attachGalleryEvents();
  renderMaps(sheet);
}

function attachGalleryEvents() {
  document.querySelectorAll(".thumbnail-button").forEach(button => {
    button.addEventListener("click", () => {
      state.galleryIndex = Number(button.dataset.index || 0);
      renderSheet(state.activeSheet);
    });
  });
}

function destroyMap(name) {
  if (state.maps[name]) {
    state.maps[name].remove();
    delete state.maps[name];
  }
}

function getFieldCoordinates(sheet) {
  const field = sheet?.fieldRecord || {};
  if (typeof field.decimalLatitude === "number" && typeof field.decimalLongitude === "number") {
    return {
      lat: field.decimalLatitude,
      lon: field.decimalLongitude,
      label: field.localityName || getEnglishName(sheet)
    };
  }
  if (Array.isArray(sheet?.media)) {
    const photoWithCoords = sheet.media
      .map(item => ({ item, coords: getMediaCoordinates(item) }))
      .find(entry => entry.coords);
    if (photoWithCoords) {
      return {
        lat: photoWithCoords.coords.lat,
        lon: photoWithCoords.coords.lon,
        label: photoWithCoords.coords.label || getEnglishName(sheet)
      };
    }
  }
  return null;
}

function renderMaps(sheet) {
  if (!window.L) {
    const globalMapEl = document.getElementById("globalGbifMap");
    const fieldMapEl = document.getElementById("fieldLocationMap");
    if (globalMapEl) globalMapEl.innerHTML = '<div class="empty-state"><p>Leaflet did not load. The rest of the page still works.</p></div>';
    if (fieldMapEl) fieldMapEl.innerHTML = '<div class="empty-state"><p>Leaflet did not load.</p></div>';
    return;
  }

  destroyMap("global");
  destroyMap("field");

  const globalMapEl = document.getElementById("globalGbifMap");
  const fieldMapEl = document.getElementById("fieldLocationMap");
  const tileTemplate = buildGbifHexTileTemplate(sheet);
  const fieldCoords = getFieldCoordinates(sheet);

  if (globalMapEl) {
    const globalMap = L.map(globalMapEl, {
      zoomControl: true,
      worldCopyJump: true
    }).setView([25, 10], 2);
    state.maps.global = globalMap;

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(globalMap);

    if (tileTemplate) {
      L.tileLayer(tileTemplate, {
        opacity: 0.82,
        attribution: 'GBIF occurrence density'
      }).addTo(globalMap);
    }

    if (fieldCoords) {
      L.circleMarker([fieldCoords.lat, fieldCoords.lon], {
        radius: 6,
        weight: 2,
        fillOpacity: 0.95
      }).addTo(globalMap).bindPopup(escapeHtml(fieldCoords.label));
    }
  }

  if (fieldMapEl) {
    if (fieldCoords) {
      const fieldMap = L.map(fieldMapEl, {
        zoomControl: true
      }).setView([fieldCoords.lat, fieldCoords.lon], 12);
      state.maps.field = fieldMap;
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors'
      }).addTo(fieldMap);
      const marker = L.marker([fieldCoords.lat, fieldCoords.lon]).addTo(fieldMap);
      const popupHtml = `
        <strong>${escapeHtml(fieldCoords.label)}</strong><br>
        <a href="https://www.openstreetmap.org/?mlat=${encodeURIComponent(fieldCoords.lat)}&mlon=${encodeURIComponent(fieldCoords.lon)}#map=14/${encodeURIComponent(fieldCoords.lat)}/${encodeURIComponent(fieldCoords.lon)}" target="_blank" rel="noopener noreferrer">Open this location in OpenStreetMap</a>
      `;
      marker.bindPopup(popupHtml).openPopup();
    } else {
      fieldMapEl.innerHTML = `
        <div class="empty-state">
          <h3 class="section-title">No coordinates yet</h3>
          <p>Add <code>fieldRecord.decimalLatitude</code> and <code>fieldRecord.decimalLongitude</code>, or fill a photo's <code>capturedAt</code> coordinates.</p>
        </div>
      `;
    }
  }
}

speciesSearchEl.addEventListener("input", event => filterSpecies(event.target.value));

window.addEventListener("hashchange", () => {
  const slug = getSlugFromLocation();
  if (slug && slug !== state.activeSlug) {
    setActiveSlug(slug, false);
  }
});

loadIndex();
