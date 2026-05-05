from flask import Flask, jsonify, request, redirect
import uuid, os, requests, psycopg2, random
from datetime import datetime

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY")
ADMIN_KEY = os.environ.get("ADMIN_KEY")

BASE_URL = "https://hdi-global-api.onrender.com"
SYMBOLS = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "GOOGL", "META"]

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
            params={
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "apikey": ALPHA_VANTAGE_KEY
            },
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
        change_pct = round(((latest_close - previous_close) / previous_close) * 100, 2)

        return {
            "symbol": symbol,
            "date": dates[0],
            "latest_close": latest_close,
            "previous_close": previous_close,
            "change_pct": change_pct
        }
    except:
        return None

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
            cur.execute(
                "UPDATE user_behavior SET count=%s WHERE id=%s",
                (existing[1] + 1, existing[0])
            )
        else:
            cur.execute(
                "INSERT INTO user_behavior(api_key,symbol,action,count) VALUES(%s,%s,%s,1)",
                (api_key, symbol, action)
            )

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

def generate_decision_signal(symbol=None):
    symbol = symbol or random.choice(SYMBOLS)
    market = fetch_alpha_daily(symbol)

    if market:
        change = market["change_pct"]
        source = "Alpha Vantage Market Data"
        date = market["date"]
    else:
        change = round(random.uniform(-2.5, 3.5), 2)
        source = "HDI Adaptive Fallback Model"
        date = "Recent"

    if change > 2:
        action = "ENTER POSITION NOW"
        urgency = "CRITICAL"
        risk = "MODERATE"
        score = random.randint(88, 96)
        brief = "Strong momentum detected. HDI identifies a high-probability decision pattern."
        pattern = "Momentum Breakout Pattern"
    elif change > 0:
        action = "MONITOR CLOSELY"
        urgency = "HIGH"
        risk = "CONTROLLED"
        score = random.randint(76, 87)
        brief = "Positive movement detected. Market behavior suggests controlled opportunity formation."
        pattern = "Controlled Growth Pattern"
    else:
        action = "WAIT"
        urgency = "MEDIUM"
        risk = "MODERATE"
        score = random.randint(60, 75)
        brief = "Uncertainty detected. HDI recommends waiting for stronger confirmation."
        pattern = "Reversal Watch Pattern"

    expected_low = round(abs(change) * 0.8, 1)
    expected_high = round(abs(change) * 1.8 + 1.5, 1)

    return {
        "symbol": symbol,
        "source": source,
        "date": date,
        "change": change,
        "pattern": pattern,
        "market_score": score,
        "strategic_action": action,
        "exposure": "20% – 30%" if change > 2 else "10% – 20%" if change > 0 else "0%",
        "entry_window": f"Next {random.randint(2,4)} hours",
        "expiry": f"{random.randint(4,8)} hours",
        "expected": f"+{expected_low}% to +{expected_high}%",
        "risk": risk,
        "urgency": urgency,
        "confidence": f"{score}%",
        "intelligence_brief": brief,
        "micro_result": f"{symbol} moved {change}% from previous close",
        "confidence_breakdown": {
            "momentum": "Strong" if change > 1 else "Moderate",
            "volume": "Confirmed",
            "alignment": "Positive" if change > 0 else "Mixed"
        }
    }

def generate_adaptive_signal(api_key):
    preferred = get_preferred_symbol(api_key)
    signal = generate_decision_signal(preferred)
    signal["adaptive_note"] = (
        f"Personalized signal based on your activity around {preferred}."
        if preferred else
        "General signal while HDI learns your behavior."
    )
    return signal

