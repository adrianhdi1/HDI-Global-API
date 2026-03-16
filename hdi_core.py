from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/hdi/country-opportunity/<country>")
def country_opportunity(country):
    scores = {
        "Tanzania": 7.4,
        "Kenya": 7.6,
        "India": 8.5
    }

    score = scores.get(country)

    if score is None:
        return jsonify({"error": "Country not found"}), 404

    return jsonify({
        "country": country,
        "opportunity_score": score
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
