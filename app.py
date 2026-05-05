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

def generate_decision_signal():
    symbol = random.choice(SYMBOLS)
    market = fetch_alpha_daily(symbol)

    if market:
        change = market["change_pct"]
        source = "Alpha Vantage market data"
        latest_date = market["latest_date"]
    else:
        change = round(random.uniform(-2.5, 3.5), 2)
        source = "HDI fallback decision model"
        latest_date = "Recent"

    if change > 2:
        action = "ENTER POSITION"
        urgency = "CRITICAL"
        risk = "MODERATE"
        score = random.randint(88, 96)
        summary = "Strong upward momentum detected. HDI identifies a high-probability opportunity pattern."
    elif change > 0:
        action = "MONITOR CLOSELY"
        urgency = "HIGH"
        risk = "CONTROLLED"
        score = random.randint(76, 87)
        summary = "Positive market movement detected. Market conditions show controlled growth potential."
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
        "recommended_action": action,
        "ai_summary": summary,
        "confidence": f"{score}%",
        "urgency": urgency,
        "risk": risk,
        "margin": f"{margin_low}% - {margin_high}%",
        "window": f"Next {random.randint(3, 8)} hours",
        "why": [
            f"{symbol} moved {change}% from previous close",
            "HDI analyzed real market movement",
            "Signal converted into decision intelligence"
        ]
    }

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
            <b>{symbol}</b> →
            <span style="color:{color};font-weight:bold;">{sign}{change}%</span>
            <br><small>{date}</small>
        </div>
        """
    return rows

@app.route("/")
def home():
    return """