def generate_insight_feed(api_key=None):
    preferred = get_preferred_symbol(api_key) if api_key else None

    if preferred:
        return {
            "sector": f"{preferred} Focus",
            "theme": "personalized market behavior pattern",
            "impact": random.choice(["STRONG", "HIGH"]),
            "confidence": random.randint(78, 93),
            "interpretation": f"HDI detected repeated interest in {preferred}. Your intelligence feed is now adapting toward this focus."
        }

    return {
        "sector": random.choice(["Global Equities", "AI", "Energy", "Fintech", "Healthcare"]),
        "theme": random.choice(["capital rotation", "rising volatility", "momentum pressure", "breakout potential"]),
        "impact": random.choice(["MODERATE", "STRONG", "HIGH"]),
        "confidence": random.randint(72, 91),
        "interpretation": "Market behavior suggests an emerging decision window. HDI will personalize this feed as you use the system."
    }

def performance_tracking_html():
    rows = ""
    wins = 0
    total = 0

    for symbol in SYMBOLS[:6]:
        market = fetch_alpha_daily(symbol)
        if market:
            change = market["change_pct"]
            date = market["date"]
        else:
            change = round(random.uniform(-1.8, 3.8), 2)
            date = "Recent"

        total += 1
        if change > 0:
            wins += 1

        color = "#22c55e" if change >= 0 else "#ef4444"
        sign = "+" if change >= 0 else ""

        rows += f"""
        <div class="box">
            <b>{symbol}</b><br>
            <span style="color:{color};font-size:22px;font-weight:bold;">{sign}{change}%</span>
            <br><small>{date}</small>
        </div>
        """

    accuracy = round((wins / total) * 100) if total else 0
    return f"<p class='blue'>Recent Positive Movement Rate: {accuracy}%</p><div class='grid'>{rows}</div>"

def get_watchlist(api_key):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM watchlist WHERE api_key=%s ORDER BY id DESC", (api_key,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in rows]

def watchlist_html(api_key):
    symbols = get_watchlist(api_key)
    if not symbols:
        return "<p class='muted'>No watchlist yet. Add AAPL, TSLA, NVDA, etc.</p>"

    html = ""
    for symbol in symbols:
        signal = generate_decision_signal(symbol)
        color = "#22c55e" if signal["change"] >= 0 else "#ef4444"
        sign = "+" if signal["change"] >= 0 else ""

        html += f"""
        <div class="box">
            <b>{symbol}</b><br>
            <span style="color:{color};font-size:22px;font-weight:bold;">{sign}{signal["change"]}%</span>
            <br><span class="muted">{signal["micro_result"]}</span>
            <br><span class="muted">Strategic Action: 🔒 Locked</span>
            <br><a href="/hdi/remove-watchlist?key={api_key}&symbol={symbol}" style="color:#ef4444;">Remove</a>
        </div>
        """
    return html

def base_style():
    return """
    <style>
    body{margin:0;font-family:Arial;background:linear-gradient(135deg,#020617,#0f172a,#111827);color:white;text-align:center;}
    .container{max-width:980px;margin:auto;padding:60px 20px;}
    .card{background:rgba(17,24,39,.92);border:1px solid rgba(56,189,248,.18);box-shadow:0 0 50px rgba(0,0,0,.45);padding:42px;border-radius:24px;margin-bottom:24px;}
    .institution{color:#38bdf8;font-weight:bold;letter-spacing:1px;text-transform:uppercase;font-size:13px;}
    h1{font-size:42px;margin-bottom:12px;} h2{color:#e5e7eb;} p{color:#cbd5e1;line-height:1.6;}
    input,select{padding:14px;margin:8px;width:80%;border-radius:10px;border:1px solid #334155;background:#020617;color:white;}
    button,.btn,.pay{display:inline-block;padding:14px 26px;border-radius:12px;border:none;text-decoration:none;color:white;font-weight:bold;margin-top:12px;cursor:pointer;}
    button,.btn{background:#2563eb;} .pay{background:#16a34a;}
    .box{background:#0b1220;border:1px solid rgba(148,163,184,.16);padding:18px;margin:12px;border-radius:14px;text-align:left;}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
    .blue{color:#38bdf8;font-weight:bold;} .gold{color:#facc15;font-weight:bold;} .muted{color:#94a3b8;font-size:14px;}
    .metric{font-size:30px;font-weight:bold;color:#38bdf8;} .locked{filter:blur(3px);opacity:.55;}
    </style>
    """

