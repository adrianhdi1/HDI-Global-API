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

def now_utc():
    return datetime.utcnow()

def premium_expiry():
    return (now_utc() + timedelta(days=30)).isoformat()

def is_premium(plan, premium_until):
    if plan != "premium" or not premium_until:
        return False
    try:
        return datetime.fromisoformat(premium_until) > now_utc()
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

# 🔥 LANDING PAGE
@app.route("/")
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>HDI Global Intelligence</title>
        <style>
            body {
                font-family: Arial;
                background: #050816;
                color: white;
                text-align: center;
                padding: 60px;
            }
            .card {
                max-width: 700px;
                margin: auto;
                background: #111827;
                padding: 40px;
                border-radius: 18px;
            }
            h1 { font-size: 42px; }
            p { color: #cbd5e1; }
            .btn {
                margin-top: 20px;
                padding: 14px 24px;
                background: #2563eb;
                color: white;
                text-decoration: none;
                border-radius: 10px;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>HDI Intelligence</h1>
            <p>AI-powered opportunity signals for Africa</p>
            <p>Free preview. Premium unlocks full intelligence.</p>
            <a class="btn" href="/hdi/premium-alerts?key=DEMO_KEY">
                Try Preview
            </a>
        </div>
    </body>
    </html>
    """

@app.route("/hdi/create-user", methods=["POST"])
def create_user():
    data = request.get_json() or {}
    name = data.get("name")
    email = data.get("email")

    api_key = "HDI-" + uuid.uuid4().hex[:10].upper()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (name, email, api_key) VALUES (%s, %s, %s)",
        (name, email, api_key)
    )
    conn.commit()
    cur.close()
    conn.close()

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
            "preview": "Opportunity detected...",
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

    headers = {"Authorization": f"Bearer {FLW_SECRET_KEY}"}

    payload = {
        "tx_ref": tx_ref,
        "amount": PAY_AMOUNT,
        "currency": PAY_CURRENCY,
        "redirect_url": f"{BASE_URL}/hdi/verify-payment",
        "customer": {"email": user[2], "name": user[1]}
    }

    res = requests.post("https://api.flutterwave.com/v3/payments",
                        json=payload, headers=headers)

    return jsonify(res.json())

@app.route("/hdi/webhook", methods=["POST"])
def webhook():
    if request.headers.get("verif-hash") != FLW_SECRET_HASH:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
