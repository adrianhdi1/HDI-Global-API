from flask import Flask, jsonify, request
import random
import json
import os

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
# Storage (API Keys)
# ---------------------------
KEYS_FILE = "keys.json"

def load_keys():
    if not os.path.exists(KEYS_FILE):
        return []
    with open(KEYS_FILE, "r") as f:
        return json.load(f)

def save_keys(keys):
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f)

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
    return "HDI Global API FULL SYSTEM LIVE 🚀"

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
# Alerts (Free)
# ---------------------------
@app.route("/hdi/alerts")
def alerts():
    country = random.choice(list(COUNTRY_OPPORTUNITIES.keys()))
    sector = COUNTRY_SECTORS[country]["best_sector"]

    return jsonify({
        "alert": f"🚨 Opportunity detected in {country} - {sector} sector"
    })

# ---------------------------
# Generate API Key
# ---------------------------
@app.route("/hdi/generate-key")
def generate_key():
    keys = load_keys()

    new_key = f"HDI-{random.randint(1000,9999)}-{random.randint(1000,9999)}"
    keys.append(new_key)

    save_keys(keys)

    return jsonify({
        "message": "API key generated",
        "api_key": new_key
    })

# ---------------------------
# Premium Alerts
# ---------------------------
@app.route("/hdi/premium-alerts")
def premium_alerts():
    api_key = request.args.get("key")
    keys = load_keys()

    if api_key not in keys:
        return jsonify({
            "error": "Invalid or missing API key"
        }), 403

    country = random.choice(list(COUNTRY_OPPORTUNITIES.keys()))
    sector = COUNTRY_SECTORS[country]["best_sector"]

    return jsonify({
        "premium_alert": f"🚨 CRITICAL opportunity in {country} - {sector} sector",
        "access": "GRANTED"
    })

# ---------------------------
# Run
# ---------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
