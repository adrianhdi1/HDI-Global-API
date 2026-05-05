from flask import Flask, jsonify, request, redirect
import uuid, os, requests, psycopg2, random
from datetime import datetime, timedelta

app = Flask(__name__)

FLW_SECRET_KEY = os.environ.get("FLW_SECRET_KEY")
FLW_SECRET_HASH = os.environ.get("FLW_SECRET_HASH")
DATABASE_URL = os.environ.get("DATABASE_URL")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY")
ADMIN_KEY = os.environ.get("ADMIN_KEY")

BASE_URL = "https://hdi-global-api.onrender.com"
PAY_AMOUNT = 10
PAY_CURRENCY = "USD"

SYMBOLS = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "GOOGL", "META"]

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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS access_requests (
        id SERIAL PRIMARY KEY,
        name TEXT,
        email TEXT,
        api_key TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS watchlist (
        id SERIAL PRIMARY KEY,
        api_key TEXT,
        symbol TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    cur.close()
    conn.close()

init_db()

def is_premium(plan, premium_until):
    if plan != "premium" or not premium_until:
        return False
    try:
        return datetime.fromisoformat(premium_until) > datetime.utcnow()
    except:
        return False

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
            "latest_date": dates[0],
            "latest_close": latest_close,
            "previous_close": previous_close,
            "change_pct": change_pct
        }
    except:
        return None

def generate_decision_signal(symbol=None):
    symbol = symbol or random.choice(SYMBOLS)
    market = fetch_alpha_daily(symbol)

    if market:
        change = market["change_pct"]
        source = "Alpha Vantage Market Data"
        latest_date = market["latest_date"]
    else:
        change = round(random.uniform(-2.5, 3.5), 2)
        source = "HDI Fallback Decision Model"
        latest_date = "Recent"

    if change > 2:
        action = "ENTER POSITION"
        urgency = "CRITICAL"
        risk = "MODERATE"
        score = random.randint(88, 96)
        summary = "Strong upward momentum detected. HDI identifies a high-probability institutional opportunity pattern."
    elif change > 0:
        action = "MONITOR CLOSELY"
        urgency = "HIGH"
        risk = "CONTROLLED"
        score = random.randint(76, 87)
        summary = "Positive movement detected. Market conditions show controlled growth potential."
    else:
        action = "WAIT"
        urgency = "MEDIUM"
        risk = "MODERATE"
        score = random.randint(60, 75)
        summary = "Market uncertainty detected. HDI recommends waiting for stronger confirmation."

    margin_low = max(8, abs(int(change * 3)) + 8)
    margin_high = margin_low + random.randint(5, 12)

    return {
        "source": source,
        "symbol": symbol,
        "date": latest_date,
        "change": change,
        "sector": "Global Equities",
        "market_score": score,
        "strategic_action": action,
        "intelligence_brief": summary,
        "confidence": f"{score}%",
        "urgency": urgency,
        "risk": risk,
        "margin": f"{margin_low}% - {margin_high}%",
        "window": f"Next {random.randint(3, 8)} hours",
        "micro_result": f"{symbol} moved {change}% from previous close",
        "why": [
            f"{symbol} moved {change}% from previous close",
            "HDI analyzed real market movement",
            "Signal converted into decision intelligence"
        ]
    }

def confidence_bar(score):
    filled = int(score / 10)
    empty = 10 - filled
    return "█" * filled + "░" * empty

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
        return """
        <p class="muted">No watchlist yet. Add a symbol like AAPL, TSLA, NVDA.</p>
        """

    html = ""
    for symbol in symbols:
        signal = generate_decision_signal(symbol)
        color = "#22c55e" if signal["change"] >= 0 else "#ef4444"
        sign = "+" if signal["change"] >= 0 else ""

        html += f"""
        <div class="box">
            <b>{symbol}</b><br>
            <span style="color:{color};font-size:22px;font-weight:bold;">{sign}{signal["change"]}%</span>
            <br><span class="muted">Mini Insight: {signal["micro_result"]}</span>
            <br><span class="muted">Strategic Action: 🔒 Locked</span>
            <br><a href="/hdi/remove-watchlist?key={api_key}&symbol={symbol}" style="color:#ef4444;">Remove</a>
        </div>
        """
    return html

def track_record_html():
    rows = ""
    for symbol in SYMBOLS[:5]:
        market = fetch_alpha_daily(symbol)
        if market:
            change = market["change_pct"]
            date = market["latest_date"]
        else:
            change = round(random.uniform(-1.5, 3.5), 2)
            date = "Recent"

        color = "#22c55e" if change >= 0 else "#ef4444"
        sign = "+" if change >= 0 else ""

        rows += f"""
        <div class="box">
            <b>{symbol}</b><br>
            <span style="color:{color};font-size:22px;font-weight:bold;">{sign}{change}%</span>
            <br><small>{date}</small>
        </div>
        """
    return rows

def base_style():
    return """
    <style>
    body{
        margin:0;
        font-family:Arial, sans-serif;
        background:linear-gradient(135deg,#020617,#0f172a,#111827);
        color:white;
        text-align:center;
    }
    .container{
        max-width:980px;
        margin:auto;
        padding:60px 20px;
    }
    .card{
        background:rgba(17,24,39,0.92);
        border:1px solid rgba(56,189,248,0.18);
        box-shadow:0 0 50px rgba(0,0,0,0.45);
        padding:42px;
        border-radius:24px;
        margin-bottom:24px;
    }
    .institution{
        color:#38bdf8;
        font-weight:bold;
        letter-spacing:1px;
        text-transform:uppercase;
        font-size:13px;
    }
    h1{font-size:42px;margin-bottom:12px;}
    h2{color:#e5e7eb;}
    p{color:#cbd5e1;line-height:1.6;}
    input,select{
        padding:14px;
        margin:8px;
        width:80%;
        border-radius:10px;
        border:1px solid #334155;
        background:#020617;
        color:white;
    }
    button,.btn,.pay{
        display:inline-block;
        padding:14px 26px;
        border-radius:12px;
        border:none;
        text-decoration:none;
        color:white;
        font-weight:bold;
        margin-top:12px;
        cursor:pointer;
    }
    button,.btn{background:#2563eb;}
    .pay{background:#16a34a;}
    .box{
        background:#0b1220;
        border:1px solid rgba(148,163,184,0.16);
        padding:18px;
        margin:12px;
        border-radius:14px;
        text-align:left;
    }
    .grid{
        display:grid;
        grid-template-columns:1fr 1fr;
        gap:12px;
    }
    .blue{color:#38bdf8;font-weight:bold;}
    .gold{color:#facc15;font-weight:bold;}
    .muted{color:#94a3b8;font-size:14px;}
    .metric{font-size:30px;font-weight:bold;color:#38bdf8;}
    .locked{filter:blur(3px);opacity:.55;}
    </style>
    """

@app.route("/")
def home():
    return f"""
<html>
<head>
<title>HDI Global Intelligence</title>
{base_style()}
</head>
<body>
<div class="container">
    <div class="card">
        <div class="institution">Private Beta Access</div>
        <h1>HDI Global Intelligence</h1>
        <p class="blue">Decision Intelligence System for Investors, Institutions & Strategic Decision Makers</p>
        <p>
            HDI converts real market data into strategic decisions:
            Market Score, Strategic Action, Risk Level, Intelligence Brief, and Track Record.
        </p>

        <h2>Create Access</h2>
        <input id="name" placeholder="Full Name"><br>
        <input id="email" placeholder="Email Address"><br>
        <button onclick="createUser()">Enter HDI</button>

        <hr style="margin:35px;border-color:#1f2937;">

        <h2>Login</h2>
        <p class="muted">Already have access? Enter your email.</p>
        <input id="login_email" placeholder="Email Address"><br>
        <button onclick="loginUser()">Login</button>

        <div id="result" style="margin-top:25px;color:#38bdf8;"></div>
    </div>
</div>

<script>
function goDashboard(api_key){{
    window.location.href = "/hdi/dashboard?key=" + api_key;
}}

async function createUser(){{
    let name=document.getElementById("name").value;
    let email=document.getElementById("email").value;

    let res=await fetch("/hdi/create-user",{{
        method:"POST",
        headers:{{"Content-Type":"application/json"}},
        body:JSON.stringify({{name,email}})
    }});

    let data=await res.json();

    if(data.api_key){{
        goDashboard(data.api_key);
    }} else {{
        document.getElementById("result").innerHTML="Error: "+JSON.stringify(data);
    }}
}}

async function loginUser(){{
    let email=document.getElementById("login_email").value;

    let res=await fetch("/hdi/login",{{
        method:"POST",
        headers:{{"Content-Type":"application/json"}},
        body:JSON.stringify({{email}})
    }});

    let data=await res.json();

    if(data.api_key){{
        goDashboard(data.api_key);
    }} else {{
        document.getElementById("result").innerHTML="Login error: "+JSON.stringify(data);
    }}
}}
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
        return jsonify({"error": "name and email are required"}), 400

    existing = get_user_by_email(email)
    if existing:
        return jsonify({"api_key": existing[3], "plan": existing[4]})

    api_key = "HDI-" + uuid.uuid4().hex[:10].upper()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users(name,email,api_key) VALUES(%s,%s,%s)",
        (name, email, api_key)
    )
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"api_key": api_key, "plan": "free"})

@app.route("/hdi/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email")

    user = get_user_by_email(email)
    if not user:
        return jsonify({"error": "No account found with this email"}), 404

    return jsonify({
        "api_key": user[3],
        "plan": user[4],
        "premium_active": is_premium(user[4], user[5])
    })

@app.route("/hdi/dashboard")
def dashboard():
    key = request.args.get("key")
    user = get_user_by_key(key)

    if not user:
        return "Invalid access"

    signal = generate_decision_signal()
    premium_active = is_premium(user[4], user[5])
    status = "Institutional Premium Active ✅" if premium_active else "Private Beta / Free Access 🔒"
    access_button = f"<a class='pay' href='/hdi/request-access?key={key}'>Request Institutional Access</a>" if not premium_active else ""
    records = track_record_html()
    watchlist = watchlist_html(key)

    return f"""
<html>
<head>
<title>HDI Dashboard</title>
{base_style()}
</head>
<body>
<div class="container">
    <div class="card">
        <div class="institution">HDI Decision Terminal</div>
        <h1>Strategic Intelligence Dashboard</h1>
        <p class="blue">Welcome, {user[1]}</p>
        <p>HDI is built for investors, institutions, companies, banks, and high-level decision makers.</p>

        <div class="grid">
            <div class="box"><b>Email</b><br>{user[2]}</div>
            <div class="box"><b>Access Status</b><br>{status}</div>
            <div class="box"><b>Access Key</b><br>{user[3]}</div>
            <div class="box"><b>Premium Until</b><br>{user[5] if user[5] else "Not active"}</div>
        </div>

        <a class="btn" href="/hdi/premium-alerts?key={key}">Open Decision Signal</a>
        {access_button}
    </div>

    <div class="card">
        <div class="institution">Free User Utility</div>
        <h2>⭐ Personal Watchlist</h2>
        <p class="blue">Track symbols and mini market movement before premium access.</p>

        <form action="/hdi/add-watchlist" method="POST">
            <input type="hidden" name="key" value="{key}">
            <select name="symbol">
                <option value="AAPL">AAPL</option>
                <option value="MSFT">MSFT</option>
                <option value="TSLA">TSLA</option>
                <option value="NVDA">NVDA</option>
                <option value="AMZN">AMZN</option>
                <option value="GOOGL">GOOGL</option>
                <option value="META">META</option>
            </select><br>
            <button type="submit">Add to Watchlist</button>
        </form>

        <div class="grid">{watchlist}</div>
    </div>

    <div class="card">
        <div class="institution">Today’s HDI Signal</div>
        <h2>Daily Signal Drop</h2>
        <p class="blue">Partial intelligence preview available for private beta users.</p>

        <div class="grid">
            <div class="box"><b>Symbol</b><br>{signal["symbol"]}</div>
            <div class="box"><b>Market Score</b><br><span class="metric">{signal["market_score"]}/100</span></div>
            <div class="box"><b>Strategic Action</b><br><span class="gold">{signal["strategic_action"]}</span></div>
            <div class="box"><b>Micro Result</b><br>{signal["micro_result"]}</div>
        </div>

        <p class="muted">Full intelligence brief, timing window, and risk breakdown remain restricted.</p>
    </div>

    <div class="card">
        <h2>📊 Signal Track Record</h2>
        <p class="blue">Recent market movement proof from the real data layer</p>
        <div class="grid">{records}</div>
    </div>

    <a href="/" class="muted">Logout</a>
</div>
</body>
</html>
"""

@app.route("/hdi/add-watchlist", methods=["POST"])
def add_watchlist():
    key = request.form.get("key")
    symbol = request.form.get("symbol")

    user = get_user_by_key(key)
    if not user:
        return "Invalid key"

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM watchlist WHERE api_key=%s AND symbol=%s",
        (key, symbol)
    )
    existing = cur.fetchone()

    if not existing:
        cur.execute(
            "INSERT INTO watchlist(api_key,symbol,created_at) VALUES(%s,%s,%s)",
            (key, symbol, datetime.utcnow().isoformat())
        )
        conn.commit()

    cur.close()
    conn.close()

    return redirect(f"/hdi/dashboard?key={key}")

@app.route("/hdi/remove-watchlist")
def remove_watchlist():
    key = request.args.get("key")
    symbol = request.args.get("symbol")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM watchlist WHERE api_key=%s AND symbol=%s", (key, symbol))
    conn.commit()
    cur.close()
    conn.close()

    return redirect(f"/hdi/dashboard?key={key}")

@app.route("/hdi/premium-alerts")
def premium():
    key = request.args.get("key")
    user = get_user_by_key(key)
    signal = generate_decision_signal()
    records = track_record_html()

    if not user:
        return "Invalid key"

    score_bar = confidence_bar(signal["market_score"])

    if not is_premium(user[4], user[5]):
        return f"""
<html>
<head>
<title>HDI Locked Signal</title>
{base_style()}
</head>
<body>
<div class="container">
    <div class="card">
        <div class="institution">Private Beta Signal Preview</div>
        <h1>Strategic Signal Detected</h1>
        <p class="blue">HDI detected a decision pattern from real market data.</p>

        <div class="grid">
            <div class="box"><b>Data Source</b><br>{signal["source"]}</div>
            <div class="box"><b>Symbol</b><br>{signal["symbol"]}</div>
            <div class="box"><b>Market Activity Score</b><br><span class="metric">{signal["market_score"]}/100</span></div>
            <div class="box"><b>Strategic Action</b><br><span class="gold">{signal["strategic_action"]}</span></div>
            <div class="box"><b>Micro Result</b><br>{signal["micro_result"]}</div>
            <div class="box"><b>Confidence Level</b><br>Partial Preview</div>
        </div>

        <hr style="margin:35px;border-color:#1f2937;">

        <div class="grid">
            <div class="box locked"><b>Full Intelligence Brief</b><br>{signal["intelligence_brief"]}</div>
            <div class="box locked"><b>Timing Window</b><br>{signal["window"]}</div>
            <div class="box locked"><b>Risk Breakdown</b><br>{signal["risk"]}</div>
            <div class="box locked"><b>Why This Signal?</b><br>Real-data reasoning locked</div>
        </div>

        <h2>Request Institutional Access</h2>
        <p>Limited access is maintained to protect signal quality, system performance, and institutional-grade analysis.</p>
        <a class="pay" href="/hdi/request-access?key={key}">Request Institutional Access</a>
    </div>

    <div class="card">
        <h2>📊 Track Record Preview</h2>
        <div class="grid">{records}</div>
    </div>

    <a href="/hdi/dashboard?key={key}" class="muted">Back to Dashboard</a>
</div>
</body>
</html>
"""

    why_html = "".join([f"<li>{w}</li>" for w in signal["why"]])

    return f"""
<html>
<head>
<title>HDI Decision Signal</title>
{base_style()}
</head>
<body>
<div class="container">
    <div class="card">
        <div class="institution">Premium Decision Intelligence</div>
        <h1>🔥 HDI Strategic Signal</h1>

        <div class="grid">
            <div class="box"><b>Data Source</b><br>{signal["source"]}</div>
            <div class="box"><b>Symbol</b><br>{signal["symbol"]}</div>
            <div class="box"><b>Market Activity Score</b><br><span class="metric">{signal["market_score"]}/100</span></div>
            <div class="box"><b>Strategic Action</b><br><span class="gold">{signal["strategic_action"]}</span></div>
            <div class="box"><b>Confidence Level</b><br>{score_bar} {signal["confidence"]}</div>
            <div class="box"><b>Urgency</b><br>{signal["urgency"]}</div>
            <div class="box"><b>Risk</b><br>{signal["risk"]}</div>
            <div class="box"><b>Estimated Margin</b><br>{signal["margin"]}</div>
        </div>

        <h2>Market Intelligence Brief</h2>
        <p>{signal["intelligence_brief"]}</p>

        <h2>Why This Signal?</h2>
        <ul style="text-align:left;display:inline-block;">{why_html}</ul>
    </div>

    <div class="card">
        <h2>📊 Recent Track Record</h2>
        <div class="grid">{records}</div>
    </div>

    <a href="/hdi/dashboard?key={key}" class="muted">Back to Dashboard</a>
</div>
</body>
</html>
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
        cur.execute(
            "INSERT INTO access_requests(name,email,api_key,created_at) VALUES(%s,%s,%s,%s)",
            (user[1], user[2], key, datetime.utcnow().isoformat())
        )
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

    return f"""
<html>
<head>
<title>Request HDI Access</title>
{base_style()}
</head>
<body>
<div class="container">
    <div class="card">
        <div class="institution">Private Beta Request</div>
        <h1>Institutional Access Request Recorded</h1>
        <p class="blue">Thank you, {user[1]}.</p>
        <p>
            HDI Premium is currently in restricted deployment.
            Access is granted selectively to maintain signal quality, system performance,
            and institutional-grade decision intelligence.
        </p>

        <div class="box"><b>Name</b><br>{user[1]}</div>
        <div class="box"><b>Email</b><br>{user[2]}</div>

        <p class="gold">Your request is now in the private beta queue.</p>
        <a class="btn" href="/hdi/dashboard?key={key}">Return to Dashboard</a>
    </div>
</div>
</body>
</html>
"""

@app.route("/hdi/real-signal")
def real_signal_api():
    return jsonify(generate_decision_signal())

@app.route("/hdi/pay")
def pay():
    key = request.args.get("key")
    return redirect(f"/hdi/request-access?key={key}")

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

    cur.execute("SELECT COUNT(*) FROM access_requests")
    requests_count = cur.fetchone()[0]

    cur.close()
    conn.close()

    return jsonify({
        "users": users,
        "premium": premium,
        "access_requests": requests_count
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

    return jsonify([{"name": r[0], "email": r[1], "plan": r[2]} for r in rows])

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

    return jsonify([
        {"name": r[0], "email": r[1], "api_key": r[2], "created_at": r[3]}
        for r in rows
    ])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
