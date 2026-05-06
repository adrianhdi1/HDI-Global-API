from flask import Flask, jsonify, request, redirect
import uuid, os, requests, psycopg2, random
from datetime import datetime

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY")

SYMBOLS = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "GOOGL", "META"]

SECTORS = {
    "Artificial Intelligence": ["NVDA", "MSFT", "GOOGL"],
    "Technology": ["AAPL", "MSFT", "META"],
    "Electric Vehicles": ["TSLA"],
    "E-Commerce": ["AMZN"],
    "Digital Advertising": ["GOOGL", "META"],
    "Cloud Infrastructure": ["MSFT", "AMZN", "GOOGL"]
}

ECONOMIES = {
    "USA Economy": {"focus":"Inflation, interest rates, technology markets","risk":"Policy sensitivity","opportunity":"AI, equities, institutional capital"},
    "China Economy": {"focus":"Manufacturing, exports, real estate pressure","risk":"Demand slowdown","opportunity":"Industrial recovery and trade flows"},
    "Africa Markets": {"focus":"Agriculture, infrastructure, mobile money, energy","risk":"Currency pressure and inflation","opportunity":"Emerging consumer growth"},
    "Emerging Markets": {"focus":"Currency movement, commodities, capital inflows","risk":"External debt and rate pressure","opportunity":"High-growth market expansion"},
    "Global Economy": {"focus":"Inflation, liquidity, global risk appetite","risk":"Macro uncertainty","opportunity":"Capital rotation across sectors"}
}

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name TEXT,
        email TEXT UNIQUE,
        api_key TEXT UNIQUE,
        plan TEXT DEFAULT 'free',
        premium_until TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS watchlist (
        id SERIAL PRIMARY KEY,
        api_key TEXT,
        symbol TEXT,
        created_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS access_requests (
        id SERIAL PRIMARY KEY,
        name TEXT,
        email TEXT,
        api_key TEXT,
        created_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS user_behavior (
        id SERIAL PRIMARY KEY,
        api_key TEXT,
        symbol TEXT,
        action TEXT,
        count INTEGER DEFAULT 1
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS signal_history (
        id SERIAL PRIMARY KEY,
        api_key TEXT,
        symbol TEXT,
        action TEXT,
        score INTEGER,
        entry_price REAL,
        current_price REAL,
        expected TEXT,
        result TEXT DEFAULT 'pending',
        created_at TEXT,
        checked_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS portfolio (
        id SERIAL PRIMARY KEY,
        api_key TEXT,
        symbol TEXT,
        amount REAL,
        created_at TEXT
    )""")

    conn.commit()
    cur.close()
    conn.close()

init_db()

def get_user_by_email(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

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
    if not ALPHA_VANTAGE_KEY:
        return None
    try:
        res = requests.get(
            "https://www.alphavantage.co/query",
            params={"function":"TIME_SERIES_DAILY","symbol":symbol,"apikey":ALPHA_VANTAGE_KEY},
            timeout=15
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
        latest_high = float(latest["2. high"])
        latest_low = float(latest["3. low"])

        change_pct = round(((latest_close - previous_close) / previous_close) * 100, 2)
        volatility_pct = round(((latest_high - latest_low) / latest_close) * 100, 2)

        return {
            "symbol": symbol,
            "date": dates[0],
            "latest_close": latest_close,
            "previous_close": previous_close,
            "change_pct": change_pct,
            "volatility_pct": volatility_pct
        }
    except:
        return None

def fetch_news_sentiment():
    if not ALPHA_VANTAGE_KEY:
        return []
    try:
        res = requests.get(
            "https://www.alphavantage.co/query",
            params={"function":"NEWS_SENTIMENT","tickers":"AAPL,TSLA,NVDA,MSFT","limit":6,"apikey":ALPHA_VANTAGE_KEY},
            timeout=15
        )
        data = res.json()
        return data.get("feed", [])[:5]
    except:
        return []

def track_behavior(api_key, symbol, action):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, count FROM user_behavior
            WHERE api_key=%s AND symbol=%s AND action=%s
        """, (api_key, symbol, action))
        existing = cur.fetchone()

        if existing:
            cur.execute("UPDATE user_behavior SET count=%s WHERE id=%s", (existing[1] + 1, existing[0]))
        else:
            cur.execute("INSERT INTO user_behavior(api_key,symbol,action,count) VALUES(%s,%s,%s,1)", (api_key, symbol, action))

        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def get_preferred_symbol(api_key):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT symbol, SUM(count) AS total
        FROM user_behavior
        WHERE api_key=%s
        GROUP BY symbol
        ORDER BY total DESC
        LIMIT 1
    """, (api_key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None

def get_behavior_summary(api_key):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT symbol, SUM(count) AS total
        FROM user_behavior
        WHERE api_key=%s
        GROUP BY symbol
        ORDER BY total DESC
        LIMIT 3
    """, (api_key,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return "HDI is still learning your market focus."

    return "Adaptive focus: " + ", ".join([f"{r[0]} ({r[1]})" for r in rows])

def calculate_multi_factor(symbol, change, volatility, is_preferred):
    momentum_score = min(100, max(40, int(60 + change * 8)))
    volatility_score = min(100, max(35, int(100 - volatility * 6)))
    trend_strength = min(100, max(40, int(65 + abs(change) * 7)))
    relevance_score = 95 if is_preferred else random.randint(55, 75)

    final_score = int(
        momentum_score * 0.35 +
        volatility_score * 0.20 +
        trend_strength * 0.25 +
        relevance_score * 0.20
    )

    if final_score >= 88:
        priority = "CRITICAL"
    elif final_score >= 76:
        priority = "HIGH"
    elif final_score >= 64:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    return {
        "momentum_score": momentum_score,
        "volatility_score": volatility_score,
        "trend_strength": trend_strength,
        "relevance_score": relevance_score,
        "final_score": final_score,
        "priority": priority
    }

def generate_decision_signal(symbol=None, api_key=None):
    preferred = get_preferred_symbol(api_key) if api_key else None
    symbol = symbol or preferred or random.choice(SYMBOLS)
    market = fetch_alpha_daily(symbol)

    if market:
        change = market["change_pct"]
        volatility = market["volatility_pct"]
        source = "Alpha Vantage Market Data"
        date = market["date"]
    else:
        change = round(random.uniform(-2.5, 3.5), 2)
        volatility = round(random.uniform(1.2, 4.8), 2)
        source = "HDI Adaptive Fallback Model"
        date = "Recent"

    factors = calculate_multi_factor(symbol, change, volatility, symbol == preferred)
    score = factors["final_score"]
    priority = factors["priority"]

    if score >= 88 and change > 0:
        action = "ENTER POSITION WITH CONTROLLED EXPOSURE"
        exposure = "20% – 30%"
        risk = "MODERATE"
        pattern = "Multi-Factor Momentum Breakout"
        brief = "HDI detects strong alignment between momentum, trend strength, and market relevance."
        recommendation = "HDI Recommendation: Consider entry within the next 2–4 hours while momentum remains active."
    elif score >= 76:
        action = "MONITOR CLOSELY"
        exposure = "10% – 20%"
        risk = "CONTROLLED"
        pattern = "Adaptive Growth Pattern"
        brief = "HDI detects improving conditions, but confirmation is still developing."
        recommendation = "HDI Recommendation: Monitor closely and wait for confirmation before increasing exposure."
    elif score >= 64:
        action = "WAIT FOR CONFIRMATION"
        exposure = "0% – 10%"
        risk = "MODERATE"
        pattern = "Confirmation Pending Pattern"
        brief = "HDI detects partial alignment, but not enough strength for a decisive move."
        recommendation = "HDI Recommendation: Wait for stronger confirmation before taking action."
    else:
        action = "AVOID / STAND BY"
        exposure = "0%"
        risk = "ELEVATED"
        pattern = "Weak Signal Pattern"
        brief = "HDI detects weak market alignment."
        recommendation = "HDI Recommendation: Avoid action until stronger signals appear."

    expected_low = round(abs(change) * 0.7 + 0.8, 1)
    expected_high = round(abs(change) * 1.9 + 1.5, 1)

    adaptive_note = f"Personalized signal based on your activity around {preferred}." if preferred else "General signal while HDI learns your behavior."

    return {
        "symbol": symbol,
        "source": source,
        "date": date,
        "change": change,
        "volatility": volatility,
        "pattern": pattern,
        "market_score": score,
        "priority": priority,
        "strategic_action": action,
        "recommendation": recommendation,
        "exposure": exposure,
        "entry_window": f"Next {random.randint(2,4)} hours",
        "expiry": f"{random.randint(4,8)} hours",
        "expected": f"+{expected_low}% to +{expected_high}%",
        "risk": risk,
        "confidence": f"{score}%",
        "intelligence_brief": brief,
        "adaptive_note": adaptive_note,
        "micro_result": f"{symbol} moved {change}% with {volatility}% intraday volatility",
        "factors": factors,
        "confidence_breakdown": {
            "momentum": factors["momentum_score"],
            "volatility": factors["volatility_score"],
            "trend_strength": factors["trend_strength"],
            "user_relevance": factors["relevance_score"]
        }
    }

def generate_sector_intelligence():
    sector_rows = []
    for sector, symbols in SECTORS.items():
        changes = []
        volatilities = []

        for symbol in symbols:
            market = fetch_alpha_daily(symbol)
            if market:
                changes.append(market["change_pct"])
                volatilities.append(market["volatility_pct"])
            else:
                changes.append(round(random.uniform(-2, 3), 2))
                volatilities.append(round(random.uniform(1, 5), 2))

        avg_change = round(sum(changes) / len(changes), 2)
        avg_vol = round(sum(volatilities) / len(volatilities), 2)

        momentum = min(100, max(40, int(60 + avg_change * 8)))
        stability = min(100, max(35, int(100 - avg_vol * 6)))
        sector_score = int(momentum * 0.6 + stability * 0.4)

        if sector_score >= 85:
            opportunity = "Strong opportunity pressure detected"
            risk = "MODERATE"
            priority = "HIGH"
        elif sector_score >= 70:
            opportunity = "Developing opportunity pattern"
            risk = "CONTROLLED"
            priority = "MEDIUM"
        else:
            opportunity = "Weak or uncertain sector conditions"
            risk = "ELEVATED"
            priority = "LOW"

        sector_rows.append({
            "sector": sector,
            "symbols": ", ".join(symbols),
            "avg_change": avg_change,
            "avg_volatility": avg_vol,
            "sector_score": sector_score,
            "opportunity": opportunity,
            "risk": risk,
            "priority": priority
        })

    return sorted(sector_rows, key=lambda x: x["sector_score"], reverse=True)

def sector_intelligence_html():
    html = ""
    for s in generate_sector_intelligence():
        html += f"""
        <div class="box">
            <b>{s["sector"]}</b><br>
            Symbols: <span class="muted">{s["symbols"]}</span><br>
            Sector Score: <span class="metric">{s["sector_score"]}/100</span><br>
            Avg Change: {s["avg_change"]}%<br>
            Volatility: {s["avg_volatility"]}%<br>
            Opportunity: <span class="gold">{s["opportunity"]}</span><br>
            Risk: {s["risk"]}<br>
            Priority: {s["priority"]}
        </div>
        """
    return html
@app.route("/hdi/request-access")
def request_access():
    key = request.args.get("key")
    user = get_user_by_key(key)

    if not user:
        return "Invalid key"

    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO access_requests(name,email,api_key,created_at)
            VALUES(%s,%s,%s,%s)
        """, (
            user[1],
            user[2],
            key,
            datetime.utcnow().isoformat()
        ))

        conn.commit()
        cur.close()
        conn.close()

    except:
        pass

    return f"""
<html>
<head>
<title>Request Access</title>
{base_style()}
</head>

<body>
<div class="container">

<div class="card">
<div class="institution">Private Beta Request</div>

<h1>Institutional Access Request Recorded</h1>

<p class="blue">
Thank you, {user[1]}.
</p>

<p>
Your access request is now in the private beta queue.
</p>

<a class="btn" href="/hdi/dashboard?key={key}">
Return to Dashboard
</a>

</div>
</div>
</body>
</html>
"""

@app.route("/hdi/real-signal")
def real_signal_api():
    key = request.args.get("key")
    return jsonify(generate_decision_signal(api_key=key))

@app.route("/hdi/ranked-signals")
def ranked_signals_api():
    key = request.args.get("user_key")
    return jsonify(generate_ranked_signals(key))

@app.route("/hdi/pay")
def pay():
    key = request.args.get("key")
    return redirect(f"/hdi/request-access?key={key}")

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)))
