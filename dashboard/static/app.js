/* ============================================================
   SPOTIFY DASHBOARD - app.js
   Laedt die Analyse-JSONs und baut alle Panels/Charts.
   ============================================================ */

// ---------- Design-Konstanten (an CSS angelehnt) ----------
const C = {
  bg: "#0d1117", panel: "#161b22", text: "#e6edf3", dim: "#8b949e",
  green: "#1DB954", red: "#ff4d4d", blue: "#4d9fff", border: "#2a3038",
};
const FONT = "Inter, sans-serif";

// gemeinsames Plotly-Layout (dunkel)
function baseLayout(extra = {}) {
  return Object.assign({
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: C.text, family: FONT, size: 12 },
    margin: { l: 60, r: 20, t: 10, b: 40 },
    xaxis: { gridcolor: C.border, zerolinecolor: C.border },
    yaxis: { gridcolor: C.border, zerolinecolor: C.border },
  }, extra);
}
const PLOT_CONFIG = { displayModeBar: false, responsive: true };

// ---------- kleine Helfer ----------
const $ = (sel) => document.querySelector(sel);
const fmt = (n) => n.toLocaleString("de-DE");
async function getData(name) {
  const r = await fetch(`/api/data/${name}`);
  if (!r.ok) throw new Error(`${name} konnte nicht geladen werden`);
  return r.json();
}

// zentraler Zustand
const STATE = {
  genre: "__all__",
  minPop: 0,
  cache: {},           // geladene JSONs
  explorerLoaded: false,
};

// ============================================================
//  NAVIGATION (4 Seiten)
// ============================================================
document.querySelectorAll(".nav button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    const page = btn.dataset.page;
    $(`#page-${page}`).classList.add("active");
  
    // Filterleisten je Seite umschalten
    const normalBar = document.querySelector(".filterbar:not(#explorerBar):not(#genreBar)");
    const explorerBar = document.querySelector("#explorerBar");
    const genreBar = document.querySelector("#genreBar");
    if (normalBar) normalBar.style.display = "none";
    if (explorerBar) explorerBar.style.display = (page === "explorer") ? "flex" : "none";
    if (genreBar) genreBar.style.display = (page === "genres") ? "flex" : "none";

    // Explorer erst bei Bedarf laden (grosse Datei)
    if (page === "explorer" && !STATE.explorerLoaded) initExplorer();
    // Plotly-Charts nach Sichtbarwerden neu vermessen
    window.dispatchEvent(new Event("resize"));
  });
});

// ============================================================
//  FILTER
// ============================================================
$("#popFilter").addEventListener("input", (e) => {
  STATE.minPop = +e.target.value;
  $("#popVal").textContent = STATE.minPop;
});
$("#popFilter").addEventListener("change", applyFilters);
$("#genreFilter").addEventListener("change", (e) => {
  STATE.genre = e.target.value; applyFilters();
});
$("#filterReset").addEventListener("click", () => {
  STATE.genre = "__all__"; STATE.minPop = 0;
  $("#genreFilter").value = "__all__";
  $("#popFilter").value = 0; $("#popVal").textContent = "0";
  applyFilters();
});

// Filter wirken (aktuell) auf die Top-10-Tabelle und die Genre-Top-Liste
function applyFilters() {
  renderTop10();
  renderTopGenres();
}

// ============================================================
//  INIT
// ============================================================
(async function init() {
  try {
    const [overview, genres] = await Promise.all([
      getData("overview"), getData("genres"),
    ]);
    STATE.cache.overview = overview;
    STATE.cache.genres = genres;

    // Genre-Filter fuellen
    const gf = $("#genreFilter");
    genres.forEach((g) => {
      const o = document.createElement("option"); o.value = g; o.textContent = g; gf.appendChild(o);
    });

    renderKPIs(overview);

    // restliche Daten laden
    STATE.cache.top10 = await getData("top10");
    STATE.cache.genre_stats = await getData("genre_stats");
    renderTop10();
    renderTopGenres();

    // Seite 2 + 3 vorbereiten (Fehler dort sollen Seite 1 nicht blockieren)
    initPopularityPage().catch((e) => console.error("Popularity:", e));
    initGenrePage().catch((e) => console.error("Genres:", e));
  } catch (err) {
    console.error(err);
    $("#kpiRow").innerHTML = `<div class="loading">Fehler beim Laden: ${err.message}. Läuft der Server & sind die JSONs im /data-Ordner?</div>`;
  }
  // normale Filterbar von Anfang an ausblenden
  const nb0 = document.querySelector(".filterbar:not(#explorerBar):not(#genreBar)");
  if (nb0) nb0.style.display = "none";
})();

