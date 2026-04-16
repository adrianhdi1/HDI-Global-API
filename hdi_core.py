from flask import Flask, jsonify
import random

app = Flask(__name__)

# ---------------------------
# Base Data
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
# Dynamic scoring
# ---------------------------
def dynamic_score(base_score):
    return round(base_score + random.uniform(-0.3, 0.3), 2)

# ---------------------------
# Home
# ---------------------------
@app.route("/")
def home():
    return "HDI Global API with AI + Alerts is LIVE 🚀"

# ---------------------------
# Country Opportunity
# ---------------------------
@app.route("/hdi/country-opportunity/<country_name>")
def country_opportunity(country_name):
    base = COUNTRY_OPPORTUNITIES.get(country_name)
    if base is None:
        return jsonify({"error": "Country not found"}), 404

    return jsonify({
        "country": country_name,
        "opportunity_score": dynamic_score(base)
    })

# ---------------------------
# Sector Opportunity
# ---------------------------
@app.route("/hdi/sector-opportunity/<country_name>")
def sector_opportunity(country_name):
    sector = COUNTRY_SECTORS.get(country_name)
    if sector is None:
        return jsonify({"error": "Country not found"}), 404

    return jsonify({
        "country": country_name,
        "best_sector": sector["best_sector"],
        "profit_level": sector["profit_level"]
    })

# ---------------------------
# AI Prediction
# ---------------------------
@app.route("/hdi/ai-prediction/<country_name>")
def ai_prediction(country_name):
    base = COUNTRY_OPPORTUNITIES.get(country_name)
    sector = COUNTRY_SECTORS.get(country_name)

    if base is None or sector is None:
        return jsonify({"error": "Country not found"}), 404

    predicted_score = round(dynamic_score(base) + random.uniform(0.2, 0.6), 2)
    confidence = random.randint(85, 99)

    return jsonify({
        "country": country_name,
        "best_sector": sector["best_sector"],
        "predicted_opportunity_score": predicted_score,
        "confidence_percent": confidence,
        "profit_level": sector["profit_level"]
    })

# ---------------------------
# Alerts System 🚨
# ---------------------------
@app.route("/hdi/alerts")
def alerts():
    country = random.choice(list(COUNTRY_OPPORTUNITIES.keys()))
    sector = COUNTRY_SECTORS[country]["best_sector"]
    urgency = random.choice(["HIGH", "MEDIUM", "CRITICAL"])

    return jsonify({
        "alert": f"🚨 High opportunity detected in {country} - {sector} sector",
        "urgency": urgency
    })

# ---------------------------
# Run
# ---------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