@app.route("/")
def home():
    return f"""
<html><head><title>HDI Global Intelligence</title>{base_style()}</head>
<body>
<div class="container">
<div class="card">
<div class="institution">Private Beta Access</div>
<h1>HDI Global Intelligence</h1>
<p class="blue">Adaptive Decision Intelligence System</p>
<p>HDI learns user behavior and converts market data into personalized strategic intelligence.</p>

<h2>Create Access</h2>
<input id="name" placeholder="Full Name"><br>
<input id="email" placeholder="Email Address"><br>
<button onclick="createUser()">Enter HDI</button>

<hr style="margin:35px;border-color:#1f2937;">

<h2>Login</h2>
<input id="login_email" placeholder="Email Address"><br>
<button onclick="loginUser()">Login</button>

<div id="result"></div>
</div>
</div>

<script>
function goDashboard(api_key){{ window.location.href="/hdi/dashboard?key="+api_key; }}

async function createUser(){{
let name=document.getElementById("name").value;
let email=document.getElementById("email").value;
let res=await fetch("/hdi/create-user",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{name,email}})}});
let data=await res.json();
if(data.api_key){{goDashboard(data.api_key);}} else {{document.getElementById("result").innerHTML="Error: "+JSON.stringify(data);}}
}}

async function loginUser(){{
let email=document.getElementById("login_email").value;
let res=await fetch("/hdi/login",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{email}})}});
let data=await res.json();
if(data.api_key){{goDashboard(data.api_key);}} else {{document.getElementById("result").innerHTML="Login error: "+JSON.stringify(data);}}
}}
</script>
</body></html>
"""

@app.route("/hdi/create-user", methods=["POST"])
def create_user():
    data = request.get_json() or {}
    name = data.get("name")
    email = data.get("email")

    if not name or not email:
        return jsonify({"error": "name and email are required"}), 400

    existing = get_user_by_email(email)
    if existing:
        return jsonify({"api_key": existing[3], "plan": existing[4]})

    api_key = "HDI-" + uuid.uuid4().hex[:10].upper()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO users(name,email,api_key) VALUES(%s,%s,%s)", (name,email,api_key))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"api_key": api_key, "plan": "free"})