// ============================================================
//  SEITE 1: ÜBERBLICK
// ============================================================
function renderKPIs(o) {
  const cards = [
    { val: fmt(o.n_songs), lab: "Songs (dedupliziert)", hint: `${fmt(o.n_rows)} Zeilen gesamt` },
    { val: o.n_genres, lab: "Genres" },
    { val: fmt(o.n_artists), lab: "Artists" },
    { val: o.avg_popularity, lab: "Ø Popularität", hint: `Median ${o.median_popularity}` },
    { val: "≥ " + o.popular_threshold, lab: "Populär-Schwelle", hint: "Top 10 %" },
  ];
  $("#kpiRow").innerHTML = cards.map((c) => `
    <div class="kpi">
      <div class="val">${c.val}</div>
      <div class="lab">${c.lab}</div>
      ${c.hint ? `<div class="hint">${c.hint}</div>` : ""}
    </div>`).join("");
}

function renderTop10() {
  let rows = STATE.cache.top10 || [];
  // Filter anwenden
  rows = rows.filter((r) =>
    (STATE.genre === "__all__" || r.track_genre === STATE.genre) &&
    r.popularity >= STATE.minPop
  );
  if (!rows.length) {
    $("#top10Table").innerHTML = `<div class="loading">Keine Songs für diesen Filter.</div>`;
    return;
  }
  $("#top10Table").innerHTML = `
    <table>
      <thead><tr><th>#</th><th>Song</th><th>Artist</th><th>Genre</th><th>Pop.</th></tr></thead>
      <tbody>
        ${rows.map((r, i) => `
          <tr>
            <td class="rank">${i + 1}</td>
            <td>${esc(r.track_name)}</td>
            <td>${esc(r.artists)}</td>
            <td style="color:var(--text-dim)">${esc(r.track_genre)}</td>
            <td><span class="pop-pill">${r.popularity}</span></td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}

function renderTopGenres() {
  let g = (STATE.cache.genre_stats || []).slice();
  if (STATE.genre !== "__all__") g = g.filter((x) => x.track_genre === STATE.genre);
  g = g.sort((a, b) => b.avg_popularity - a.avg_popularity).slice(0, 12).reverse();

  Plotly.react("topGenresPlot", [{
    type: "bar", orientation: "h",
    x: g.map((x) => x.avg_popularity),
    y: g.map((x) => x.track_genre),
    marker: { color: C.green },
    hovertemplate: "%{y}: %{x:.1f}<extra></extra>",
  }], baseLayout({ margin: { l: 90, r: 20, t: 6, b: 30 },
      xaxis: { gridcolor: C.border, title: "Ø Popularität" }, yaxis: { gridcolor: "rgba(0,0,0,0)" } }),
    PLOT_CONFIG);
}

