"""
============================================================
 DATEI 02: KORRELATIONEN (DuckDB -> JSON)
============================================================
Beantwortet:
  - Frage 7 & 9  : Welche Features haengen zusammen? (Korrelationsmatrix)
  - Frage 5 & 10 : Welche Features korrelieren mit Popularitaet?

WICHTIG - Datenbasis:
  Korrelationen sind SONG-Analysen -> deduplizierte Song-Ebene.
  Ein Song (track_name + artists) zaehlt genau EINMAL (Zeile mit
  hoechster Popularitaet), sonst verwaessern mehrfach gelistete
  Multi-Genre-Hits die Korrelationen.

Methodik:
  - Pearson  = linearer Zusammenhang (Hauptmass)
  - Spearman = Rang-Zusammenhang (robust gegen Schiefe/Ausreisser)
  Beide werden exportiert; im Dashboard nutzen wir Pearson,
  Spearman dient als Robustheits-Check.

Ausgaben in ./export/ :
  - correlation_matrix.json  : volle Feature-x-Feature-Matrix (Pearson)
  - correlation_popularity.json : Korrelation jedes Features mit popularity
  - (optional) correlation_matrix.png : statischer Kontroll-Plot
============================================================
"""

import duckdb
import pandas as pd
import numpy as np
import json
import os

# ------------------------------------------------------------
# PFADE  (auf deinem Rechner anpassen)
# ------------------------------------------------------------
DB_PFAD     = r"C:\Users\Datas\Desktop\New folder\spotify.duckdb"
EXPORT_DIR  = r"C:\Users\Datas\Desktop\New folder\export"

# Auf deinem Rechner z.B.:
# DB_PFAD    = r"C:\Users\Datas\Desktop\spotify-dashboard\spotify.duckdb"
# EXPORT_DIR = r"C:\Users\Datas\Desktop\spotify-dashboard\export"

# statischen PNG-Plot zusaetzlich erzeugen? (braucht matplotlib + seaborn)
MAKE_PNG = True

os.makedirs(EXPORT_DIR, exist_ok=True)

# ------------------------------------------------------------
# FEATURES
# ------------------------------------------------------------
# Reihenfolge bestimmt spaeter die Anordnung in der Heatmap.
FEATURES = [
    "popularity",
    "danceability", "energy", "loudness", "valence",
    "acousticness", "instrumentalness", "speechiness",
    "liveness", "tempo", "duration_min",
    "explicit", "mode", "time_signature", "key",
]


def speichern(name, daten):
    pfad = os.path.join(EXPORT_DIR, name)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    print(f"  -> gespeichert: {name}")


# ------------------------------------------------------------
# DATEN LADEN (dedupliziert!)
# ------------------------------------------------------------
con = duckdb.connect(DB_PFAD, read_only=True)
df = con.execute("""
    SELECT DISTINCT ON (track_name, artists) *
    FROM tracks
    ORDER BY track_name, artists, popularity DESC
""").df()
con.close()

print(f"Songs geladen (dedupliziert): {len(df):,}")

# nur vorhandene Features, bool -> int (explicit)
FEATURES = [f for f in FEATURES if f in df.columns]
if df["explicit"].dtype == bool:
    df["explicit"] = df["explicit"].astype(int)

data = df[FEATURES].dropna()
print(f"Zeilen fuer Korrelation (ohne NaN): {len(data):,}")


# ------------------------------------------------------------
# 1) KORRELATIONSMATRIX (Pearson)  -> correlation_matrix.json  (F7, F9)
# ------------------------------------------------------------
print("\n[1] Korrelationsmatrix (Pearson) ...")
corr = data.corr(method="pearson").round(3)

# Export im dashboard-freundlichen Format: Labels + 2D-Werteliste
matrix_export = {
    "method":   "pearson",
    "labels":   list(corr.columns),
    "matrix":   corr.values.tolist(),
}
speichern("correlation_matrix.json", matrix_export)

# staerkste Feature-Paare (ohne Diagonale, ohne popularity-Zeile doppelt)
print("Staerkste Feature-Paare (|r| absteigend):")
paare = []
cols = list(corr.columns)
for i in range(len(cols)):
    for j in range(i + 1, len(cols)):
        paare.append((cols[i], cols[j], corr.iloc[i, j]))
