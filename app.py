from flask import Flask, jsonify, request
import sqlite3
import uuid
import os
import requests

app = Flask(__name__)
DB = "hdi.db"

FLW_SECRET_KEY = os.environ.get("FLW_SECRET_KEY")
BASE_URL = "https://hdi-global-api.onrender.com"
PAY_AMOUNT = 10
PAY_CURRENCY = "USD"

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
    conn.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT,
        tx_ref TEXT UNIQUE,
        amount REAL,
        currency TEXT,
        status TEXT DEFAULT 'pending'
    )
    """)
    conn.commit()
    conn.close()

init_db()

def get_conn():
    return sqlite3.connect(DB)

def get_user_by_key(api_key):
    conn = get_conn()
    user = conn.execute(
        "SELECT id, name, email, api_key, plan FROM users WHERE api_key=?",
        (api_key,)
    ).fetchone()
    conn.close()
    return user

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
        conn = get_conn()
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

    if not key:
        return jsonify({"error": "key is required"}), 400

    user = get_user_by_key(key)

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "name": user[1],
        "email": user[2],
        "plan": user[4],
        "api_key": user[3]
    })

@app.route("/hdi/premium-alerts")
def premium_alerts():
    key = request.args.get("key")

    user = get_user_by_key(key)

    if not user:
        return jsonify({
            "error": "Invalid API key",
            "upgrade": "Create an HDI account to access intelligence signals"
        }), 403

    name = user[1]
    plan = user[4]

    if plan == "free":
        return jsonify({
            "message": "🔒 Premium insight locked",
            "preview": "High-profit opportunity detected...",
            "upgrade": "Upgrade to PREMIUM to unlock full intelligence"
        }), 403

    return jsonify({
        "user": name,
        "plan": plan,
        "alert": "🔥 Full opportunity: Agriculture export opportunity in East Africa worth $500K+",
        "confidence": "91%",
        "urgency": "HIGH"
    })

@app.route("/hdi/pay")
def pay():
    api_key = request.args.get("key")

    if not api_key:
        return jsonify({"error": "Missing API key"}), 400

    user = get_user_by_key(api_key)

    if not user:
        return jsonify({"error": "Invalid API key"}), 404

    if not FLW_SECRET_KEY:
        return jsonify({"error": "Flutterwave secret key not configured"}), 500

    tx_ref = "HDI-TX-" + uuid.uuid4().hex[:12].upper()

    conn = get_conn()
    conn.execute(
        "INSERT INTO payments (api_key, tx_ref, amount, currency, status) VALUES (?, ?, ?, ?, ?)",
        (api_key, tx_ref, PAY_AMOUNT, PAY_CURRENCY, "pending")
    )
    conn.commit()
    conn.close()

    payload = {
        "tx_ref": tx_ref,
        "amount": PAY_AMOUNT,
        "currency": PAY_CURRENCY,
        "redirect_url": f"{BASE_URL}/hdi/verify-payment",
        "customer": {
            "email": user[2],
            "name": user[1]
        },
        "customizations": {
            "title": "HDI Premium Access",
            "description": "Unlock premium HDI intelligence"
        }
    }

    headers = {
        "Authorization": f"Bearer {FLW_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    res = requests.post(
        "https://api.flutterwave.com/v3/payments",
        json=payload,
        headers=headers,
        timeout=30
    )

    data = res.json()

    if res.status_code != 200 or data.get("status") != "success":
        return jsonify({
            "error": "Failed to create payment link",
            "details": data
        }), 400

    return jsonify({
        "message": "Payment link created",
        "payment_link": data["data"]["link"],
        "tx_ref": tx_ref
    })

@app.route("/hdi/verify-payment")
def verify_payment():
    transaction_id = request.args.get("transaction_id")
    tx_ref = request.args.get("tx_ref")
    status = request.args.get("status")

    if not transaction_id or not tx_ref:
        return jsonify({"error": "transaction_id and tx_ref are required"}), 400

    if not FLW_SECRET_KEY:
        return jsonify({"error": "Flutterwave secret key not configured"}), 500

    headers = {
        "Authorization": f"Bearer {FLW_SECRET_KEY}"
    }

    verify_res = requests.get(
        f"https://api.flutterwave.com/v3/transactions/{transaction_id}/verify",
        headers=headers,
        timeout=30
    )

    verify_data = verify_res.json()

    if verify_res.status_code != 200 or verify_data.get("status") != "success":
        return jsonify({
            "error": "Verification failed",
            "details": verify_data
        }), 400

    payment = verify_data.get("data", {})

    paid_status = payment.get("status")
    paid_tx_ref = payment.get("tx_ref")
    paid_amount = payment.get("amount")
    paid_currency = payment.get("currency")

    if (
        status != "successful"
        or paid_status != "successful"
        or paid_tx_ref != tx_ref
        or float(paid_amount) < float(PAY_AMOUNT)
        or paid_currency != PAY_CURRENCY
    ):
        return jsonify({
            "error": "Payment not valid",
            "payment_status": paid_status,
            "tx_ref": paid_tx_ref,
            "amount": paid_amount,
            "currency": paid_currency
        }), 400

    conn = get_conn()

    payment_row = conn.execute(
        "SELECT api_key FROM payments WHERE tx_ref=?",
        (tx_ref,)
    ).fetchone()

    if not payment_row:
        conn.close()
        return jsonify({"error": "Payment record not found"}), 404

    api_key = payment_row[0]

    conn.execute(
        "UPDATE payments SET status='successful' WHERE tx_ref=?",
        (tx_ref,)
    )

    conn.execute(
        "UPDATE users SET plan='premium' WHERE api_key=?",
        (api_key,)
    )

    conn.commit()
    conn.close()

    user = get_user_by_key(api_key)

    return jsonify({
        "message": "Payment verified and user upgraded",
        "user": user[1],
        "email": user[2],
        "api_key": api_key,
        "plan": "premium"
    })

if __name__ == "__main__":
    app.run()