// ============================================================
//  SEITE 2: POPULARITÄT
// ============================================================
async function initPopularityPage() {
  const [pvr, popcorr, rfimp, rfmet] = await Promise.all([
    getData("popular_vs_rest"), getData("correlation_popularity"),
    getData("rf_importance"), getData("rf_metrics"),
  ]);

  // Effektgroesse
  const f = pvr.features.slice().sort((a, b) => a.effect_size - b.effect_size);
  Plotly.react("effectPlot", [{
    type: "bar", orientation: "h",
    x: f.map((d) => d.effect_size), y: f.map((d) => d.feature),
    marker: { color: f.map((d) => d.effect_size >= 0 ? C.green : C.red) },
    hovertemplate: "%{y}: %{x:+.2f} σ<extra></extra>",
  }], baseLayout({ margin: { l: 120, r: 20, t: 6, b: 40 },
      xaxis: { title: "Effektgröße (σ)", gridcolor: C.border, zeroline: true, zerolinecolor: C.dim } }),
    PLOT_CONFIG);

  // Korrelation mit Popularitaet
  const p = popcorr.slice().sort((a, b) => a.pearson - b.pearson);
  Plotly.react("popCorrPlot", [{
    type: "bar", orientation: "h",
    x: p.map((d) => d.pearson), y: p.map((d) => d.feature),
    marker: { color: p.map((d) => d.pearson >= 0 ? C.green : C.red) },
    hovertemplate: "%{y}: r = %{x:+.3f}<extra></extra>",
  }], baseLayout({ margin: { l: 120, r: 20, t: 6, b: 40 },
      xaxis: { title: "Pearson r", gridcolor: C.border, zeroline: true, zerolinecolor: C.dim } }),
    PLOT_CONFIG);

  // RF Importance: Permutation vs Standard
  const perm = rfimp.permutation.slice().sort((a, b) => a.importance - b.importance);
  const stdMap = Object.fromEntries(rfimp.standard.map((d) => [d.feature, d.importance]));
  Plotly.react("rfImpPlot", [
    { type: "bar", orientation: "h", name: "Permutation",
      x: perm.map((d) => d.importance), y: perm.map((d) => d.feature),
      marker: { color: C.green },
      error_x: { type: "data", array: perm.map((d) => d.std), color: C.dim, thickness: 1 },
      hovertemplate: "%{y}: %{x:.4f}<extra>Permutation</extra>" },
    { type: "bar", orientation: "h", name: "Standard",
      x: perm.map((d) => stdMap[d.feature] || 0), y: perm.map((d) => d.feature),
      marker: { color: C.blue }, opacity: 0.6,
      hovertemplate: "%{y}: %{x:.4f}<extra>Standard</extra>" },
  ], baseLayout({ barmode: "group", margin: { l: 120, r: 20, t: 6, b: 40 },
      legend: { orientation: "h", y: 1.08, x: 0 },
      xaxis: { title: "Wichtigkeit", gridcolor: C.border } }),
    PLOT_CONFIG);

  // Metriken
  const stabColor = rfmet.stability === "STABIL" ? C.green
                   : rfmet.stability === "AKZEPTABEL" ? C.blue : C.red;
  $("#rfMetrics").innerHTML = `
    <div class="song-meta" style="margin-top:0">
      <div class="box"><div class="k">R²</div><div class="v">${(rfmet.r2 * 100).toFixed(1)} %</div></div>
      <div class="box"><div class="k">RMSE</div><div class="v">±${rfmet.rmse.toFixed(1)}</div></div>
      <div class="box"><div class="k">MAE</div><div class="v">±${rfmet.mae.toFixed(1)}</div></div>
      <div class="box"><div class="k">CV R²</div><div class="v">${rfmet.cv_mean.toFixed(3)}</div></div>
    </div>
    <div class="box" style="margin-top:10px; background:var(--panel-2); border:1px solid var(--border); border-radius:10px; padding:10px 12px">
      <div class="k" style="color:var(--text-dim); font-size:11px; text-transform:uppercase; letter-spacing:.04em">Stabilität (5-Fold)</div>
      <div class="v" style="color:${stabColor}; font-weight:800; font-size:16px; margin-top:2px">${rfmet.stability} · ±${rfmet.cv_std.toFixed(3)}</div>
    </div>
    `;
}

// ============================================================
//  SEITE 3: GENRES
// ============================================================
async function initGenrePage() {
  const [cm, gmap] = await Promise.all([
    getData("correlation_matrix"), getData("genre_map"),
  ]);


  // Korrelationsmatrix (untere Dreiecksmatrix maskiert)
  const labels = cm.labels;
  const z = cm.matrix.map((row, i) => row.map((v, j) => (j > i ? null : v)));
  Plotly.react("corrMatrixPlot", [{
    type: "heatmap", z, x: labels, y: labels,
    colorscale: [
      [0.0, "#e63946"],   // -1  : sattes Rot
      [0.25, "#8b2c34"],  // -0.5: dunkleres Rot
      [0.5, "#0d1117"],   //  0  : fast schwarz (Mitte)
      [0.75, "#1a7a3f"],  // +0.5: dunkleres Grün
      [1.0, "#1DB954"],   // +1  : sattes Spotify-Grün
    ],
    zmin: -1, zmax: 1, xgap: 1, ygap: 1,
    hovertemplate: "%{y} ↔ %{x}: %{z:.2f}<extra></extra>",
    colorbar: { thickness: 10, len: 0.7, tickfont: { color: C.dim } },
  }], baseLayout({ margin: { l: 110, r: 20, t: 6, b: 110 },
      xaxis: { tickangle: -45, gridcolor: "rgba(0,0,0,0)", autorange: true },
      yaxis: { autorange: "reversed", gridcolor: "rgba(0,0,0,0)" } }),
    PLOT_CONFIG);

  // Genre-Map (PCA + KMeans): ein Trace pro Cluster
  renderGenreMap(gmap);
  renderClusterLegend(gmap);
  initGenreRadar();
}

