from flask import Flask, jsonify, request
import sqlite3
import uuid

app = Flask(__name__)
DB = "hdi.db"

def init_db():
    conn = sqlite3.connect(DB)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        api_key TEXT UNIQUE,
        plan TEXT DEFAULT 'free'
    )
    """)
    conn.close()

init_db()

@app.route("/")
def home():
    return jsonify({"message": "HDI API LIVE 🚀"})

@app.route("/hdi/create-user", methods=["POST"])
def create_user():
    data = request.get_json() or {}

    name = data.get("name")
    email = data.get("email")

    if not name or not email:
        return jsonify({"error": "name and email are required"}), 400

    api_key = "HDI-" + uuid.uuid4().hex[:10].upper()

    try:
        conn = sqlite3.connect(DB)
        conn.execute(
            "INSERT INTO users (name, email, api_key) VALUES (?, ?, ?)",
            (name, email, api_key)
        )
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already exists"}), 409

    return jsonify({
        "message": "User created",
        "api_key": api_key,
        "plan": "free"
    })

@app.route("/hdi/user")
def get_user():
    key = request.args.get("key")

    conn = sqlite3.connect(DB)
    user = conn.execute(
        "SELECT name, email, plan FROM users WHERE api_key=?",
        (key,)
    ).fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "name": user[0],
        "email": user[1],
        "plan": user[2]
    })

@app.route("/hdi/upgrade", methods=["POST"])
def upgrade():
    data = request.get_json() or {}

    key = data.get("api_key")
    plan = data.get("plan", "premium")

    if not key:
        return jsonify({"error": "api_key is required"}), 400

    conn = sqlite3.connect(DB)
    cur = conn.execute(
        "UPDATE users SET plan=? WHERE api_key=?",
        (plan, key)
    )
    conn.commit()
    updated = cur.rowcount
    conn.close()

    if updated == 0:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "message": "User upgraded successfully",
        "plan": plan
    })

@app.route("/hdi/premium-alerts")
def premium_alerts():
    key = request.args.get("key")

    conn = sqlite3.connect(DB)
    user = conn.execute(
        "SELECT name, plan FROM users WHERE api_key=?",
        (key,)
    ).fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "Invalid API key"}), 403

    if user[1] != "premium":
        return jsonify({"error": "Upgrade to premium"}), 403

    return jsonify({
        "user": user[0],
        "plan": user[1],
        "alert": "🔥 Premium opportunity unlocked"
    })

if __name__ == "__main__":
    app.run()
