"""
============================================================
 DATEI 03: RANDOM FOREST - Was erklaert Popularitaet? (Frage 4)
============================================================
Modell: RandomForestRegressor  (Popularitaet 0-100 als Zahl)

Beantwortet Frage 4 vollstaendig:
  - Welche Features erklaeren Popularitaet? (Feature Importance)
  - Sind die Ergebnisse representativ/stabil? (5-Fold Cross-Validation)
  - Alle Metriken: R^2, RMSE, MAE
  - Permutation Importance (robuster als Standard-Importance)

WICHTIG - Datenbasis: DEDUPLIZIERTE Song-Ebene!
  Grund: Derselbe Song steht mehrfach im Datensatz (mehrere Genres,
  identische Features). Ohne Deduplizierung landen Kopien desselben
  Songs gleichzeitig in Train UND Test -> "Data Leakage":
  das Modell lernt Songs auswendig und R^2 wird kuenstlich aufgeblaeht
  (0.54 statt ehrlicher 0.15). Deduplizieren verhindert das.

Methodik-Hinweise:
  - Standard-Importance ist bei korrelierten Features verzerrt
    (energy<->loudness r=0.76!). Darum zusaetzlich Permutation
    Importance auf den TESTdaten (nie auf Trainingsdaten messen).

Ausgaben in ./export/ :
  - rf_metrics.json           : R^2, RMSE, MAE, CV-Ergebnisse
  - rf_importance.json        : Standard + Permutation Importance
  - (optional) rf_importance.png, rf_cv.png : Kontroll-Plots
============================================================
"""

import duckdb
import pandas as pd
import numpy as np
import json
import os

from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from sklearn.inspection import permutation_importance
from sklearn.utils import resample

# ------------------------------------------------------------
# PFADE  (auf deinem Rechner anpassen)
# ------------------------------------------------------------
DB_PFAD     = r"C:\Users\Datas\Desktop\New folder\spotify.duckdb"
EXPORT_DIR  = r"C:\Users\Datas\Desktop\New folder\export"

MAKE_PNG = True
RANDOM_STATE = 42

# Cross-Validation: Anzahl Baeume pro Fold. 50 ist genau; wenn es dir zu
# langsam ist, auf 30 reduzieren (Ergebnis bleibt praktisch gleich stabil).
CV_TREES = 50

os.makedirs(EXPORT_DIR, exist_ok=True)

FEATURES = [
    "danceability", "energy", "mode", "speechiness", "acousticness",
    "instrumentalness", "liveness", "valence", "tempo", "duration_min",
    "time_signature", "explicit", "key", "loudness",
]


def speichern(name, daten):
    pfad = os.path.join(EXPORT_DIR, name)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    print(f"  -> gespeichert: {name}")


# ------------------------------------------------------------
# DATEN LADEN (dedupliziert - verhindert Data Leakage!)
# ------------------------------------------------------------
con = duckdb.connect(DB_PFAD, read_only=True)
df = con.execute("""
    SELECT DISTINCT ON (track_name, artists) *
    FROM tracks
    ORDER BY track_name, artists, popularity DESC
""").df()
con.close()
print(f"Songs geladen (dedupliziert): {len(df):,}")

df = df[FEATURES + ["popularity"]].copy()
if df["explicit"].dtype == bool:
    df["explicit"] = df["explicit"].astype(int)
df = df.dropna()

X = df[FEATURES]
y = df["popularity"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=RANDOM_STATE
)
print(f"Train: {len(X_train):,} | Test: {len(X_test):,}")


# ------------------------------------------------------------
# MODELL TRAINIEREN
# ------------------------------------------------------------
print("\n[1] Random Forest trainieren ...")
model = RandomForestRegressor(
    n_estimators=100, random_state=RANDOM_STATE, n_jobs=-1
)
model.fit(X_train, y_train)


# ------------------------------------------------------------
# METRIKEN
# ------------------------------------------------------------
print("\n[2] Metriken ...")
y_pred = model.predict(X_test)
r2   = r2_score(y_test, y_pred)
rmse = mean_squared_error(y_test, y_pred) ** 0.5
mae  = mean_absolute_error(y_test, y_pred)

print(f"  R^2  = {r2:.3f}  -> Modell erklaert {r2*100:.1f}% der Varianz")
print(f"  RMSE = {rmse:.2f} -> mittlerer Fehler +/- {rmse:.1f} Punkte")
print(f"  MAE  = {mae:.2f} -> durchschnittl. Fehler +/- {mae:.1f} Punkte")


# ------------------------------------------------------------
# CROSS-VALIDATION (Representativitaet / Stabilitaet)
# ------------------------------------------------------------
print("\n[3] 5-Fold Cross-Validation (Stabilitaetstest) ...")
cv_scores = cross_val_score(
    RandomForestRegressor(n_estimators=CV_TREES, random_state=RANDOM_STATE, n_jobs=-1),
    X, y, cv=5, scoring="r2",
)
cv_mean, cv_std = cv_scores.mean(), cv_scores.std()
for i, s in enumerate(cv_scores, 1):
    print(f"  Fold {i}: R^2 = {s:.3f}")
print(f"  Mittel: R^2 = {cv_mean:.3f} +/- {cv_std:.3f}")

if cv_std < 0.02:
    stabilitaet = "STABIL"
elif cv_std < 0.05:
    stabilitaet = "AKZEPTABEL"
else:
    stabilitaet = "INSTABIL"
print(f"  -> Ergebnis ist {stabilitaet}")