// Genre-Map als Scatter: Naehe = Aehnlichkeit, Farbe = Cluster, Groesse = Popularitaet
async function renderGenreMap(gmap) {
  const el = document.getElementById("genreMapPlot");
  if (!el) return;
  try {
    const html = await (await fetch("/api/genremap")).text();
    el.innerHTML = html;
    // Plotly-Skripte im eingefügten HTML ausführen
    el.querySelectorAll("script").forEach((old) => {
      const s = document.createElement("script");
      s.textContent = old.textContent;
      document.body.appendChild(s);
    });
  } catch (e) {
    el.innerHTML = "<p style='color:#888'>Genre-Map konnte nicht geladen werden.</p>";
  }
}
  

// ============================================================
//  SEITE 4: TRACK-EXPLORER
// ============================================================
async function initExplorer() {
  STATE.explorerLoaded = true;
  try {
    const [tracks, glossary] = await Promise.all([
      getData("tracks_explorer"), getData("feature_glossary"),
    ]);
    STATE.cache.tracks = tracks;

    // nach Genre gruppieren
    const byGenre = {};
    tracks.forEach((t) => { (byGenre[t.track_genre] ||= []).push(t); });
    STATE.cache.byGenre = byGenre;

    // Genre-Dropdown
    const eg = $("#expGenre");
    eg.innerHTML = "";
    Object.keys(byGenre).sort().forEach((g) => {
      const o = document.createElement("option"); o.value = g; o.textContent = g; eg.appendChild(o);
    });
    eg.addEventListener("change", fillSongs);
    $("#expSong").addEventListener("change", showSong);

    // Glossar
    renderGlossary(glossary);

    fillSongs();
  } catch (err) {
    $("#songCard").innerHTML = `<div class="loading">Fehler: ${err.message}</div>`;
  }
}

function fillSongs() {
  const g = $("#expGenre").value;
  const list = (STATE.cache.byGenre[g] || []).slice().sort((a, b) => a.rank_in_genre - b.rank_in_genre);
  const es = $("#expSong");
  es.innerHTML = list.map((t) =>
    `<option value="${t.track_id}">#${t.rank_in_genre} · ${esc(t.track_name)} — ${esc(t.artists)}</option>`
  ).join("");
  if (list.length) { es.value = list[0].track_id; showSong(); }
}

function showSong() {
  const id = $("#expSong").value;
  const g = $("#expGenre").value;
  const t = (STATE.cache.byGenre[g] || []).find((x) => x.track_id === id);
  if (!t) return;

  const KEYS = ["C","C♯/D♭","D","D♯/E♭","E","F","F♯/G♭","G","G♯/A♭","A","A♯/B♭","H/B"];
  const keyName = t.key >= 0 && t.key < 12 ? KEYS[t.key] : "–";
  const modeName = t.mode === 1 ? "Dur" : "Moll";

  // Initialen fuers Cover
  const initials = esc(t.track_name.trim().slice(0, 2).toUpperCase());
  // Rang als Prozent (Platz 1 = 100%)
  const rankPct = Math.max(2, 100 * (1 - (t.rank_in_genre - 1) / Math.max(1, t.genre_size - 1)));
  // Interpretation ggü. Genre
  const interp = buildInterpretation(t, g);

  $("#songCard").innerHTML = `
    <div class="sc-header">
      <div class="sc-cover">${initials}</div>
      <div class="sc-headinfo">
        <div class="sc-song">${esc(t.track_name)}</div>
        <div class="sc-artist">${esc(t.artists)}</div>
        <div class="sc-sub"><span class="sc-tag">Album</span> ${esc(t.album_name)}</div>
        <div class="sc-sub"><span class="sc-tag">Genre</span> ${esc(t.track_genre)}</div>
      </div>
    </div>

    <div class="sc-rankblock">
      <div class="sc-rankrow">
        <span>Rang im Genre</span>
        <strong>#${t.rank_in_genre} <span class="sc-dim">/ ${t.genre_size}</span></strong>
      </div>
      <div class="sc-bar"><div class="sc-bar-fill" style="width:${rankPct.toFixed(1)}%"></div></div>
      <div class="sc-rankrow sc-small">
        <span>Popularität</span><strong>${t.popularity} <span class="sc-dim">/ 100</span></strong>
      </div>
    </div>

    <div class="song-meta">
      <div class="box"><div class="k">Dauer</div><div class="v">${t.duration_min.toFixed(2)}<span class="u"> min</span></div></div>
      <div class="box"><div class="k">Tempo</div><div class="v">${Math.round(t.tempo)}<span class="u"> BPM</span></div></div>
      <div class="box"><div class="k">Tonart</div><div class="v">${keyName}<span class="u"> ${modeName}</span></div></div>
      <div class="box"><div class="k">Takt</div><div class="v">${t.time_signature}<span class="u">/4</span></div></div>
    </div>

    <div class="sc-interp">${interp}</div>`;

  renderRadar(t, g);
}

