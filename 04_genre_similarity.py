"""
============================================================
 DATEI 04: GENRE-AEHNLICHKEIT & TRACK-EXPLORER
============================================================
Beantwortet:
  - Frage 6  : Welche Genres sind ruhig / energiegeladen? = Aehnlichkeit
  - Frage 13 : Track-Level Exploration (einzelnen Song ansehen)

Datenbasis:
  - Genre-Aehnlichkeit  -> ALLE Zeilen (Genre-Analyse: Song zaehlt in
                           jedem seiner Genres)
  - Track-Explorer      -> DEDUPLIZIERTE Songs (jeder Song einmal)

Methodik Genre-Aehnlichkeit:
  1. Pro Genre die Durchschnitts-Features berechnen
  2. Features standardisieren (StandardScaler), damit alle gleich zaehlen
  3. Cosine-Similarity zwischen den Genre-Vektoren
  4. Energie-Index (ruhig -> energiegeladen) aus energy/loudness/acousticness

Ausgaben in ./export/ :
  - genre_similarity.json  : Aehnlichkeitsmatrix (Top 30 Genres) + aehnlichste Paare
  - genre_energy_rank.json : alle 115 Genres von ruhig -> energiegeladen
  - tracks_explorer.json   : Top 100 Songs je Genre, mit echtem Rang im Genre
  - feature_glossary.json  : Erklaerungen aller Features (fuer Frage 13-Tabelle)
============================================================
"""

import duckdb
import pandas as pd
import numpy as np
import json
import os
import plotly.express as px

from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans

# ------------------------------------------------------------
# PFADE (auf deinem Rechner anpassen)
# ------------------------------------------------------------

DB_PFAD    = r"C:\Users\Datas\Desktop\New folder\spotify.duckdb"
EXPORT_DIR = r"C:\Users\Datas\Desktop\New folder\export"

TOP_N_PER_GENRE   = 100   # Songs je Genre fuer den Explorer
HEATMAP_N_GENRES  = 30    # groesste Genres in der Aehnlichkeits-Heatmap

os.makedirs(EXPORT_DIR, exist_ok=True)

# Features fuer die Genre-Aehnlichkeit (klanglich relevant)
SIM_FEATURES = [
    "danceability", "energy", "loudness", "valence",
    "acousticness", "instrumentalness", "speechiness",
    "liveness", "tempo",
]


def speichern(name, daten):
    pfad = os.path.join(EXPORT_DIR, name)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    print(f"  -> gespeichert: {name}")


con = duckdb.connect(DB_PFAD, read_only=True)

# ------------------------------------------------------------
# 1) GENRE-DURCHSCHNITTE (alle Zeilen)   -> Basis fuer F6
# ------------------------------------------------------------
print("[1] Genre-Durchschnitte berechnen ...")
avg_sel = ", ".join([f"AVG({f}) AS {f}" for f in SIM_FEATURES])
genre_df = con.execute(f"""
    SELECT
        track_genre,
        COUNT(*)          AS n_tracks,
        AVG(popularity)   AS avg_popularity,
        {avg_sel}
    FROM tracks
    GROUP BY track_genre
    ORDER BY track_genre
""").df()
print(f"  {len(genre_df)} Genres")

# Features standardisieren
X = StandardScaler().fit_transform(genre_df[SIM_FEATURES])

# ------------------------------------------------------------
# 2) AEHNLICHKEITSMATRIX (Cosine)   -> genre_similarity.json  (F6)
# ------------------------------------------------------------
print("\n[2] Genre-Aehnlichkeit (Cosine) ...")
sim = cosine_similarity(X)

# aehnlichste Paare (ueber ALLE 115 Genres)
paare = []
namen = genre_df["track_genre"].tolist()
for i in range(len(namen)):
    for j in range(i + 1, len(namen)):
        paare.append({"a": namen[i], "b": namen[j],
                      "similarity": round(float(sim[i, j]), 4)})
paare.sort(key=lambda p: p["similarity"], reverse=True)

print("  Aehnlichste Genre-Paare:")
for p in paare[:6]:
    print(f"    {p['a']} <-> {p['b']}: {p['similarity']:.3f}")

# Heatmap-Anzeige auf die groessten Genres begrenzen (uebersichtlich)
top_genres = (genre_df.sort_values("n_tracks", ascending=False)
              .head(HEATMAP_N_GENRES)["track_genre"].tolist())
