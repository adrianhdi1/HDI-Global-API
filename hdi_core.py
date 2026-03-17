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

@app.route("/")
def home():
    return "HDI Global API is live"

@app.route("/hdi/country-opportunity/<country_name>")
def country_opportunity(country_name):
    score = COUNTRY_OPPORTUNITIES.get(country_name)

    if score is None:
        return jsonify({
            "error": "Country not found"
        }), 404

    return jsonify({
        "country": country_name,
        "opportunity_score": score
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