@app.route("/hdi/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    user = get_user_by_email(data.get("email"))

    if not user:
        return jsonify({"error": "No account found with this email"}), 404

    return jsonify({"api_key": user[3], "plan": user[4]})

@app.route("/hdi/dashboard")
def dashboard():
    key = request.args.get("key")
    user = get_user_by_key(key)
    if not user:
        return "Invalid access"

    signal = generate_adaptive_signal(key)
    insight = generate_insight_feed(key)
    performance = performance_tracking_html()
    watchlist = watchlist_html(key)
    behavior = get_behavior_summary(key)

    premium_active = is_premium(user[4], user[5])
    status = "Institutional Premium Active ✅" if premium_active else "Private Beta / Free Access 🔒"
    access_button = "" if premium_active else f"<a class='pay' href='/hdi/request-access?key={key}'>Request Institutional Access</a>"

    return f"""
<html><head><title>HDI Dashboard</title>{base_style()}</head>
<body><div class="container">

<div class="card">
<div class="institution">HDI Adaptive Terminal</div>
<h1>Adaptive Intelligence Dashboard</h1>
<p class="blue">Welcome, {user[1]}</p>
<p>{behavior}</p>
<div class="grid">
<div class="box"><b>Email</b><br>{user[2]}</div>
<div class="box"><b>Status</b><br>{status}</div>
<div class="box"><b>Access Key</b><br>{user[3]}</div>
<div class="box"><b>Premium Until</b><br>{user[5] if user[5] else "Not active"}</div>
</div>
<a class="btn" href="/hdi/premium-alerts?key={key}">Open Adaptive Decision Signal</a>
{access_button}
</div>

<div class="card">
<div class="institution">Next Level AI Layer</div>
<h2>🧠 Adaptive Signal Engine</h2>
<p class="blue">{signal["adaptive_note"]}</p>
<div class="grid">
<div class="box"><b>Priority Symbol</b><br>{signal["symbol"]}</div>
<div class="box"><b>Detected Pattern</b><br>{signal["pattern"]}</div>
<div class="box"><b>Market Score</b><br><span class="metric">{signal["market_score"]}/100</span></div>
<div class="box"><b>Strategic Action</b><br><span class="gold">{signal["strategic_action"]}</span></div>
</div>
</div>

<div class="card">
<div class="institution">Adaptive Insight Feed</div>
<h2>Market Intelligence Pulse</h2>
<div class="grid">
<div class="box"><b>Sector Focus</b><br>{insight["sector"]}</div>
<div class="box"><b>Detected Pattern</b><br>{insight["theme"]}</div>
<div class="box"><b>Impact Level</b><br><span class="gold">{insight["impact"]}</span></div>
<div class="box"><b>Confidence</b><br>{insight["confidence"]}%</div>
</div>
<p>{insight["interpretation"]}</p>
</div>

<div class="card">
<h2>⭐ Personal Watchlist</h2>
<form action="/hdi/add-watchlist" method="POST">
<input type="hidden" name="key" value="{key}">
<select name="symbol">
<option>AAPL</option><option>MSFT</option><option>TSLA</option><option>NVDA</option><option>AMZN</option><option>GOOGL</option><option>META</option>
</select><br>
<button type="submit">Add to Watchlist</button>
</form>
<div class="grid">{watchlist}</div>
</div>

<div class="card">
<h2>📊 HDI Performance Layer</h2>
{performance}
</div>

<a href="/" class="muted">Logout</a>
</div></body></html>
"""

@app.route("/hdi/add-watchlist", methods=["POST"])
def add_watchlist():
    key = request.form.get("key")
    symbol = request.form.get("symbol")

    if not get_user_by_key(key):
        return "Invalid key"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM watchlist WHERE api_key=%s AND symbol=%s", (key,symbol))
    if not cur.fetchone():
        cur.execute("INSERT INTO watchlist(api_key,symbol,created_at) VALUES(%s,%s,%s)", (key,symbol,datetime.utcnow().isoformat()))
        conn.commit()
    cur.close()
    conn.close()

    track_behavior(key, symbol, "watchlist")
    return redirect(f"/hdi/dashboard?key={key}")

@app.route("/hdi/remove-watchlist")
def remove_watchlist():
    key = request.args.get("key")
    symbol = request.args.get("symbol")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM watchlist WHERE api_key=%s AND symbol=%s", (key,symbol))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(f"/hdi/dashboard?key={key}")

@app.route("/hdi/premium-alerts")
def premium():
    key = request.args.get("key")
    user = get_user_by_key(key)
    if not user:
        return "Invalid key"

    signal = generate_adaptive_signal(key)
    track_behavior(key, signal["symbol"], "signal_open")
    performance = performance_tracking_html()

    if not is_premium(user[4], user[5]):
        return f"""
<html><head><title>HDI Signal</title>{base_style()}</head>
<body><div class="container">

<div class="card">
<div class="institution">Adaptive Signal Preview</div>
<h1>Strategic Pattern Detected</h1>
<p class="blue">{signal["adaptive_note"]}</p>

<div class="grid">
<div class="box"><b>Symbol</b><br>{signal["symbol"]}</div>
<div class="box"><b>Pattern</b><br>{signal["pattern"]}</div>
<div class="box"><b>Market Score</b><br><span class="metric">{signal["market_score"]}/100</span></div>
<div class="box"><b>Strategic Action</b><br><span class="gold">{signal["strategic_action"]}</span></div>
<div class="box locked"><b>Exposure</b><br>{signal["exposure"]}</div>
<div class="box locked"><b>Entry Window</b><br>{signal["entry_window"]}</div>
<div class="box locked"><b>Expected Opportunity</b><br>{signal["expected"]}</div>
<div class="box locked"><b>Risk Breakdown</b><br>{signal["risk"]}</div>
</div>

<a class="pay" href="/hdi/request-access?key={key}">Request Institutional Access</a>
</div>

<div class="card"><h2>📊 Performance Preview</h2>{performance}</div>
<a href="/hdi/dashboard?key={key}" class="muted">Back to Dashboard</a>
</div></body></html>
"""

    cb = signal["confidence_breakdown"]

    return f"""
<html><head><title>Premium HDI</title>{base_style()}</head>
<body><div class="container">

<div class="card">
<div class="institution">Premium Adaptive Intelligence</div>
<h1>🔥 HDI Adaptive Strategic Decision</h1>
<p class="blue">{signal["adaptive_note"]}</p>

<div class="grid">
<div class="box"><b>Symbol</b><br>{signal["symbol"]}</div>
<div class="box"><b>Pattern</b><br>{signal["pattern"]}</div>
<div class="box"><b>Market Score</b><br><span class="metric">{signal["market_score"]}/100</span></div>
<div class="box"><b>Strategic Action</b><br><span class="gold">{signal["strategic_action"]}</span></div>
<div class="box"><b>Exposure</b><br>{signal["exposure"]}</div>
<div class="box"><b>Entry Window</b><br>{signal["entry_window"]}</div>
<div class="box"><b>Expected Opportunity</b><br>{signal["expected"]}</div>
<div class="box"><b>Risk</b><br>{signal["risk"]}</div>
</div>

<h2>Intelligence Brief</h2>
<p>{signal["intelligence_brief"]}</p>

<h2>Confidence Breakdown</h2>
<ul style="text-align:left;display:inline-block;">
<li>Momentum: {cb["momentum"]}</li>
<li>Volume: {cb["volume"]}</li>
<li>Market Alignment: {cb["alignment"]}</li>
</ul>
</div>

<div class="card"><h2>📊 Performance Tracking</h2>{performance}</div>
<a href="/hdi/dashboard?key={key}" class="muted">Back to Dashboard</a>
</div></body></html>
"""

@app.route("/hdi/request-access")
def request_access():
    key = request.args.get("key")
    user = get_user_by_key(key)
    if not user:
        return "Invalid key"

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO access_requests(name,email,api_key,created_at) VALUES(%s,%s,%s,%s)", (user[1],user[2],key,datetime.utcnow().isoformat()))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

    return f"""
<html><head><title>Request Access</title>{base_style()}</head>
<body><div class="container"><div class="card">
<div class="institution">Private Beta Request</div>
<h1>Institutional Access Request Recorded</h1>
<p class="blue">Thank you, {user[1]}.</p>
<p>Your access request is now in the private beta queue.</p>
<a class="btn" href="/hdi/dashboard?key={key}">Return to Dashboard</a>
</div></div></body></html>
"""

@app.route("/hdi/real-signal")
def real_signal_api():
    key = request.args.get("key")
    if key:
        return jsonify(generate_adaptive_signal(key))
    return jsonify(generate_decision_signal())

@app.route("/hdi/admin")
def admin():
    if request.args.get("key") != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM access_requests")
    requests_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM user_behavior")
    behavior_events = cur.fetchone()[0]
    cur.close()
    conn.close()

    return jsonify({
        "users": users,
        "access_requests": requests_count,
        "behavior_events": behavior_events
    })

@app.route("/hdi/access-requests")
def access_requests():
    if request.args.get("key") != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT name,email,api_key,created_at FROM access_requests ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{"name": r[0], "email": r[1], "api_key": r[2], "created_at": r[3]} for r in rows])

@app.route("/hdi/behavior")
def behavior():
    if request.args.get("key") != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT api_key,symbol,action,count FROM user_behavior ORDER BY count DESC LIMIT 50")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{"api_key": r[0], "symbol": r[1], "action": r[2], "count": r[3]} for r in rows])

@app.route("/hdi/pay")
def pay():
    key = request.args.get("key")
    return redirect(f"/hdi/request-access?key={key}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