// erzeugt einen kurzen Satz, wie sich der Song vom Genre unterscheidet
function buildInterpretation(t, g) {
  const list = STATE.cache.byGenre[g] || [];
  const avg = (f) => list.reduce((s, x) => s + x[f], 0) / list.length;
  const diffs = [
    { f: "valence", hi: "fröhlicher", lo: "melancholischer" },
    { f: "energy", hi: "energiegeladener", lo: "ruhiger" },
    { f: "danceability", hi: "tanzbarer", lo: "weniger tanzbar" },
    { f: "acousticness", hi: "akustischer", lo: "weniger akustisch" },
  ].map((d) => ({ ...d, delta: t[d.f] - avg(d.f) }));
  // die zwei staerksten Abweichungen
  diffs.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  const phrases = diffs.slice(0, 2).map((d) =>
    Math.abs(d.delta) < 0.03 ? null : (d.delta > 0 ? d.hi : d.lo)
  ).filter(Boolean);
  if (!phrases.length) return `Dieser Song klingt sehr typisch für <b>${esc(g)}</b>.`;
  return `Im Vergleich zu typischen <b>${esc(g)}</b>-Songs ist dieser Track ${phrases.join(" und ")}.`;
}

function renderRadar(t, g) {
  const feats = ["danceability","energy","valence","acousticness","instrumentalness","speechiness","liveness"];
  const list = STATE.cache.byGenre[g] || [];
  const avg = feats.map((f) => list.reduce((s, x) => s + x[f], 0) / list.length);
  const song = feats.map((f) => t[f]);

  const BLUE = "#4d9fff";  // Genre-Durchschnitt (statt blau)

  const songHover = feats.map((f, i) =>
    `<b>${f}</b><br>Song: ${song[i].toFixed(2)}<br>Genre-Ø: ${avg[i].toFixed(2)}`);
  const avgHover = feats.map((f, i) =>
    `<b>${f}</b><br>Genre-Ø: ${avg[i].toFixed(2)}<br>Song: ${song[i].toFixed(2)}`);

  Plotly.react("songRadar", [
    { type: "scatterpolar", r: [...song, song[0]], theta: [...feats, feats[0]],
      fill: "toself", name: "Song", line: { color: C.green, width: 2.5 },
      fillcolor: "rgba(29,185,84,0.28)",
      marker: { size: 7, color: C.green },
      text: [...songHover, songHover[0]], hovertemplate: "%{text}<extra></extra>" },
    { type: "scatterpolar", r: [...avg, avg[0]], theta: [...feats, feats[0]],
      fill: "toself", name: "Genre-Ø", line: { color: BLUE, width: 2.5 },
      fillcolor: "rgba(77,159,255,0.15)",
      marker: { size: 7, color: BLUE },
      text: [...avgHover, avgHover[0]], hovertemplate: "%{text}<extra></extra>" },
  ], baseLayout({
      margin: { l: 70, r: 70, t: 50, b: 50 },
      paper_bgcolor: "rgba(0,0,0,0)",
      polar: {
        bgcolor: "rgba(0,0,0,0)",
        radialaxis: { range: [0, 1], gridcolor: C.border,
                      tickfont: { color: C.dim, size: 10 } },
        angularaxis: { gridcolor: C.border,
                       tickfont: { color: C.text, size: 13 } },
      },
      legend: {
        orientation: "v", x: 1.02, y: 1.1,
        xanchor: "left", yanchor: "top",
        font: { size: 12, color: C.text },
        bgcolor: "rgba(22,27,34,0.6)", bordercolor: C.border, borderwidth: 1,
      },
      showlegend: true,
    }),
    PLOT_CONFIG);
}

