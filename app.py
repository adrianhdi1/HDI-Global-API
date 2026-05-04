from flask import Flask, jsonify, request, redirect
import uuid
import os
import requests
import psycopg2
import random
from datetime import datetime, timedelta

app = Flask(__name__)

FLW_SECRET_KEY = os.environ.get("FLW_SECRET_KEY")
FLW_SECRET_HASH = os.environ.get("FLW_SECRET_HASH")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_KEY = os.environ.get("ADMIN_KEY")

BASE_URL = "https://hdi-global-api.onrender.com"
PAY_AMOUNT = 10
PAY_CURRENCY = "USD"

COUNTRIES = ["Tanzania","Kenya","Uganda","Rwanda","Nigeria","Ghana"]
SECTORS = ["Agriculture Export","Logistics","Energy","Fintech","Retail","Mining"]
OPPORTUNITIES = [
    "Demand surge detected",
    "Supply gap emerging",
    "Buyer interest increasing",
    "Price inefficiency detected"
]
RISKS = ["LOW","MODERATE"]
URGENCIES = ["HIGH","CRITICAL"]

def generate_signal():
    margin_low = random.randint(12,20)
    margin_high = margin_low + random.randint(5,10)

    return {
        "country": random.choice(COUNTRIES),
        "sector": random.choice(SECTORS),
        "opportunity": random.choice(OPPORTUNITIES),
        "margin": f"{margin_low}% - {margin_high}%",
        "confidence": f"{random.randint(85,97)}%",
        "urgency": random.choice(URGENCIES),
        "risk": random.choice(RISKS),
        "window_hours": random.randint(3,6),
        "unlocked_today": random.randint(10,40)
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
    cur.execute("""CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        api_key TEXT,
        tx_ref TEXT UNIQUE,
        amount REAL,
        currency TEXT,
        status TEXT DEFAULT 'pending'
    )""")
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
    cur.execute("SELECT * FROM users WHERE api_key=%s",(api_key,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

@app.route("/")
def home():
    return """
<html>
<head>
<title>HDI</title>
<style>
body{font-family:Arial;background:#050816;color:white;text-align:center;padding:60px;}
.card{max-width:700px;margin:auto;background:#111827;padding:40px;border-radius:20px;}
input{padding:12px;margin:8px;width:80%;border-radius:8px;border:none;}
button{padding:12px 24px;background:#2563eb;color:white;border:none;border-radius:10px;}
.pay{background:#16a34a;padding:12px 20px;border-radius:10px;color:white;text-decoration:none;display:inline-block;margin-top:15px;}
</style>
</head>
<body>
<div class="card">
<h1>HDI Intelligence</h1>
<p>AI opportunity signals</p>

<input id="name" placeholder="Name"><br>
<input id="email" placeholder="Email"><br>
<button onclick="createUser()">Get Access</button>

<div id="result"></div>
</div>

<script>
async function createUser(){
let name=document.getElementById("name").value;
let email=document.getElementById("email").value;

let res=await fetch("/hdi/create-user",{
method:"POST",
headers:{"Content-Type":"application/json"},
body:JSON.stringify({name,email})
});

let data=await res.json();

document.getElementById("result").innerHTML=
"Key: "+data.api_key+
"<br><a href='/hdi/premium-alerts?key="+data.api_key+"'>View Signals</a>"+
"<br><a class='pay' href='/hdi/pay?key="+data.api_key+"'>Upgrade 💰</a>";
}
</script>
</body>
</html>
"""

@app.route("/hdi/create-user", methods=["POST"])
def create_user():
    data=request.get_json()
    api_key="HDI-"+uuid.uuid4().hex[:10].upper()

    conn=get_conn()
    cur=conn.cursor()
    cur.execute("INSERT INTO users(name,email,api_key) VALUES(%s,%s,%s)",
    (data["name"],data["email"],api_key))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"api_key":api_key})

@app.route("/hdi/premium-alerts")
def premium():
    key=request.args.get("key")
    user=get_user_by_key(key)
    signal=generate_signal()

    if not user:
        return "Invalid key"

    if not is_premium(user[4],user[5]):
        hours=signal["window_hours"]

        return f"""
<html>
<head>
<style>
body{{font-family:Arial;background:#050816;color:white;text-align:center;padding:60px;}}
.card{{max-width:700px;margin:auto;background:#111827;padding:40px;border-radius:20px;}}
.box{{background:#0b1220;padding:15px;margin:10px;border-radius:10px;text-align:left;}}
.pay{{background:#16a34a;padding:15px 25px;border-radius:10px;color:white;text-decoration:none;display:inline-block;margin-top:20px;}}
</style>
</head>
<body>
<div class="card">
<h1>🔒 Signal Locked</h1>

<div class="box">Sector: {signal["sector"]}</div>
<div class="box">Margin: {signal["margin"]}</div>
<div class="box">Risk: {signal["risk"]}</div>

<div class="box">⏳ Window closes in: <span id="countdown"></span></div>

<p>🔥 {signal["unlocked_today"]} users unlocked today</p>

<a class="pay" href="/hdi/pay?key={key}">Upgrade Now 💰</a>
</div>

<script>
let seconds = {hours} * 3600;

function update(){{
let h=Math.floor(seconds/3600);
let m=Math.floor((seconds%3600)/60);
let s=seconds%60;

document.getElementById("countdown").innerHTML=
String(h).padStart(2,"0")+":"+
String(m).padStart(2,"0")+":"+
String(s).padStart(2,"0");

if(seconds>0) seconds--;
}}

setInterval(update,1000);
update();
</script>

</body>
</html>
"""

    return f"""
<html><body style="background:#050816;color:white;text-align:center;padding:60px;">
<h1>🔥 Premium Signal</h1>
<p>{signal["country"]}</p>
<p>{signal["sector"]}</p>
<p>{signal["margin"]}</p>
<p>{signal["confidence"]}</p>
<p>{signal["urgency"]}</p>
</body></html>
"""

@app.route("/hdi/pay")
def pay():
    key=request.args.get("key")
    user=get_user_by_key(key)

    tx_ref="HDI-"+uuid.uuid4().hex[:12]

    conn=get_conn()
    cur=conn.cursor()
    cur.execute("INSERT INTO payments(api_key,tx_ref,amount,currency) VALUES(%s,%s,%s,%s)",
    (key,tx_ref,PAY_AMOUNT,PAY_CURRENCY))
    conn.commit()
    cur.close()
    conn.close()

    headers={"Authorization":f"Bearer {FLW_SECRET_KEY}"}

    payload={
        "tx_ref":tx_ref,
        "amount":PAY_AMOUNT,
        "currency":PAY_CURRENCY,
        "redirect_url":BASE_URL,
        "customer":{"email":user[2],"name":user[1]}
    }

    res=requests.post("https://api.flutterwave.com/v3/payments",json=payload,headers=headers)
    data=res.json()

    return redirect(data["data"]["link"])

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