idx = [namen.index(g) for g in top_genres]
sub = sim[np.ix_(idx, idx)]

similarity_export = {
    "heatmap": {
        "labels": top_genres,
        "matrix": np.round(sub, 3).tolist(),
        "note": f"Cosine-Aehnlichkeit der {HEATMAP_N_GENRES} groessten Genres "
                f"(Berechnung ueber alle 115).",
    },
    "most_similar_pairs": paare[:20],
}
speichern("genre_similarity.json", similarity_export)

# ------------------------------------------------------------
# 3) ENERGIE-RANKING ruhig -> energiegeladen  (F6)
# ------------------------------------------------------------
print("\n[3] Ranking ruhig -> energiegeladen ...")
# Energie-Index aus z-standardisierten Werten:
#  + energy, + loudness, - acousticness  (akustisch = ruhig)
z = pd.DataFrame(
    StandardScaler().fit_transform(genre_df[["energy", "loudness", "acousticness"]]),
    columns=["energy", "loudness", "acousticness"],
)
genre_df["energy_index"] = (
    0.5 * z["energy"] + 0.3 * z["loudness"] - 0.2 * z["acousticness"]
).round(4)

energy_rank = genre_df.sort_values("energy_index")[
    ["track_genre", "n_tracks", "avg_popularity", "energy", "loudness",
     "acousticness", "energy_index"]
].copy()
energy_rank["avg_popularity"] = energy_rank["avg_popularity"].round(2)
for c in ["energy", "loudness", "acousticness"]:
    energy_rank[c] = energy_rank[c].round(4)

print("  Ruhigste:", energy_rank.head(5)["track_genre"].tolist())
print("  Energiegeladenste:", energy_rank.tail(5)["track_genre"].tolist())

speichern("genre_energy_rank.json", energy_rank.to_dict(orient="records"))

# ------------------------------------------------------------
# 3b) GENRE-MAP (PCA + KMeans)  -> genre_map.json   (F6, 2D-Karte)
# ------------------------------------------------------------
# Idee: Genres als Punkte auf einer 2D-Karte. Naehe = klangliche Aehnlichkeit.
#   PCA reduziert die 9 Features auf 2 Achsen.
#   KMeans gruppiert Genres in Klang-Familien (Farben).
print("\n[3b] Genre-Map (PCA + KMeans) ...")
X_full = StandardScaler().fit_transform(genre_df[SIM_FEATURES])

pca = PCA(n_components=2, random_state=42)
coords = pca.fit_transform(X_full)
var = pca.explained_variance_ratio_
print(f"  Erklaerte Varianz: PC1={var[0]*100:.0f}%, PC2={var[1]*100:.0f}%")

N_CLUSTER = 6
clusters = KMeans(n_clusters=N_CLUSTER, random_state=42, n_init=10).fit_predict(X_full)

# --- Cluster-Namen aus dem Klang-Profil ableiten (eindeutig) ---
cluster_names = {}
for c in range(N_CLUSTER):
    sub = genre_df[clusters == c]
    if len(sub) == 0:
        cluster_names[c] = f"Gruppe {c+1}"; continue
    e = sub["energy"].mean(); a = sub["acousticness"].mean()
    ins = sub["instrumentalness"].mean(); n = len(sub)
    if n == 1:
        g = sub["track_genre"].iloc[0]
        cluster_names[c] = ("Naturklänge" if g == "nature_sounds"
                            else "Sprache/Comedy" if g == "comedy" else g.capitalize())
    elif ins > 0.4 and a > 0.4:
        cluster_names[c] = "Ruhig & Instrumental"
    elif e > 0.75:
        cluster_names[c] = "Laut & Energetisch"
    elif e > 0.6 and a < 0.35:
        cluster_names[c] = "Rhythmisch/Modern"
    else:
        cluster_names[c] = "Ausgewogen/Organisch"

# --- Cluster-Farben exakt wie plotly.express "Bold" ---
BOLD = ["#7F3C8D","#11A579","#3969AC","#F2B701","#E73F74","#80BA5A",
        "#E68310","#008695","#CF1C90","#F97B72","#4B4B8F","#A5AA99"]
cluster_order = []
for c in clusters:
    if c not in cluster_order:
        cluster_order.append(c)
cluster_color = {c: BOLD[i % len(BOLD)] for i, c in enumerate(cluster_order)}