function renderGlossary(glossary) {
  $("#glossaryTable").innerHTML = `
    <table>
      <thead><tr><th>Feature</th><th>Bereich</th><th>Bedeutung</th></tr></thead>
      <tbody>
        ${glossary.map((g) => `
          <tr><td>${esc(g.feature)}</td><td>${esc(g.range)}</td><td>${esc(g.erklaerung)}</td></tr>
        `).join("")}
      </tbody>
    </table>`;
}

// ---------- Feature-Tabelle + ähnlichste Genres ----------
function renderGenreTables(genre, g) {
  const meta = {
    danceability:   "Wie gut geeignet zum Tanzen",
    energy:         "Intensität und Aktivität",
    speechiness:    "Anteil gesprochener Sprache",
    acousticness:   "Wahrscheinlichkeit akustischer Klänge",
    instrumentalness:"Wahrscheinlichkeit ohne Gesang",
    liveness:       "Klingt wie Live-Aufnahme",
    valence:        "Positive / fröhliche Stimmung",
  };
  const label = (v) =>
    v >= 0.66 ? "Hoch" : v >= 0.4 ? "Mittel" : v >= 0.15 ? "Niedrig" : "Sehr niedrig";

  // Feature-Übersicht
  const ft = document.getElementById("genreFeatureTable");
  if (ft) ft.innerHTML = `
    <table>
      <thead><tr><th>Feature</th><th>Wert</th><th>Einschätzung</th><th>Bedeutung</th></tr></thead>
      <tbody>
        ${Object.keys(meta).map((f) => `
          <tr><td>${f}</td><td>${g[f].toFixed(3)}</td><td>${label(g[f])}</td><td>${meta[f]}</td></tr>
        `).join("")}
      </tbody>
    </table>`;

  // Ähnlichste Genres (euklidische Distanz über die Features)
  const feats = Object.keys(meta);
  const stats = STATE.cache.genre_stats || [];
  const dist = stats
    .filter((x) => x.track_genre !== genre)
    .map((x) => ({
      genre: x.track_genre,
      d: Math.sqrt(feats.reduce((s, f) => s + (x[f] - g[f]) ** 2, 0)),
    }))
    .sort((a, b) => a.d - b.d)
    .slice(0, 10);

  const top = dist.slice(0, 10).reverse();
  Plotly.react("genreSimilarPlot", [{
    type: "bar", orientation: "h",
    x: top.map((d) => d.d),
    y: top.map((d) => d.genre),
    marker: { color: C.green },
    hovertemplate: "%{y}: Distanz %{x:.3f}<extra></extra>",
  }], baseLayout({
      margin: { l: 90, r: 15, t: 6, b: 30 },
      xaxis: { title: { text: "Distanz (klein = ähnlich)", font: { size: 10 } }, gridcolor: C.border },
      yaxis: { gridcolor: "rgba(0,0,0,0)", tickfont: { size: 11 } },
    }), PLOT_CONFIG);
}

