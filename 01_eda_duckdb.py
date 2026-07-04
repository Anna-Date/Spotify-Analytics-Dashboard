"""
============================================================
 DATEI 01: EDA & DESKRIPTIVE ANALYSE (DuckDB -> JSON)
============================================================
Beantwortet die deskriptiven Fragen direkt per SQL:
  - Frage 1     : Top 10 Songs
  - Frage 2 & 8 : Populaer (Top 10%) vs. Rest  -> Feature-Vergleich
  - Frage 3 & 11: Populaerste Genres (Durchschnitt)

Zusaetzlich werden Daten fuer das Dashboard exportiert:
  - genres.json   : Genre-Liste fuer das Dropdown-Filter
  - overview.json : Kennzahlen fuer die Kopfzeile

Alle Ergebnisse werden als JSON in ./export/ gespeichert
und zur Kontrolle in der Konsole ausgegeben.
============================================================
"""

import duckdb
import json
import os

# ------------------------------------------------------------
# PFADE
# ------------------------------------------------------------
# Hier in der Testumgebung:
DB_PFAD     = r"C:\Users\Datas\Desktop\New folder\spotify.duckdb"
EXPORT_DIR  = r"C:\Users\Datas\Desktop\New folder\export"

# Auf deinem Rechner stattdessen z.B.:
# DB_PFAD    = r"C:\Users\Datas\DAV-Spotify\spotify.duckdb"
# EXPORT_DIR = r"C:\Users\Datas\DAV-Spotify\export"

os.makedirs(EXPORT_DIR, exist_ok=True)

# Populaer-Definition: Top 10 % (Perzentil 90)
POPULAR_QUANTILE = 0.90

# Audio-Features, die wir vergleichen
FEATURES = [
    "danceability", "energy", "loudness", "speechiness",
    "acousticness", "instrumentalness", "liveness",
    "valence", "tempo", "duration_min",
]


def speichern(name, daten):
    """Speichert ein Objekt als JSON in EXPORT_DIR."""
    pfad = os.path.join(EXPORT_DIR, name)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    print(f"  -> gespeichert: {name}")


# ------------------------------------------------------------
# VERBINDUNG
# ------------------------------------------------------------
con = duckdb.connect(DB_PFAD, read_only=True)

# ------------------------------------------------------------
# DEDUPLIZIERTE SONG-VIEW  (fuer alle SONG-bezogenen Analysen)
# ------------------------------------------------------------
# Ein Song (track_name + artists) taucht im Datensatz mehrfach auf,
# wenn er mehreren Genres zugeordnet ist. Die Audio-Features sind dabei
# identisch (dieselbe Aufnahme). Fuer Song-Analysen zaehlt jeder Song
# daher genau EINMAL - wir behalten die Zeile mit der hoechsten Popularitaet.
#
#   -> song_tracks : Song-Ebene (dedupliziert)   fuer Frage 1, 2, 8, ...
#   -> tracks      : Zuordnungs-Ebene (alle Zeilen) fuer Genre-Fragen 3, 11
#
# Hinweis: eine read-only-Verbindung kann keine echte VIEW speichern,
# darum nutzen wir eine CTE-Vorlage, die wir in die Abfragen einsetzen.
SONG_VIEW = """
    SELECT DISTINCT ON (track_name, artists) *
    FROM tracks
    ORDER BY track_name, artists, popularity DESC
"""

n_all  = con.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
n_song = con.execute(f"SELECT COUNT(*) FROM ({SONG_VIEW})").fetchone()[0]
print(f"Zeilen gesamt (Zuordnungs-Ebene): {n_all:,}")
print(f"Songs dedupliziert (Song-Ebene):  {n_song:,}")

# Schwellenwert (Top 10 %) auf SONG-EBENE berechnen
schwelle = con.execute(
    f"SELECT quantile_cont(popularity, ?) FROM ({SONG_VIEW})", [POPULAR_QUANTILE]
).fetchone()[0]
print(f"Populaer-Schwelle (Top 10%): popularity >= {schwelle}")


# ------------------------------------------------------------
# 0) OVERVIEW  -> overview.json
# ------------------------------------------------------------
print("\n[0] Overview-Kennzahlen ...")
row = con.execute(f"""
    SELECT
        (SELECT COUNT(*) FROM ({SONG_VIEW}))            AS n_songs,
        (SELECT COUNT(*) FROM tracks)                   AS n_rows,
        (SELECT COUNT(DISTINCT track_genre) FROM tracks) AS n_genres,
        (SELECT COUNT(DISTINCT artists) FROM tracks)    AS n_artists,
        (SELECT ROUND(AVG(popularity),2) FROM ({SONG_VIEW})) AS avg_popularity,
        (SELECT median(popularity) FROM ({SONG_VIEW}))  AS median_popularity,
        {schwelle}                                      AS popular_threshold
""").fetchone()

overview = {
    "n_songs":            int(row[0]),
    "n_rows":             int(row[1]),
    "n_genres":           int(row[2]),
    "n_artists":          int(row[3]),
    "avg_popularity":     float(row[4]),
    "median_popularity":  float(row[5]),
    "popular_threshold":  float(row[6]),
    "popular_definition": f"Top 10% (popularity >= {schwelle})",
}
print(f"  Songs (dedup): {overview['n_songs']:,} | Zeilen: {overview['n_rows']:,} "
      f"| Genres: {overview['n_genres']} | Artists: {overview['n_artists']:,}")
