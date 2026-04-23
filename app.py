from flask import Flask, jsonify, request
import sqlite3
import uuid

app = Flask(__name__)
DB = "hdi.db"

# ---------------------------
# Init DB
# ---------------------------
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

# ---------------------------
# Home
# ---------------------------
@app.route("/")
def home():
    return jsonify({"message": "HDI API LIVE 🚀"})

# ---------------------------
# Create User
# ---------------------------
@app.route("/hdi/create-user", methods=["POST"])
def create_user():
    data = request.get_json()

    name = data.get("name")
    email = data.get("email")

    api_key = "HDI-" + uuid.uuid4().hex[:10].upper()

    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT INTO users (name, email, api_key) VALUES (?, ?, ?)",
        (name, email, api_key)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "message": "User created",
        "api_key": api_key
    })

# ---------------------------
# Get User
# ---------------------------
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

# ---------------------------
# Run
# ---------------------------
if __name__ == "__main__":
    app.run()
