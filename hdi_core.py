from flask import Flask, jsonify
import random

app = Flask(__name__)

# ---------------------------
# Base country scores & sectors
# ---------------------------
COUNTRY_OPPORTUNITIES = {
    "Tanzania": 7.4,
    "Kenya": 8.1,
    "Uganda": 7.8,
    "Nigeria": 8.5,
    "South Africa": 8.0,
    "Ghana": 7.9,
    "Rwanda": 8.2,
    "Ethiopia": 7.7,
    "Zambia": 7.6
}

COUNTRY_SECTORS = {
    "Tanzania": {"best_sector": "Agriculture", "profit_level": "Very High"},
    "Kenya": {"best_sector": "Technology", "profit_level": "High"},
    "Uganda": {"best_sector": "Agriculture", "profit_level": "High"},
    "Nigeria": {"best_sector": "Energy", "profit_level": "Very High"},
    "South Africa": {"best_sector": "Finance", "profit_level": "High"},
    "Ghana": {"best_sector": "Mining", "profit_level": "High"},
    "Rwanda": {"best_sector": "Tourism", "profit_level": "High"},
    "Ethiopia": {"best_sector": "Textiles", "profit_level": "Medium"},
    "Zambia": {"best_sector": "Agriculture", "profit_level": "Medium"}
}

# ---------------------------
# Home
# ---------------------------
@app.route("/")
def home():
    return "HDI Global API is live with AI prediction engine!"

# ---------------------------
# Dynamic scoring function
# ---------------------------
def dynamic_score(base_score):
    adjustment = random.uniform(-0.3, 0.3)
    return round(base_score + adjustment, 2)

# ---------------------------
# Country opportunity
# ---------------------------
@app.route("/hdi/country-opportunity/<country_name>")
def country_opportunity(country_name):
    base = COUNTRY_OPPORTUNITIES.get(country_name)
    if base is None:
        return jsonify({"error": "Country not found"}), 404
    score = dynamic_score(base)
    return jsonify({"country": country_name, "opportunity_score": score})

# ---------------------------
# Top 10 countries
# ---------------------------
@app.route("/hdi/top-opportunities")
def top_opportunities():
    dynamic_scores = {c: dynamic_score(s) for c, s in COUNTRY_OPPORTUNITIES.items()}
    sorted_countries = sorted(dynamic_scores.items(), key=lambda x: x[1], reverse=True)
    top_10 = [{"country": c, "score": s} for c, s in sorted_countries[:10]]
    return jsonify({"top_opportunities": top_10})

# ---------------------------
# Sector opportunity
# ---------------------------
@app.route("/hdi/sector-opportunity/<country_name>")
def sector_opportunity(country_name):
    sector_info = COUNTRY_SECTORS.get(country_name)
    if sector_info is None:
        return jsonify({"error": "Country not found"}), 404
    return jsonify({
        "country": country_name,
        "best_sector": sector_info["best_sector"],
        "profit_level": sector_info["profit_level"]
    })

# ---------------------------
# ---------------------------
# AI Prediction: “Next Millionaire Opportunity”
# ---------------------------
@app.route("/hdi/ai-prediction/<country_name>")
def ai_prediction(country_name):
    base_score = COUNTRY_OPPORTUNITIES.get(country_name)
    sector_info = COUNTRY_SECTORS.get(country_name)

    if not base_score or not sector_info:
        return jsonify({"error": "Country not found"}), 404

    # Simulate AI prediction: combine dynamic score + sector growth trend
    predicted_score = round(dynamic_score(base_score) + random.uniform(0.1, 0.5), 2)
    confidence = random.randint(85, 99)  # prediction confidence %

    return jsonify({
        "country": country_name,
        "best_sector": sector_info["best_sector"],
        "predicted_opportunity_score": predicted_score,
        "confidence_percent": confidence,
        "profit_level": sector_info["profit_level"]
    })

# ---------------------------
# Run Flask
# ---------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