speichern("overview.json", overview)


# ------------------------------------------------------------
# 1) TOP 10 SONGS  -> top10.json   (Frage 1)
# ------------------------------------------------------------
print("\n[1] Top 10 Songs (dedupliziert) ...")
top10 = con.execute(f"""
    SELECT
        track_name,
        artists,
        album_name,
        track_genre,
        popularity
    FROM ({SONG_VIEW})
    ORDER BY popularity DESC, track_name ASC
    LIMIT 10
""").df()

print(top10.to_string(index=False))
speichern("top10.json", top10.to_dict(orient="records"))


# ------------------------------------------------------------
# 2) POPULAER vs. REST  -> popular_vs_rest.json   (Frage 2 & 8)
# ------------------------------------------------------------
print("\n[2] Populaer (Top 10%) vs. Rest - Feature-Vergleich (dedupliziert) ...")

# pro Feature den Mittelwert beider Gruppen
avg_select = ",\n        ".join(
    [f"ROUND(AVG({f}), 4) AS {f}" for f in FEATURES]
)

vergleich = con.execute(f"""
    WITH songs AS ({SONG_VIEW})
    SELECT
        CASE WHEN popularity >= {schwelle} THEN 'populaer' ELSE 'rest' END AS gruppe,
        COUNT(*) AS n,
        {avg_select}
    FROM songs
    GROUP BY gruppe
    ORDER BY gruppe
""").df()

print(vergleich.to_string(index=False))

# Standardabweichung pro Feature (ueber alle Songs) fuer die Effektgroesse
std_select = ",\n        ".join([f"stddev_samp({f}) AS {f}" for f in FEATURES])
std_row = con.execute(f"""
    WITH songs AS ({SONG_VIEW})
    SELECT {std_select} FROM songs
""").df().iloc[0]

pop_row  = vergleich[vergleich["gruppe"] == "populaer"].iloc[0]
rest_row = vergleich[vergleich["gruppe"] == "rest"].iloc[0]

# Effektgroesse (Cohen's d-Stil): (mean_pop - mean_rest) / std_gesamt
vergleich_export = {
    "n_popular": int(pop_row["n"]),
    "n_rest":    int(rest_row["n"]),
    "features": [
        {
            "feature":     f,
            "popular":     float(pop_row[f]),
            "rest":        float(rest_row[f]),
            "difference":  round(float(pop_row[f]) - float(rest_row[f]), 4),
            "effect_size": round(
                (float(pop_row[f]) - float(rest_row[f])) / float(std_row[f]), 4
            ) if float(std_row[f]) else 0.0,
        }
        for f in FEATURES
    ],
}
# nach Effektgroesse sortieren (staerkster Effekt zuerst)
vergleich_export["features"].sort(key=lambda x: abs(x["effect_size"]), reverse=True)

print("\nEffektgroesse (Sigma) - staerkste Unterschiede zuerst:")
for feat in vergleich_export["features"]:
    print(f"  {feat['feature']:<18} {feat['effect_size']:+.3f} sigma")

speichern("popular_vs_rest.json", vergleich_export)


# ------------------------------------------------------------
# 3) POPULAERSTE GENRES  -> genre_stats.json   (Frage 3 & 11)
# ------------------------------------------------------------
print("\n[3] Genre-Statistiken (Durchschnitt pro Genre) ...")
# HINWEIS: Genre-Analysen nutzen bewusst ALLE Zeilen (tracks), nicht die
# dedup-View - ein Song soll in jedem seiner Genres mitgezaehlt werden.

genre_avg_select = ",\n        ".join(
    [f"ROUND(AVG({f}), 4) AS {f}" for f in FEATURES]
)

genre_stats = con.execute(f"""
    SELECT
        track_genre,
        COUNT(*)                     AS n_tracks,
        ROUND(AVG(popularity), 2)    AS avg_popularity,
        {genre_avg_select}
    FROM tracks
    GROUP BY track_genre
    ORDER BY avg_popularity DESC
""").df()

print("Top 10 Genres nach Durchschnitts-Popularitaet:")
print(genre_stats.head(10)[
    ["track_genre", "n_tracks", "avg_popularity"]
].to_string(index=False))

speichern("genre_stats.json", genre_stats.to_dict(orient="records"))


# ------------------------------------------------------------
# 4) GENRE-LISTE (fuer Dashboard-Dropdown)  -> genres.json
# ------------------------------------------------------------
print("\n[4] Genre-Liste fuer Dashboard-Filter ...")
genres = con.execute("""
    SELECT DISTINCT track_genre
    FROM tracks
    ORDER BY track_genre
""").df()["track_genre"].tolist()

print(f"  {len(genres)} Genres exportiert")
speichern("genres.json", genres)


con.close()
print("\n=== DATEI 01 FERTIG ===")
print(f"Alle JSONs liegen in: {EXPORT_DIR}")