# Achsen-Interpretation automatisch aus den staerksten Ladungen ableiten
load = pd.DataFrame(pca.components_.T, index=SIM_FEATURES, columns=["PC1", "PC2"])
pc1_pos = load["PC1"].idxmax(); pc1_neg = load["PC1"].idxmin()
pc2_pos = load["PC2"].idxmax(); pc2_neg = load["PC2"].idxmin()

genre_map = {
    "variance": {"pc1": round(float(var[0]), 4), "pc2": round(float(var[1]), 4)},
    "axis": {
        "x_neg": pc1_neg, "x_pos": pc1_pos,   # z.B. acousticness <-> loudness
        "y_neg": pc2_neg, "y_pos": pc2_pos,
    },
    "points": [
        {
            "genre":  genre_df["track_genre"].iloc[i],
            "x":      round(float(coords[i, 0]), 3),
            "y":      round(float(coords[i, 1]), 3),
            "cluster": int(clusters[i]),
            "cluster_name": cluster_names[clusters[i]],
            "color": cluster_color[clusters[i]],
            "n_tracks": int(genre_df["n_tracks"].iloc[i]),
            "avg_popularity": round(float(genre_df["avg_popularity"].iloc[i]), 1),
        }
        for i in range(len(genre_df))
    ],
}
print(f"  X-Achse: {pc1_neg} <-> {pc1_pos}")
print(f"  Y-Achse: {pc2_neg} <-> {pc2_pos}")
speichern("genre_map.json", genre_map)

# ------------------------------------------------------------
# 4) TRACK-EXPLORER: Top 100 je Genre + echter Rang  (F13)
# ------------------------------------------------------------
print(f"\n[4] Track-Explorer: Top {TOP_N_PER_GENRE} Songs je Genre ...")
explorer = con.execute(f"""
    WITH dedup AS (
        SELECT DISTINCT ON (track_name, artists) *
        FROM tracks
        ORDER BY track_name, artists, popularity DESC
    ),
    ranked AS (
        SELECT
            track_id, track_name, artists, album_name, track_genre,
            popularity, duration_min, danceability, energy, loudness,
            valence, acousticness, instrumentalness, speechiness,
            liveness, tempo, key, mode, time_signature, explicit,
            ROW_NUMBER() OVER (PARTITION BY track_genre
                               ORDER BY popularity DESC) AS rank_in_genre,
            COUNT(*)    OVER (PARTITION BY track_genre) AS genre_size
        FROM dedup
    )
    SELECT * FROM ranked
    WHERE rank_in_genre <= {TOP_N_PER_GENRE}
    ORDER BY track_genre, rank_in_genre
""").df()

# runden fuer kompaktere JSON
for c in ["duration_min", "danceability", "energy", "loudness", "valence",
          "acousticness", "instrumentalness", "speechiness", "liveness", "tempo"]:
    explorer[c] = explorer[c].round(4)
explorer["avg_genre_popularity"] = explorer["track_genre"].map(
    genre_df.set_index("track_genre")["avg_popularity"].round(2)
)

print(f"  Songs exportiert: {len(explorer):,} aus {explorer['track_genre'].nunique()} Genres")
speichern("tracks_explorer.json", explorer.to_dict(orient="records"))

con.close()