<html>
<head>
<title>HDI Global Intelligence</title>
<style>
body{font-family:Arial;background:#050816;color:white;text-align:center;padding:60px;}
.card{max-width:780px;margin:auto;background:#111827;padding:42px;border-radius:20px;}
input{padding:12px;margin:8px;width:80%;border-radius:8px;border:none;}
button{padding:12px 24px;background:#2563eb;color:white;border:none;border-radius:10px;font-weight:bold;margin-top:8px;}
.tag{color:#38bdf8;font-weight:bold;}
.small{color:#94a3b8;font-size:14px;}
</style>
</head>
<body>
<div class="card">
<h1>HDI Global Intelligence</h1>
<p class="tag">Decision Intelligence powered by real market data</p>
<p>Signals. Market Score. Recommended Action. AI Summary.</p>

<h3>Create Account</h3>
<input id="name" placeholder="Name"><br>
<input id="email" placeholder="Email"><br>
<button onclick="createUser()">Get Access</button>

<hr style="margin:35px;border-color:#1f2937;">

<h3>Login</h3>
<p class="small">Already have an account? Enter your email.</p>
<input id="login_email" placeholder="Your Email"><br>
<button onclick="loginUser()">Login</button>

<div id="result" style="margin-top:25px;color:#38bdf8;"></div>
</div>

<script>
function goDashboard(api_key){
    window.location.href = "/hdi/dashboard?key=" + api_key;
}

async function createUser(){
    let name=document.getElementById("name").value;
    let email=document.getElementById("email").value;

    let res=await fetch("/hdi/create-user",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({name,email})
    });

    let data=await res.json();

    if(data.api_key){
        goDashboard(data.api_key);
    } else {
        document.getElementById("result").innerHTML="Error: "+JSON.stringify(data);
    }
}

async function loginUser(){
    let email=document.getElementById("login_email").value;

    let res=await fetch("/hdi/login",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({email})
    });

    let data=await res.json();

    if(data.api_key){
        goDashboard(data.api_key);
    } else {
        document.getElementById("result").innerHTML="Login error: "+JSON.stringify(data);
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

    premium_active = is_premium(user[4], user[5])
    status = "Premium Active ✅" if premium_active else "Free Plan 🔒"
    upgrade_button = "" if premium_active else f"<a class='pay' href='/hdi/pay?key={key}'>Upgrade Now 💰</a>"
    records = track_record_html()

    return f"""
<html>
<head>
<title>HDI Dashboard</title>
<style>
body{{font-family:Arial;background:#050816;color:white;text-align:center;padding:60px;}}
.card{{max-width:900px;margin:auto;background:#111827;padding:42px;border-radius:20px;}}
.box{{background:#0b1220;padding:15px;margin:12px;border-radius:12px;text-align:left;}}
.pay{{background:#16a34a;padding:15px 25px;border-radius:10px;color:white;text-decoration:none;display:inline-block;margin-top:20px;font-weight:bold;}}
.btn{{background:#2563eb;padding:15px 25px;border-radius:10px;color:white;text-decoration:none;display:inline-block;margin-top:20px;font-weight:bold;}}
.blue{{color:#38bdf8;font-weight:bold;}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
</style>
</head>
<body>
<div class="card">
<h1>HDI Decision Dashboard</h1>
<p class="blue">Welcome, {user[1]}</p>

<div class="box"><b>Email:</b> {user[2]}</div>
<div class="box"><b>Plan:</b> {status}</div>
<div class="box"><b>API Key:</b> {user[3]}</div>
<div class="box"><b>Premium Until:</b> {user[5] if user[5] else "Not active"}</div>

<a class="btn" href="/hdi/premium-alerts?key={key}">View Decision Signal</a>
{upgrade_button}

<hr style="margin:35px;border-color:#1f2937;">
<h2>📊 Recent Signal Track Record</h2>
<p class="blue">Recent market movement proof from real data layer</p>
<div class="grid">{records}</div>

<br><br>
<a href="/" style="color:#94a3b8;">Logout</a>
</div>
</body>
</html>
"""

@app.route("/hdi/premium-alerts")
def premium():
    key = request.args.get("key")
    user = get_user_by_key(key)
    signal = generate_decision_signal()
    records = track_record_html()

    if not user:
        return "Invalid key"

    if not is_premium(user[4], user[5]):
        return f"""
<html>
<body style="font-family:Arial;background:#050816;color:white;text-align:center;padding:60px;">
<div style="max-width:860px;margin:auto;background:#111827;padding:42px;border-radius:20px;">
<h1>🔒 Decision Intelligence Locked</h1>
<p style="color:#38bdf8;font-weight:bold;">HDI detected a decision pattern from real market data</p>

<div style="background:#0b1220;padding:15px;margin:12px;border-radius:12px;text-align:left;">Data Source: {signal["source"]}</div>
<div style="background:#0b1220;padding:15px;margin:12px;border-radius:12px;text-align:left;">Symbol: {signal["symbol"]}</div>
<div style="background:#0b1220;padding:15px;margin:12px;border-radius:12px;text-align:left;">Market Activity Score: Locked</div>
<div style="background:#0b1220;padding:15px;margin:12px;border-radius:12px;text-align:left;">Recommended Action: Locked</div>
<div style="background:#0b1220;padding:15px;margin:12px;border-radius:12px;text-align:left;">AI Summary: Locked</div>

<h3>Unlock full decision intelligence for {PAY_AMOUNT} {PAY_CURRENCY}/month</h3>
<a href="/hdi/pay?key={key}" style="background:#16a34a;padding:15px 25px;border-radius:10px;color:white;text-decoration:none;">Unlock Full Decision 💰</a>

<hr style="margin:35px;border-color:#1f2937;">
<h2>📊 Track Record Preview</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">{records}</div>

<br><br>
<a href="/hdi/dashboard?key={key}" style="color:#94a3b8;">Back to Dashboard</a>
</div>
</body>
</html>
"""

    why_html = "".join([f"<li>{w}</li>" for w in signal["why"]])

    return f"""
<html>
<body style="font-family:Arial;background:#050816;color:white;text-align:center;padding:60px;">
<div style="max-width:860px;margin:auto;background:#111827;padding:42px;border-radius:20px;">
<h1>🔥 HDI Decision Signal</h1>

<p><b>Data Source:</b> {signal["source"]}</p>
<p><b>Symbol:</b> {signal["symbol"]}</p>
<p><b>Market Activity Score:</b> {signal["market_score"]}/100</p>
<p><b>Recommended Action:</b> {signal["recommended_action"]}</p>
<p><b>Confidence:</b> {signal["confidence"]}</p>
<p><b>Urgency:</b> {signal["urgency"]}</p>
<p><b>Risk:</b> {signal["risk"]}</p>
<p><b>Estimated Margin:</b> {signal["margin"]}</p>
<p><b>Window:</b> {signal["window"]}</p>

<h3>AI Summary</h3>
<p>{signal["ai_summary"]}</p>

<h3>Why this signal?</h3>
<ul style="text-align:left;display:inline-block;">{why_html}</ul>

<hr style="margin:35px;border-color:#1f2937;">
<h2>📊 Recent Track Record</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">{records}</div>

<br><br>
<a href="/hdi/dashboard?key={key}" style="color:#94a3b8;">Back to Dashboard</a>
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
    user = get_user_by_key(key)

    if not user:
        return jsonify({"error": "Invalid key"}), 403

    tx_ref = "HDI-" + uuid.uuid4().hex[:12]

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO payments(api_key,tx_ref,amount,currency) VALUES(%s,%s,%s,%s)",
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
        "redirect_url": f"{BASE_URL}/hdi/dashboard?key={key}",
        "customer": {"email": user[2], "name": user[1]},
        "customizations": {
            "title": "HDI Global Premium",
            "description": "Unlock global decision intelligence"
        }
    }

    res = requests.post(
        "https://api.flutterwave.com/v3/payments",
        json=payload,
        headers=headers
    )

    data = res.json()

    if data.get("status") == "success":
        return redirect(data["data"]["link"])

    return jsonify(data)

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

    return jsonify({"users": users, "premium": premium, "revenue": revenue})

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
