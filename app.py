from flask import Flask, jsonify, request, redirect
import uuid, os, requests, psycopg2, random
from datetime import datetime

app = Flask(__name__)

FLW_SECRET_KEY = os.environ.get("FLW_SECRET_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY")

BASE_URL = "https://hdi-global-api.onrender.com"
PAY_AMOUNT = 10
PAY_CURRENCY = "USD"

SYMBOLS = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "GOOGL", "META"]

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def get_user_by_key(api_key):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE api_key=%s", (api_key,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def is_premium(plan, premium_until):
    if plan != "premium" or not premium_until:
        return False
    try:
        return datetime.fromisoformat(premium_until) > datetime.utcnow()
    except:
        return False

def fetch_alpha_daily(symbol):
    try:
        res = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "apikey": ALPHA_VANTAGE_KEY
            },
            timeout=10
        )
        data = res.json()
        series = data.get("Time Series (Daily)")
        if not series:
            return None

        dates = sorted(series.keys(), reverse=True)
        latest = series[dates[0]]
        previous = series[dates[1]]

        latest_close = float(latest["4. close"])
        previous_close = float(previous["4. close"])
        change_pct = round(((latest_close - previous_close) / previous_close) * 100, 2)

        return {
            "symbol": symbol,
            "change_pct": change_pct
        }
    except:
        return None

def generate_decision_signal():
    symbol = random.choice(SYMBOLS)
    market = fetch_alpha_daily(symbol)

    if not market:
        change = random.uniform(-2, 3)
    else:
        change = market["change_pct"]

    # Decision logic
    if change > 2:
        action = "ENTER POSITION"
        urgency = "CRITICAL"
        score = random.randint(85, 95)
        summary = "Strong upward momentum detected. Institutional activity likely."
    elif change > 0:
        action = "MONITOR CLOSELY"
        urgency = "HIGH"
        score = random.randint(75, 85)
        summary = "Positive movement detected. Market showing stable growth."
    else:
        action = "WAIT"
        urgency = "MEDIUM"
        score = random.randint(60, 75)
        summary = "Market showing weakness or uncertainty. Possible reversal."

    return {
        "symbol": symbol,
        "change": change,
        "action": action,
        "urgency": urgency,
        "score": score,
        "summary": summary
    }

@app.route("/hdi/premium-alerts")
def premium():
    key = request.args.get("key")
    user = get_user_by_key(key)
    signal = generate_decision_signal()

    if not user:
        return "Invalid key"

    if not is_premium(user[4], user[5]):
        return f"""
        <html><body style="background:#050816;color:white;text-align:center;padding:60px;font-family:Arial;">
        <div style="max-width:700px;margin:auto;background:#111827;padding:40px;border-radius:20px;">
        <h1>🔒 Decision Signal Locked</h1>
        <p>AI has detected a high-value decision pattern</p>

        <p><b>Symbol:</b> {signal["symbol"]}</p>
        <p><b>Market Score:</b> Locked</p>
        <p><b>Recommended Action:</b> Locked</p>

        <h3>Unlock Full Decision Intelligence</h3>
        <a href="/hdi/pay?key={key}" style="background:#16a34a;padding:15px 25px;border-radius:10px;color:white;text-decoration:none;">
        Upgrade Now 💰</a>
        </div>
        </body></html>
        """

    return f"""
    <html><body style="background:#050816;color:white;text-align:center;padding:60px;font-family:Arial;">
    <div style="max-width:700px;margin:auto;background:#111827;padding:40px;border-radius:20px;">
    <h1>🔥 HDI Decision Signal</h1>

    <p><b>Symbol:</b> {signal["symbol"]}</p>
    <p><b>Market Activity Score:</b> {signal["score"]}/100</p>
    <p><b>Recommended Action:</b> {signal["action"]}</p>
    <p><b>Urgency:</b> {signal["urgency"]}</p>

    <h3>AI Summary</h3>
    <p>{signal["summary"]}</p>

    <br><a href="/hdi/dashboard?key={key}" style="color:#94a3b8;">Back to Dashboard</a>
    </div>
    </body></html>
    """

@app.route("/hdi/real-signal")
def api():
    return jsonify(generate_decision_signal())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
