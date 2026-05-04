from flask import Flask, jsonify, request
import uuid
import os
import requests
import psycopg2
from datetime import datetime, timedelta

app = Flask(__name__)

FLW_SECRET_KEY = os.environ.get("FLW_SECRET_KEY")
FLW_SECRET_HASH = os.environ.get("FLW_SECRET_HASH")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_KEY = os.environ.get("ADMIN_KEY")

BASE_URL = "https://hdi-global-api.onrender.com"
PAY_AMOUNT = 10
PAY_CURRENCY = "USD"

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name TEXT,
        email TEXT UNIQUE,
        api_key TEXT UNIQUE,
        plan TEXT DEFAULT 'free',
        premium_until TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        api_key TEXT,
        tx_ref TEXT UNIQUE,
        amount REAL,
        currency TEXT,
        status TEXT DEFAULT 'pending'
    )
    """)

    conn.commit()
    cur.close()
    conn.close()

init_db()

def premium_expiry():
    return (datetime.utcnow() + timedelta(days=30)).isoformat()

def is_premium(plan, premium_until):
    if plan != "premium" or not premium_until:
        return False
    try:
        return datetime.fromisoformat(premium_until) > datetime.utcnow()
    except:
        return False

def get_user_by_key(api_key):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, email, api_key, plan, premium_until FROM users WHERE api_key=%s",
        (api_key,)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

@app.route("/")
def home():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>HDI Intelligence</title>
    <style>
        body { font-family: Arial; background: #050816; color: white; text-align: center; padding: 60px; }
        .card { max-width: 700px; margin: auto; background: #111827; padding: 40px; border-radius: 18px; }
        input { padding: 12px; margin: 8px; width: 80%; border-radius: 8px; border: none; }
        button { padding: 12px 24px; background: #2563eb; color: white; border: none; border-radius: 10px; margin-top: 10px; cursor: pointer; }
        .pay { background: #16a34a; padding: 12px 20px; border-radius: 10px; text-decoration: none; color: white; display: inline-block; margin-top: 15px; }
        .result { margin-top: 20px; color: #38bdf8; }
    </style>
</head>
<body>
    <div class="card">
        <h1>HDI Intelligence</h1>
        <p>AI-powered opportunity signals for Africa</p>
        <input id="name" placeholder="Your Name"><br>
        <input id="email" placeholder="Your Email"><br>
        <button onclick="createUser()">Get Access</button>
        <div id="result" class="result"></div>
    </div>

    <script>
    async function createUser() {
        try {
            let name = document.getElementById("name").value;
            let email = document.getElementById("email").value;

            if (!name || !email) {
                alert("Please enter name and email");
                return;
            }

            let res = await fetch("/hdi/create-user", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({name: name, email: email})
            });

            let data = await res.json();

            if (data.api_key) {
                document.getElementById("result").innerHTML =
                    "<strong>Your Key:</strong> " + data.api_key +
                    "<br><br><a href='/hdi/premium-alerts?key=" + data.api_key + "'>View Signals</a>" +
                    "<br><br><a class='pay' href='/hdi/pay?key=" + data.api_key + "'>Upgrade Now 💰</a>";
            } else {
                document.getElementById("result").innerHTML =
                    "Error: " + JSON.stringify(data);
            }
        } catch (err) {
            document.getElementById("result").innerHTML =
                "Something went wrong. Try again.";
        }
    }
    </script>
</body>
</html>
"""

@app.route("/hdi/create-user", methods=["POST"])
def create_user():
    data = request.get_json() or {}
    name = data.get("name")
    email = data.get("email")

    if not name or not email:
        return jsonify({"error": "Missing fields"}), 400

    api_key = "HDI-" + uuid.uuid4().hex[:10].upper()

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (name, email, api_key) VALUES (%s, %s, %s)",
            (name, email, api_key)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"api_key": api_key})

@app.route("/hdi/premium-alerts")
def premium():
    key = request.args.get("key")
    user = get_user_by_key(key)

    if not user:
        return jsonify({"error": "Invalid key"}), 403

    if not is_premium(user[4], user[5]):
        return jsonify({
            "locked": True,
            "preview": "High-profit opportunity detected...",
            "payment": f"{BASE_URL}/hdi/pay?key={key}"
        }), 403

    return jsonify({
        "signal": "🔥 Premium opportunity",
        "margin": "20%",
        "urgency": "HIGH"
    })

@app.route("/hdi/pay")
def pay():
    key = request.args.get("key")
    user = get_user_by_key(key)

    if not user:
        return jsonify({"error": "Invalid key"}), 403

    tx_ref = "HDI-" + uuid.uuid4().hex[:12]

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO payments (api_key, tx_ref, amount, currency) VALUES (%s,%s,%s,%s)",
        (key, tx_ref, PAY_AMOUNT, PAY_CURRENCY)
    )
    conn.commit()
    cur.close()
    conn.close()

    headers = {
        "Authorization": f"Bearer {FLW_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "tx_ref": tx_ref,
        "amount": PAY_AMOUNT,
        "currency": PAY_CURRENCY,
        "redirect_url": f"{BASE_URL}/hdi/verify-payment",
        "customer": {"email": user[2], "name": user[1]}
    }

    res = requests.post(
        "https://api.flutterwave.com/v3/payments",
        json=payload,
        headers=headers
    )

    return jsonify(res.json())

@app.route("/hdi/webhook", methods=["POST"])
def webhook():
    if request.headers.get("verif-hash") != FLW_SECRET_HASH:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}

    if data.get("event") == "charge.completed":
        tx_ref = data["data"]["tx_ref"]

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT api_key FROM payments WHERE tx_ref=%s", (tx_ref,))
        row = cur.fetchone()

        if row:
            expiry = premium_expiry()
            cur.execute(
                "UPDATE users SET plan='premium', premium_until=%s WHERE api_key=%s",
                (expiry, row[0])
            )
            cur.execute(
                "UPDATE payments SET status='successful' WHERE tx_ref=%s",
                (tx_ref,)
            )

        conn.commit()
        cur.close()
        conn.close()

    return jsonify({"ok": True})

@app.route("/hdi/admin")
def admin():
    if request.args.get("key") != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE plan='premium'")
    premium = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(amount),0) FROM payments")
    revenue = cur.fetchone()[0]

    cur.close()
    conn.close()

    return jsonify({
        "users": users,
        "premium": premium,
        "revenue": revenue
    })

@app.route("/hdi/leads")
def leads():
    if request.args.get("key") != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT name, email, plan FROM users ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall()

    cur.close()
    conn.close()

    data = []
    for r in rows:
        data.append({
            "name": r[0],
            "email": r[1],
            "plan": r[2]
        })

    return jsonify(data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