metrics_export = {
    "model": "RandomForestRegressor",
    "n_train": int(len(X_train)),
    "n_test":  int(len(X_test)),
    "r2":   round(float(r2), 4),
    "rmse": round(float(rmse), 3),
    "mae":  round(float(mae), 3),
    "cv_scores": [round(float(s), 4) for s in cv_scores],
    "cv_mean":   round(float(cv_mean), 4),
    "cv_std":    round(float(cv_std), 4),
    "stability": stabilitaet,
    "note": ("Deduplizierte Song-Ebene, um Data Leakage zu vermeiden. "
             "Niedriges R^2 ist ein ehrliches Ergebnis: Audio-Features "
             "allein erklaeren Popularitaet nur begrenzt."),
}
speichern("rf_metrics.json", metrics_export)


# ------------------------------------------------------------
# FEATURE IMPORTANCE (Standard + Permutation)
# ------------------------------------------------------------
print("\n[4] Standard Feature Importance ...")
std_imp = pd.DataFrame({
    "feature": FEATURES,
    "importance": model.feature_importances_,
}).sort_values("importance", ascending=False)
print(std_imp.to_string(index=False))

print("\n[5] Permutation Importance (auf Testdaten, robuster) ...")
# auf Stichprobe der Testdaten fuer Tempo (dein Ansatz)
X_s, y_s = resample(X_test, y_test, n_samples=min(2000, len(X_test)),
                    random_state=RANDOM_STATE)
perm = permutation_importance(
    model, X_s, y_s, n_repeats=5, random_state=RANDOM_STATE, n_jobs=-1
)
perm_df = pd.DataFrame({
    "feature": FEATURES,
    "importance": perm.importances_mean,
    "std": perm.importances_std,
}).sort_values("importance", ascending=False)
print(perm_df.to_string(index=False))

importance_export = {
    "standard": [
        {"feature": r["feature"], "importance": round(float(r["importance"]), 5)}
        for _, r in std_imp.iterrows()
    ],
    "permutation": [
        {"feature": r["feature"],
         "importance": round(float(r["importance"]), 5),
         "std": round(float(r["std"]), 5)}
        for _, r in perm_df.iterrows()
    ],
}
speichern("rf_importance.json", importance_export)

top3 = perm_df.head(3)["feature"].tolist()
print(f"\nHinweis: Laut Permutation Importance erklaeren v.a. {', '.join(top3)}")
print("die Popularitaet - aber das Modell insgesamt bleibt schwach (siehe R^2).")


# ------------------------------------------------------------
# OPTIONAL: Kontroll-Plots
# ------------------------------------------------------------
if MAKE_PNG:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        BG, AX_BG, TEXT, GREEN, RED = "#0d1117", "#161b22", "#e6edf3", "#1DB954", "#ff4d4d"

        # Plot 1: Permutation Importance
        pdf = perm_df.sort_values("importance", ascending=True)
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor(BG); ax.set_facecolor(AX_BG)
        colors = [GREEN if v > 0 else RED for v in pdf["importance"]]
        ax.barh(pdf["feature"], pdf["importance"], xerr=pdf["std"],
                color=colors, error_kw=dict(ecolor=TEXT, capsize=3, linewidth=1))
        ax.axvline(0, color=TEXT, linewidth=0.8, linestyle="--", alpha=0.5)
        ax.set_title("Permutation Importance (dedupliziert, robuster)",
                     fontsize=13, color=GREEN, pad=15)
        ax.set_xlabel("Fehleranstieg bei zufaelligem Mischen (groesser = wichtiger)",
                      color=TEXT, fontsize=9)
        ax.tick_params(colors=TEXT)
        plt.tight_layout()
        plt.savefig(os.path.join(EXPORT_DIR, "rf_importance.png"), dpi=130, facecolor=BG)
        plt.close()
        print("\n  -> gespeichert: rf_importance.png")

        # Plot 2: Cross-Validation Stabilitaet
        fig, ax = plt.subplots(figsize=(8, 4))
        fig.patch.set_facecolor(BG); ax.set_facecolor(AX_BG)
        bar_colors = [GREEN if s >= cv_mean else RED for s in cv_scores]
        ax.bar([f"Fold {i}" for i in range(1, 6)], cv_scores, color=bar_colors, alpha=0.85)
        ax.axhline(cv_mean, color=GREEN, linewidth=1.5, linestyle="--",
                   label=f"Mittel R^2 = {cv_mean:.3f}")
        ax.axhline(cv_mean + cv_std, color=TEXT, linewidth=0.8, linestyle=":", alpha=0.5)
        ax.axhline(cv_mean - cv_std, color=TEXT, linewidth=0.8, linestyle=":", alpha=0.5,
                   label=f"+/- Std = {cv_std:.3f}")
        ax.set_title("Sind die Ergebnisse stabil? - 5-Fold Cross-Validation",
                     fontsize=13, color=GREEN, pad=15)
        ax.set_ylabel("R^2 Score", color=TEXT)
        ax.tick_params(colors=TEXT)
        ax.legend(facecolor=AX_BG, edgecolor="#30363d", labelcolor=TEXT)
        ax.set_ylim(0, max(0.3, cv_scores.max() * 1.3))
        plt.tight_layout()
        plt.savefig(os.path.join(EXPORT_DIR, "rf_cv.png"), dpi=130, facecolor=BG)
        plt.close()
        print("  -> gespeichert: rf_cv.png")
    except ImportError:
        print("\n  matplotlib nicht installiert -> PNGs uebersprungen (JSONs sind fertig).")


print("\n=== DATEI 03 FERTIG ===")
print(f"Alle Ausgaben liegen in: {EXPORT_DIR}")
