"""
============================================================
 SPOTIFY DASHBOARD - Flask Server  (Weg A1)
============================================================
Startet einen lokalen Server, der das Dashboard ausliefert
und die Analyse-JSONs als API bereitstellt.

START:
    py app.py
Dann im Browser oeffnen:  http://localhost:5000

Die JSONs liegen im Ordner ./data/ (von den Skripten 01-04 erzeugt).
============================================================
"""

from flask import Flask, render_template, jsonify, abort
import os
import json

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "export")

# erlaubte JSON-Dateien (Sicherheit: keine beliebigen Dateien ausliefern)
ERLAUBT = {
    "overview", "top10", "popular_vs_rest", "genre_stats", "genres",
    "correlation_matrix", "correlation_popularity",
    "rf_metrics", "rf_importance",
    "genre_similarity", "genre_energy_rank", "genre_map",
    "tracks_explorer", "feature_glossary",
}


@app.route("/")
def index():
    """Liefert die Haupt-HTML-Seite."""
    return render_template("index.html")


@app.route("/api/data/<name>")
def api_data(name):
    """Liefert eine Analyse-JSON aus dem data-Ordner."""
    if name not in ERLAUBT:
        abort(404, description="Unbekannte Datenquelle.")
    pfad = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(pfad):
        abort(404, description=f"Datei {name}.json fehlt - Skript 01-04 laufen lassen.")
    with open(pfad, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))

@app.route("/api/genremap")
def api_genremap():
    """Liefert die fertige Genre-Map als HTML-Fragment."""
    pfad = os.path.join(DATA_DIR, "genre_map.html")
    if not os.path.exists(pfad):
        return "<p style='color:#888'>genre_map.html fehlt – Datei 04 neu laufen lassen.</p>"
    with open(pfad, "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    print("=" * 50)
    print("  SPOTIFY DASHBOARD")
    print("  Oeffne im Browser:  http://localhost:5000")
    print("  Beenden mit:        STRG + C")
    print("=" * 50)
    app.run(debug=True, port=5000)
