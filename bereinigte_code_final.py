# -*- coding: utf-8 -*-
"""
Created on Thu May 21 11:07:26 2026

@author: Daria Iwanow, Anna Lysa
"""

import pandas as pd
import numpy as np

df = pd.read_csv("C:/Users/daria/DAV Projekt Spotyfly/dataset.csv.zip")

print(f"Originalgroesse: {df.shape[0]:,} Zeilen x {df.shape[1]} Spalten")

df.head()
df.info()


# ── 1. UNNAMED SPALTE ENTFERNEN ───────────────────────────
# 'Unnamed: 0' ist nur eine Kopie des Pandas-Zeilenindex
# hat keinen inhaltlichen Informationswert
df.drop(columns=["Unnamed: 0"], inplace=True)


# ── 2. FEHLENDE WERTE (NaN) ───────────────────────────────
# Zeilen ohne Trackname oder Kuenstler sind nicht sinnvoll nutzbar
df[df.isnull().any(axis=1)]
df = df.dropna(subset=["track_name", "artists"])
print(f"Nach NaN-Entfernung: {len(df):,} Zeilen")


# ── 3. DUPLIKATE ENTFERNEN ────────────────────────────────
# manche Songs kommen in mehreren Genres vor
# wir behalten das erste Vorkommen, alle weiteren werden geloescht
print(f"Duplikate gefunden: {df.duplicated().sum()}")
df = df.drop_duplicates()
print(f"Nach Duplikat-Entfernung: {len(df):,} Zeilen")


# ── 4. LOUDNESS – CLIPPING auf gueltigen Bereich ─────────
# Loudness wird in dB gemessen, gueltige Werte sind <= 0
# Ausreisser (positiv) werden auf 0 gesetzt
df["loudness"] = df["loudness"].clip(upper=0)
print(f"Loudness > 0 nach Clipping: {(df['loudness'] > 0).sum()} Zeilen")


# ── 5. TEMPO BEREINIGEN ───────────────────────────────────
# tempo = 0 BPM ist physikalisch unmoeoglich
# Strategie: erst replace durch NaN, dann 3-stufige Imputation:
#   Stufe 1: Median von gleichem Genre + Kuenstler (am spezifischsten)
#   Stufe 2: Median des Genres
#   Stufe 3: Globaler Median (Fallback)

mask_tempo = df["tempo"] == 0
print(f"Betroffene Zeilen (tempo=0): {mask_tempo.sum()}")

df["imputed"] = False
df.loc[mask_tempo, "imputed"] = True
df["tempo"] = df["tempo"].replace(0, np.nan)

# Median-Werte berechnen
artist_median = (
    df[df["tempo"].notna()]
    .groupby(["track_genre", "artists"])["tempo"]
    .median()
)
genre_median  = df[df["tempo"].notna()].groupby("track_genre")["tempo"].median()
global_median = df["tempo"].median()

def fill_tempo(row):
    if not row["imputed"]:
        return row["tempo"]
    key = (row["track_genre"], row["artists"])
    return artist_median.get(key, genre_median.get(row["track_genre"], global_median))

df["tempo"] = df.apply(fill_tempo, axis=1)
print(f"Noch tempo=0 oder NaN: {(df['tempo'].isna() | (df['tempo'] == 0)).sum()}")


# ── 6. TIME_SIGNATURE BEREINIGEN ──────────────────────────
# Gueltige Werte laut Spotify: 3 bis 7 (fuer 3/4 bis 7/4 Takt)
# 0 ist ein Datenfehler -> als NaN markieren
# Wir ersetzen mit dem MODUS des Genres (haeufigster Wert)
# weil Taktarten diskrete Kategorien sind (nicht kontinuierlich)
# Modus ist hier besser als Median

print(f"time_signature Verteilung:\n{df['time_signature'].value_counts().sort_index()}")

mask_ts = df["time_signature"] == 0
print(f"Betroffene Zeilen (time_signature=0): {mask_ts.sum()}")

df.loc[mask_ts, "time_signature"] = np.nan

df["time_signature"] = (
    df.groupby("track_genre")["time_signature"]
    .transform(
        lambda x: x.fillna(x.mode().iloc[0]) if not x.mode().empty else x
    )
)

# Fallback + Integer-Typ sicherstellen
df["time_signature"] = df["time_signature"].fillna(4).astype(int)
print(f"Noch time_signature=0: {(df['time_signature'] == 0).sum()}")


# ── 7. LANGE TRACKS MARKIEREN ─────────────────────────────
# Tracks ueber 30 Minuten sind meistens DJ-Mixes oder Continuous Mixes
# wir loeschen sie nicht, aber markieren sie mit einer Flag-Spalte
# so koennen wir spaeter entscheiden ob wir sie einschliessen

thirty_min_ms = 30 * 60 * 1000
df["is_long_mix"] = df["duration_ms"] > thirty_min_ms
print(f"Tracks markiert als is_long_mix (> 30 Min): {df['is_long_mix'].sum()}")


# ── 8. SONDERFALL: VOGELGERAEUSCH-TRACK ───────────────────
# "Sonidos de Aves" ist eine Naturgeraeusch-Aufnahme, kein Musiktrack
# Genre wird manuell korrigiert damit er die Musik-Analyse nicht verfaelscht
df.loc[df["track_id"] == "0ikjzGMJbuO7Fv8uVQmSSh", "track_genre"] = "nature_sounds"


# ── 9. ABSCHLUSSKONTROLLE ─────────────────────────────────
print("\n=== Finaler Datensatz ===")
print(f"Zeilen:              {len(df):,}")
print(f"Spalten:             {len(df.columns)}")
print(f"NaN-Werte gesamt:    {df.isnull().sum().sum()}")
print(f"Duplikate:           {df.duplicated().sum()}")
print(f"tempo=0 oder NaN:    {(df['tempo'].isna() | (df['tempo'] == 0)).sum()}")
print(f"time_signature=0:    {(df['time_signature'] == 0).sum()}")
print(f"loudness > 0:        {(df['loudness'] > 0).sum()}")
print(f"is_long_mix Tracks:  {df['is_long_mix'].sum()}")
print(f"Imputed tempo:       {df['imputed'].sum()} Zeilen")

df.describe()

# bereinigten Datensatz speichern
df.to_csv("C:/Users/daria/DAV Projekt Spotyfly/spotify_clean.csv", index=False)
print("\nGespeichert als: spotify_clean.csv")
