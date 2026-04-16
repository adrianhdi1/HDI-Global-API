from flask import Flask, jsonify, request
import random
import sqlite3
import uuid

app = Flask(__name__)
DB_FILE = "hdi.db"

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
# Database
# ---------------------------
def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            api_key TEXT NOT NULL UNIQUE,
            plan TEXT NOT NULL DEFAULT 'free'
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------------------
# Helpers
# ---------------------------
def dynamic_score(base_score):
    return round(base_score + random.uniform(-0.3, 0.3), 2)

def generate_api_key():
    return f"HDI-{uuid.uuid4().hex[:12].upper()}"

def get_user_by_key(api_key):
    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE api_key = ?",
        (api_key,)
    ).fetchone()
    conn.close()
    return user

# ---------------------------
# Home
# ---------------------------
@app.route("/")
def home():
    return "HDI Global API + Database is LIVE 🚀"

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
# Free Alerts
# ---------------------------
@app.route("/hdi/alerts")
def alerts():
    country = random.choice(list(COUNTRY_OPPORTUNITIES.keys()))
    sector = COUNTRY_SECTORS[country]["best_sector"]

    return jsonify({
        "alert": f"🚨 Opportunity detected in {country} - {sector} sector"
    })

# ---------------------------
# Create User
# ---------------------------
@app.route("/hdi/create-user", methods=["POST"])
def create_user():
    data = request.get_json(silent=True) or {}

    name = data.get("name")
    email = data.get("email")
    plan = data.get("plan", "free")

    if not name or not email:
        return jsonify({"error": "name and email are required"}), 400

    api_key = generate_api_key()

    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO users (name, email, api_key, plan) VALUES (?, ?, ?, ?)",
            (name, email, api_key, plan)
        )
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already exists"}), 409

    return jsonify({
        "message": "User created successfully",
        "name": name,
        "email": email,
        "plan": plan,
        "api_key": api_key
    }), 201

# ---------------------------
# Get User By API Key
# ---------------------------
@app.route("/hdi/user")
def get_user():
    api_key = request.args.get("key")
    if not api_key:
        return jsonify({"error": "API key is required"}), 400

    user = get_user_by_key(api_key)
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "name": user["name"],
        "email": user["email"],
        "plan": user["plan"],
        "api_key": user["api_key"]
    })

# ---------------------------
# Premium Alerts (DB-based)
# ---------------------------
@app.route("/hdi/premium-alerts")
def premium_alerts():
    api_key = request.args.get("key")
    if not api_key:
        return jsonify({"error": "Missing API key"}), 403

    user = get_user_by_key(api_key)
    if not user:
        return jsonify({"error": "Invalid API key"}), 403

    if user["plan"] not in ["premium", "elite"]:
        return jsonify({"error": "Upgrade to premium"}), 403

    country = random.choice(list(COUNTRY_OPPORTUNITIES.keys()))
    sector = COUNTRY_SECTORS[country]["best_sector"]

    return jsonify({
        "user": user["name"],
        "plan": user["plan"],
        "premium_alert": f"🚨 CRITICAL opportunity in {country} - {sector} sector",
        "access": "GRANTED"
    })

# ---------------------------
# Upgrade User Plan
# ---------------------------
@app.route("/hdi/upgrade-plan", methods=["POST"])
def upgrade_plan():
    data = request.get_json(silent=True) or {}

    api_key = data.get("api_key")
    new_plan = data.get("plan")

    if not api_key or not new_plan:
        return jsonify({"error": "api_key and plan are required"}), 400

    if new_plan not in ["free", "premium", "elite"]:
        return jsonify({"error": "Invalid plan"}), 400

    conn = get_connection()
    cur = conn.execute(
        "UPDATE users SET plan = ? WHERE api_key = ?",
        (new_plan, api_key)
    )
    conn.commit()
    updated = cur.rowcount
    conn.close()

    if updated == 0:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "message": "Plan updated successfully",
        "new_plan": new_plan
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
