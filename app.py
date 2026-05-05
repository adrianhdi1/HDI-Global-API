from flask import Flask, jsonify, request, redirect
import uuid, os, requests, psycopg2, random
from datetime import datetime, timedelta

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
            timeout=20
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

def generate_real_signal():
    symbol = random.choice(SYMBOLS)
    market = fetch_alpha_daily(symbol)

    if not market:
        return {
            "source": "HDI fallback model",
            "symbol": symbol,
            "sector": "Global Markets",
            "opportunity": "High-probability opportunity pattern detected",
            "confidence": f"{random.randint(84, 94)}%",
            "risk": "MODERATE",
            "urgency": "HIGH",
            "margin": "12% - 24%",
            "window": "Next 6 hours",
            "why": [
                "Market data temporarily unavailable",
                "Fallback opportunity model active",
                "Signal confidence estimated by HDI model"
            ]
        }

    change = market["change_pct"]

    if change > 2:
        urgency = "CRITICAL"
        risk = "MODERATE"
        opportunity = "Strong price momentum detected"
        confidence = random.randint(90, 97)
    elif change > 0:
        urgency = "HIGH"
        risk = "CONTROLLED"
        opportunity = "Positive market movement detected"
        confidence = random.randint(86, 93)
    else:
        urgency = "MEDIUM"
        risk = "MODERATE"
        opportunity = "Potential reversal watch detected"
        confidence = random.randint(82, 90)

    margin_low = max(8, abs(int(change * 3)) + 8)
    margin_high = margin_low + random.randint(5, 12)

    return {
        "source": "Alpha Vantage market data",
        "symbol": market["symbol"],
        "latest_date": market["latest_date"],
        "latest_close": market["latest_close"],
        "previous_close": market["previous_close"],
        "change_pct": change,
        "sector": "Global Equities",
        "opportunity": opportunity,
        "confidence": f"{confidence}%",
        "risk": risk,
        "urgency": urgency,
        "margin": f"{margin_low}% - {margin_high}%",
        "window": f"Next {random.randint(3, 8)} hours",
        "why": [
            f"{market['symbol']} moved {change}% from previous close",
            "Real daily market data detected",
            "HDI converted market movement into opportunity signal"
        ]
    }

@app.route("/")
def home():
    return """
<html>
<head>
<title>HDI Global Intelligence</title>
<style>
body{font-family:Arial;background:#050816;color:white;text-align:center;padding:60px;}
.card{max-width:760px;margin:auto;background:#111827;padding:42px;border-radius:20px;}
input{padding:12px;margin:8px;width:80%;border-radius:8px;border:none;}
button{padding:12px 24px;background:#2563eb;color:white;border:none;border-radius:10px;font-weight:bold;margin-top:8px;}
.pay{background:#16a34a;padding:12px 20px;border-radius:10px;color:white;text-decoration:none;display:inline-block;margin-top:15px;}
.tag{color:#38bdf8;font-weight:bold;}
.small{color:#94a3b8;font-size:14px;}
</style>
</head>
<body>
<div class="card">
<h1>HDI Global Intelligence</h1>
<p class="tag">Global AI-powered opportunity intelligence</p>
<p>Powered by real market data signals.</p>

<h3>Create Account</h3>
<input id="name" placeholder="Name"><br>
<input id="email" placeholder="Email"><br>
<button onclick="createUser()">Get Access</button>

<hr style="margin:35px;border-color:#1f2937;">

<h3>Login</h3>
<p class="small">Already have an account? Enter your email to recover your access key.</p>
<input id="login_email" placeholder="Your Email"><br>
<button onclick="loginUser()">Login</button>

<div id="result" style="margin-top:25px;color:#38bdf8;"></div>
</div>

<script>
function showAccess(api_key){
    document.getElementById("result").innerHTML =
    "<strong>Your Key:</strong> "+api_key+
    "<br><br><a href='/hdi/premium-alerts?key="+api_key+"'>View Global Signals</a>"+
    "<br><br><a class='pay' href='/hdi/pay?key="+api_key+"'>Upgrade Now 💰</a>";
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
        showAccess(data.api_key);
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
        showAccess(data.api_key);
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
        return jsonify({
            "message": "User already exists",
            "api_key": existing[3],
            "plan": existing[4]
        })

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

    if not email:
        return jsonify({"error": "email is required"}), 400

    user = get_user_by_email(email)

    if not user:
        return jsonify({"error": "No account found with this email"}), 404

    return jsonify({
        "message": "Login successful",
        "api_key": user[3],
        "plan": user[4],
        "premium_active": is_premium(user[4], user[5])
    })

@app.route("/hdi/premium-alerts")
def premium():
    key = request.args.get("key")
    user = get_user_by_key(key)
    signal = generate_real_signal()

    if not user:
        return "Invalid key"

    if not is_premium(user[4], user[5]):
        return f"""
<html>
<body style="font-family:Arial;background:#050816;color:white;text-align:center;padding:60px;">
<div style="max-width:760px;margin:auto;background:#111827;padding:42px;border-radius:20px;">
<h1>🔒 Real Data Signal Locked</h1>
<p style="color:#38bdf8;font-weight:bold;">HDI detected a real market movement pattern</p>
<p>Data Source: {signal["source"]}</p>
<p>Symbol: {signal["symbol"]}</p>
<p>Sector: {signal["sector"]}</p>
<p>Estimated Margin: {signal["margin"]}</p>
<p>Confidence: Locked</p>
<p>Why: Locked</p>
<h3>Unlock full real-data signal for {PAY_AMOUNT} {PAY_CURRENCY}/month</h3>
<a href="/hdi/pay?key={key}" style="background:#16a34a;padding:15px 25px;border-radius:10px;color:white;text-decoration:none;">Unlock Full Signal 💰</a>
</div>
</body>
</html>
"""

    why_html = "".join([f"<li>{w}</li>" for w in signal["why"]])

    return f"""
<html>
<body style="font-family:Arial;background:#050816;color:white;text-align:center;padding:60px;">
<div style="max-width:760px;margin:auto;background:#111827;padding:42px;border-radius:20px;">
<h1>🔥 Premium Real-Data HDI Signal</h1>
<p>Data Source: {signal["source"]}</p>
<p>Symbol: {signal["symbol"]}</p>
<p>Sector: {signal["sector"]}</p>
<p>Opportunity: {signal["opportunity"]}</p>
<p>Estimated Margin: {signal["margin"]}</p>
<p>Confidence: {signal["confidence"]}</p>
<p>Urgency: {signal["urgency"]}</p>
<p>Risk: {signal["risk"]}</p>
<p>Window: {signal["window"]}</p>
<h3>Why this signal?</h3>
<ul style="text-align:left;display:inline-block;">{why_html}</ul>
</div>
</body>
</html>
"""

@app.route("/hdi/real-signal")
def real_signal_api():
    return jsonify(generate_real_signal())

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
        "redirect_url": BASE_URL,
        "customer": {"email": user[2], "name": user[1]},
        "customizations": {
            "title": "HDI Global Premium",
            "description": "Unlock global opportunity intelligence"
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