// ---------- Cluster-Legende mit Farbe, Erklärung, Genre-Liste ----------
function renderClusterLegend(gmap) {
  const el = document.getElementById("clusterLegend");
  if (!el) return;

  // gleiche Farben wie die Genre-Map (Plotly "Bold"-Palette)
  const PALETTE = ["#7F3C8D","#11A579","#3969AC","#F2B701","#E73F74","#80BA5A",
                   "#E68310","#008695","#CF1C90","#F97B72"];

  // Genres nach Cluster gruppieren
  const byCluster = {};
  gmap.points.forEach((p) => { (byCluster[p.cluster] ||= []).push(p); });

  // für jede Gruppe die prägende Eigenschaft bestimmen (für die Kurz-Erklärung)
  const beschreibung = (genres) => {
    // Durchschnitts-Features dieser Gruppe aus genre_stats
    const stats = STATE.cache.genre_stats || [];
    const names = genres.map((g) => g.genre);
    const sub = stats.filter((s) => names.includes(s.track_genre));
    if (!sub.length) return "";
    const avg = (f) => sub.reduce((s, x) => s + x[f], 0) / sub.length;
    const e = avg("energy"), a = avg("acousticness"), v = avg("valence"),
          i = avg("instrumentalness"), sp = avg("speechiness");
    if (sp > 0.15) return "Viel gesprochene Sprache (z. B. Comedy)";
    if (i > 0.5)   return "Instrumental, oft ohne Gesang";
    if (a > 0.5)   return "Ruhig und akustisch";
    if (e > 0.72)  return "Laut und energiegeladen";
    if (v > 0.6)   return "Fröhlich und tanzbar";
    return "Ausgewogene Mainstream-Klänge";
  };

  const ids = Object.keys(byCluster).sort((a, b) => a - b);
  el.innerHTML = ids.map((cid) => {
    const genres = byCluster[cid].map((p) => p.genre).sort();
    const color = byCluster[cid][0].color;
    const desc = beschreibung(byCluster[cid]);
    return `
      <div class="cluster-card" data-cluster="${cid}"
           style="background:${color}22; border-left-color:${color}">
        <div class="cluster-head">
          <span class="cluster-dot" style="background:${color}"></span>
          <span class="cluster-title">${esc(byCluster[cid][0].cluster_name)}</span>
          <span class="cluster-count">${genres.length} Genres</span>
        </div>
        <div class="cluster-genres">${genres.map((g) => esc(g)).join(", ")}</div>
      </div>`;
  }).join("");

  // interaktiv: Klick klappt die Genre-Liste auf/zu
  el.querySelectorAll(".cluster-card").forEach((card) => {
    card.addEventListener("click", () => card.classList.toggle("open"));
  });
}

// ---------- Sicherheit: HTML escapen ----------
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
// ---------- Genre-Radar auf der Genre-Seite ----------
function initGenreRadar() {
  const sel = document.getElementById("genreRadarSel");
  if (!sel || !STATE.cache.genre_stats) return;
  const stats = STATE.cache.genre_stats.slice().sort((a, b) =>
    a.track_genre.localeCompare(b.track_genre));
  sel.innerHTML = stats.map((g) =>
    `<option value="${esc(g.track_genre)}">${esc(g.track_genre)}</option>`).join("");
  sel.addEventListener("change", () => renderGenreRadar(sel.value));
  renderGenreRadar(stats[0].track_genre);
}

function renderGenreRadar(genre) {
  const feats = ["danceability","energy","valence","acousticness","instrumentalness","speechiness","liveness"];
  const stats = STATE.cache.genre_stats || [];
  const g = stats.find((x) => x.track_genre === genre);
  if (!g) return;
  // Gesamtdurchschnitt ueber alle Genres
  const overall = feats.map((f) => stats.reduce((s, x) => s + x[f], 0) / stats.length);
  const gv = feats.map((f) => g[f]);
  renderGenreTables(genre, g);

  const gHover = feats.map((f, i) =>
    `<b>${f}</b><br>${esc(genre)}: ${gv[i].toFixed(2)}<br>Ø alle: ${overall[i].toFixed(2)}`);

  Plotly.react("genreRadar", [
    { type: "scatterpolar", r: [...gv, gv[0]], theta: [...feats, feats[0]],
      fill: "toself", name: esc(genre), line: { color: C.green, width: 2.5 },
      fillcolor: "rgba(29,185,84,0.28)", marker: { size: 7, color: C.green },
      text: [...gHover, gHover[0]], hovertemplate: "%{text}<extra></extra>" },
    { type: "scatterpolar", r: [...overall, overall[0]], theta: [...feats, feats[0]],
      fill: "toself", name: "Spotify-Ø", line: { color: "#8b949e", width: 2, dash: "dash" },
      fillcolor: "rgba(139,148,158,0.10)", marker: { size: 5, color: "#8b949e" },
      hoverinfo: "skip" },
  ], baseLayout({
      margin: { l: 70, r: 70, t: 40, b: 40 },
      paper_bgcolor: "rgba(0,0,0,0)",
      polar: { bgcolor: "rgba(0,0,0,0)",
        radialaxis: { range: [0, 1], gridcolor: C.border, tickfont: { color: C.dim, size: 10 } },
        angularaxis: { gridcolor: C.border, tickfont: { color: C.text, size: 12 } } },
      legend: { orientation: "v", x: 1.02, y: 1.1, xanchor: "left", yanchor: "top",
        font: { size: 12, color: C.text },
        bgcolor: "rgba(22,27,34,0.6)", bordercolor: C.border, borderwidth: 1 },
      showlegend: true,
    }), PLOT_CONFIG);

}