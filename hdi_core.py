from flask import Flask, jsonify

app = Flask(__name__)

# ---------------------------
# Country Opportunity Scores
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

# ---------------------------
# Country Sector Data
# ---------------------------
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
# Home route
# ---------------------------
@app.route("/")
def home():
    return "HDI Global API is live"

# ---------------------------
# Single country opportunity
# ---------------------------
@app.route("/hdi/country-opportunity/<country_name>")
def country_opportunity(country_name):
    score = COUNTRY_OPPORTUNITIES.get(country_name)
    if score is None:
        return jsonify({"error": "Country not found"}), 404
    return jsonify({"country": country_name, "opportunity_score": score})

# ---------------------------
# Top 10 countries by opportunity
# ---------------------------
@app.route("/hdi/top-opportunities")
def top_opportunities():
    sorted_countries = sorted(
        COUNTRY_OPPORTUNITIES.items(),
        key=lambda x: x[1],
        reverse=True
    )
    top_10 = [{"country": country, "score": score} for country, score in sorted_countries[:10]]
    return jsonify({"top_opportunities": top_10})

# ---------------------------
# Sector opportunity per country
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
# Optional dynamic scoring function (future AI upgrade)
# ---------------------------
def calculate_score(base_score):
    # Placeholder: can add AI-based adjustments here later
    return round(base_score, 2)

# ---------------------------
# Run Flask
# ---------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