paare.sort(key=lambda x: abs(x[2]), reverse=True)
for a, b, r in paare[:8]:
    print(f"  {a:<16} <-> {b:<16} r = {r:+.3f}")


# ------------------------------------------------------------
# 2) KORRELATION MIT POPULARITAET  -> correlation_popularity.json (F5, F10)
# ------------------------------------------------------------
print("\n[2] Korrelation jedes Features mit popularity ...")

pearson  = data.corr(method="pearson")["popularity"].drop("popularity")
spearman = data.corr(method="spearman")["popularity"].drop("popularity")

pop_corr = pd.DataFrame({
    "pearson":  pearson.round(4),
    "spearman": spearman.round(4),
})
# nach Betrag der Pearson-Korrelation sortieren (staerkster Zusammenhang zuerst)
pop_corr = pop_corr.reindex(
    pop_corr["pearson"].abs().sort_values(ascending=False).index
)

print(pop_corr.to_string())

pop_export = [
    {
        "feature":  feat,
        "pearson":  float(row["pearson"]),
        "spearman": float(row["spearman"]),
    }
    for feat, row in pop_corr.iterrows()
]
speichern("correlation_popularity.json", pop_export)

# kleiner interpretierender Hinweis in der Konsole
staerkste = pop_export[0]
print(f"\nHinweis: staerkste Korrelation mit Popularitaet = "
      f"{staerkste['feature']} (r={staerkste['pearson']:+.3f}).")
print("Alle Korrelationen sind schwach (|r| < 0.2) -> kein einzelnes Feature")
print("erklaert Popularitaet linear. -> Random Forest (Datei 03) sucht")
print("nichtlineare Feature-Kombinationen.")


# ------------------------------------------------------------
# 3) OPTIONAL: statischer Kontroll-Plot  -> correlation_matrix.png
# ------------------------------------------------------------
if MAKE_PNG:
    try:
        import matplotlib
        matplotlib.use("Agg")  # kein Fenster, nur Datei
        import matplotlib.pyplot as plt
        import seaborn as sns
        from matplotlib.colors import LinearSegmentedColormap

        print("\n[3] Erzeuge statischen Kontroll-Plot ...")
        BG, AX_BG, TEXT, GREEN = "#0d1117", "#161b22", "#e6edf3", "#1DB954"
        cmap = LinearSegmentedColormap.from_list(
            "red_white_green", ["#ff4d4d", "#2b2b2b", GREEN]
        )
        mask = np.triu(np.ones_like(corr, dtype=bool), k=1)

        fig, ax = plt.subplots(figsize=(11, 11))
        fig.patch.set_facecolor(BG)
        ax.set_facecolor(AX_BG)
        sns.heatmap(
            corr, mask=mask, cmap=cmap, vmin=-1, vmax=1, center=0,
            annot=True, fmt=".2f",
            annot_kws={"size": 8, "color": TEXT, "weight": "bold"},
            linewidths=0.5, linecolor="#30363d", square=True,
            cbar_kws={"shrink": 0.8}, ax=ax,
        )
        # schwache Zellen abdunkeln (dein Detail)
        for i in range(len(corr)):
            for j in range(len(corr)):
                if j <= i and abs(corr.iloc[i, j]) < 0.2:
                    ax.add_patch(plt.Rectangle((j, i), 1, 1, fill=True,
                                               color="black", alpha=0.15))
        ax.set_title("Spotify Audio Features - Correlation (Pearson, dedupliziert)",
                     color=GREEN, fontsize=14, pad=15)
        plt.xticks(rotation=45, ha="right", color=TEXT)
        plt.yticks(color=TEXT, rotation=0)
        plt.tight_layout()
        out = os.path.join(EXPORT_DIR, "correlation_matrix.png")
        plt.savefig(out, dpi=130, facecolor=BG)
        plt.close()
        print(f"  -> gespeichert: correlation_matrix.png")
    except ImportError:
        print("\n[3] matplotlib/seaborn nicht installiert -> PNG uebersprungen.")
        print("    (pip install matplotlib seaborn)  - JSONs sind trotzdem fertig.")


print("\n=== DATEI 02 FERTIG ===")
print(f"Alle Ausgaben liegen in: {EXPORT_DIR}")
