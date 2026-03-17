from flask import Flask, jsonify

app = Flask(__name__)

# HDI country opportunity scores
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

# Home route
@app.route("/")
def home():
    return "HDI Global API is live"

# Single country opportunity
@app.route("/hdi/country-opportunity/<country_name>")
def country_opportunity(country_name):
    score = COUNTRY_OPPORTUNITIES.get(country_name)
    if score is None:
        return jsonify({"error": "Country not found"}), 404
    return jsonify({"country": country_name, "opportunity_score": score})

# Top 10 countries by opportunity
@app.route("/hdi/top-opportunities")
def top_opportunities():
    sorted_countries = sorted(
        COUNTRY_OPPORTUNITIES.items(),
        key=lambda x: x[1],
        reverse=True
    )
    top_10 = [{"country": country, "score": score} for country, score in sorted_countries[:10]]
    return jsonify({"top_opportunities": top_10})

# Optional: dynamic scoring function for future AI integration
def calculate_score(base_score):
    # For now, just return base_score
    return round(base_score, 2)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
