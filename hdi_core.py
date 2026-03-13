from flask import Flask, jsonify
import numpy as np

app = Flask(__name__)

# Mock data
country_scores = {
    "Kenya": 7.6,
    "Tanzania": 7.4,
    "India": 8.5
}

sector_scores = {
    "Finance": 8.0,
    "Logistics & Trade": 7.93,
    "Agriculture": 7.33,
    "Industrial": 6.67
}

countries = list(country_scores.keys())

sectors = {
    "Finance": [0.8, 0.75, 0.82],
    "Logistics & Trade": [0.7, 0.65, 0.68],
    "Agriculture": [0.6, 0.58, 0.62],
    "Industrial": [0.55, 0.5, 0.57]
}

@app.route("/hdi/country-opportunity/<country>")
def country_opportunity(country):
    score = country_scores.get(country)
    if score is None:
        return jsonify({"error": "Country not found"}), 404
    return jsonify({"country": country, "opportunity_score": score})

@app.route("/hdi/sector-score/<sector>")
def sector_score(sector):
    score = sector_scores.get(sector)
    if score is None:
        return jsonify({"error": "Sector not found"}), 404
    return jsonify({"sector": sector, "opportunity_score": score})

@app.route("/hdi/automated-opportunities")
def automated_opportunities():
    results = []
    for country in countries:
        for sector, growth_factors in sectors.items():
            avg_growth = np.mean(growth_factors)
            opportunity_score = round(avg_growth * 10 + np.random.rand(), 2)
            recommendation = "Focus expansion in this sector" if opportunity_score > 7 else "Caution"
            results.append((country, sector, opportunity_score, recommendation))
    results.sort(key=lambda x: x[2], reverse=True)
    output = [
        {"country": r[0], "sector": r[1], "opportunity_score": r[2], "recommendation": r[3]}
        for r in results
    ]
    return jsonify(output)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