# ------------------------------------------------------------
# 5) FEATURE-GLOSSAR (Erklaerungen fuer die F13-Tabelle)
# ------------------------------------------------------------
print("\n[5] Feature-Glossar ...")
glossary = [
    {"feature": "danceability", "range": "0.0 - 1.0",
     "erklaerung": "Wie gut sich ein Song zum Tanzen eignet (Tempo, Rhythmus, Beat). 1.0 = sehr tanzbar."},
    {"feature": "energy", "range": "0.0 - 1.0",
     "erklaerung": "Intensitaet und Aktivitaet. Hohe Energie = schnell, laut, energisch (z.B. Metal)."},
    {"feature": "loudness", "range": "dB (meist -60 - 0)",
     "erklaerung": "Gesamtlautstaerke in Dezibel. Hoehere (weniger negative) Werte = lauter."},
    {"feature": "valence", "range": "0.0 - 1.0",
     "erklaerung": "Musikalische Positivitaet. Hoch = froehlich/euphorisch, niedrig = traurig/duester."},
    {"feature": "acousticness", "range": "0.0 - 1.0",
     "erklaerung": "Wahrscheinlichkeit, dass der Song akustisch ist. Nahe 1.0 = akustisch."},
    {"feature": "instrumentalness", "range": "0.0 - 1.0",
     "erklaerung": "Wahrscheinlichkeit, dass kein Gesang vorkommt. Nahe 1.0 = instrumental."},
    {"feature": "speechiness", "range": "0.0 - 1.0",
     "erklaerung": "Anteil gesprochener Worte. >0.66 = fast nur Sprache, 0.33-0.66 = z.B. Rap, <0.33 = Musik."},
    {"feature": "liveness", "range": "0.0 - 1.0",
     "erklaerung": "Wahrscheinlichkeit einer Live-Aufnahme (Publikum). >0.8 = sehr wahrscheinlich live."},
    {"feature": "tempo", "range": "BPM",
     "erklaerung": "Geschwindigkeit in Schlaegen pro Minute (Beats per Minute)."},
    {"feature": "duration_min", "range": "Minuten",
     "erklaerung": "Laenge des Songs in Minuten."},
    {"feature": "key", "range": "0 - 11",
     "erklaerung": "Tonart (Pitch Class): 0=C, 1=C#/Db, 2=D, 3=D#/Eb, 4=E, 5=F, "
                   "6=F#/Gb, 7=G, 8=G#/Ab, 9=A, 10=A#/Bb, 11=H/B. -1 = nicht erkannt."},
    {"feature": "mode", "range": "0 oder 1",
     "erklaerung": "Tongeschlecht: 1 = Dur (major), 0 = Moll (minor)."},
    {"feature": "time_signature", "range": "3 - 7",
     "erklaerung": "Taktart: z.B. 3 = 3/4-Takt, 4 = 4/4-Takt (der haeufigste)."},
    {"feature": "explicit", "range": "true/false",
     "erklaerung": "Ob der Song explizite (anstoessige) Texte enthaelt."},
    {"feature": "popularity", "range": "0 - 100",
     "erklaerung": "Spotify-Popularitaet, v.a. aus Anzahl + Aktualitaet der Wiedergaben. "
                   "100 = sehr populaer. Beachte: neuere Songs sind oft im Vorteil."},
]
speichern("feature_glossary.json", glossary)

# ------------------------------------------------------------
# GENRE-MAP als fertiges HTML (exakt wie plotly.express)
# ------------------------------------------------------------
print("\n[3c] Genre-Map als HTML exportieren ...")
BG, AX_BG, TEXT = "#0d1117", "#161b22", "#e6edf3"

genre_profile = con_df_profile = genre_df.set_index("track_genre")[SIM_FEATURES]
counts = genre_df.set_index("track_genre")["n_tracks"]
pops   = genre_df.set_index("track_genre")["avg_popularity"].round(1)

pca_df = pd.DataFrame({
    "Genre": genre_df["track_genre"].values,
    "PC1": coords[:, 0], "PC2": coords[:, 1],
    "Cluster": [f"Gruppe {c+1}" for c in clusters],
    "Tracks": counts.values,
    "Ø Popularity": pops.values,
})

fig = px.scatter(
    pca_df, x="PC1", y="PC2", color="Cluster", text="Genre",
    size="Ø Popularity", hover_name="Genre",
    hover_data={"PC1": False, "PC2": False, "Cluster": True, "Tracks": True, "Ø Popularity": True},
    color_discrete_sequence=px.colors.qualitative.Bold,
)
fig.update_traces(textposition="top center", textfont=dict(size=8),
                  marker=dict(opacity=0.85, line=dict(width=0.5, color="white")))
fig.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color=TEXT, height=480,
    xaxis=dict(title=f"← akustisch / ruhig          energetisch / laut →  ({var[0]*100:.0f}%)",
               gridcolor="#30363d", zerolinecolor="#30363d"),
    yaxis=dict(title=f"← instrumental          vokal / sprachreich →  ({var[1]*100:.0f}%)",
               gridcolor="#30363d", zerolinecolor="#30363d"),
    legend=dict(title="Klang-Gruppe", bgcolor=AX_BG, bordercolor="#30363d"),
    margin=dict(l=20, r=20, t=20, b=20),
)
html_fragment = fig.to_html(full_html=False, include_plotlyjs=False,
                            div_id="genreMapEmbed", config={"displayModeBar": False})
with open(os.path.join(EXPORT_DIR, "genre_map.html"), "w", encoding="utf-8") as f:
    f.write(html_fragment)
print("  -> gespeichert: genre_map.html")

print("\n=== DATEI 04 FERTIG ===")
print(f"Alle Ausgaben liegen in: {EXPORT_DIR}")
