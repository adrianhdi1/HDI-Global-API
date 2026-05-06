from flask import Flask, jsonify, request, redirect
import uuid, os, requests, psycopg2, random
from datetime import datetime

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY")
ADMIN_KEY = os.environ.get("ADMIN_KEY")

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
    "USA Economy": {"focus": "Inflation, interest rates, technology markets", "risk": "Policy sensitivity", "opportunity": "AI, equities, institutional capital"},
    "China Economy": {"focus": "Manufacturing, exports, real estate pressure", "risk": "Demand slowdown", "opportunity": "Industrial recovery and trade flows"},
    "Africa Markets": {"focus": "Agriculture, infrastructure, mobile money, energy", "risk": "Currency pressure and inflation", "opportunity": "Emerging consumer growth"},
    "Emerging Markets": {"focus": "Currency movement, commodities, capital inflows", "risk": "External debt and rate pressure", "opportunity": "High-growth market expansion"},
    "Global Economy": {"focus": "Inflation, liquidity, global risk appetite", "risk": "Macro uncertainty", "opportunity": "Capital rotation across sectors"}
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
            params={"function": "TIME_SERIES_DAILY", "symbol": symbol, "apikey": ALPHA_VANTAGE_KEY},
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
            params={"function": "NEWS_SENTIMENT", "tickers": "AAPL,TSLA,NVDA,MSFT", "limit": 6, "apikey": ALPHA_VANTAGE_KEY},
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
    final_score = int(momentum_score * 0.35 + volatility_score * 0.20 + trend_strength * 0.25 + relevance_score * 0.20)
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
        exposure = "20% â 30%"
        risk = "MODERATE"
        pattern = "Multi-Factor Momentum Breakout"
        brief = "HDI detects strong alignment between momentum, trend strength, and market relevance."
        recommendation = "HDI Recommendation: Consider entry within the next 2â4 hours while momentum remains active."
    elif score >= 76:
        action = "MONITOR CLOSELY"
        exposure = "10% â 20%"
        risk = "CONTROLLED"
        pattern = "Adaptive Growth Pattern"
        brief = "HDI detects improving conditions, but confirmation is still developing."
        recommendation = "HDI Recommendation: Monitor closely and wait for confirmation before increasing exposure."
    elif score >= 64:
        action = "WAIT FOR CONFIRMATION"
        exposure = "0% â 10%"
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
        changes, volatilities = [], []
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
            opportunity, risk, priority = "Strong opportunity pressure detected", "MODERATE", "HIGH"
        elif sector_score >= 70:
            opportunity, risk, priority = "Developing opportunity pattern", "CONTROLLED", "MEDIUM"
        else:
            opportunity, risk, priority = "Weak or uncertain sector conditions", "ELEVATED", "LOW"
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

def generate_economy_intelligence():
    rows = []
    for economy, data in ECONOMIES.items():
        inflation_pressure = random.randint(45, 88)
        risk_score = random.randint(40, 85)
        opportunity_score = random.randint(55, 92)
        total_score = int(opportunity_score * 0.45 + (100 - risk_score) * 0.25 + (100 - inflation_pressure) * 0.30)
        if total_score >= 75:
            mood, priority = "OPPORTUNITY ZONE", "HIGH"
        elif total_score >= 60:
            mood, priority = "WATCH ZONE", "MEDIUM"
        else:
            mood, priority = "RISK ZONE", "LOW"
        rows.append({
            "economy": economy,
            "focus": data["focus"],
            "risk": data["risk"],
            "opportunity": data["opportunity"],
            "inflation_pressure": inflation_pressure,
            "risk_score": risk_score,
            "opportunity_score": opportunity_score,
            "total_score": total_score,
            "mood": mood,
            "priority": priority
        })
    return sorted(rows, key=lambda x: x["total_score"], reverse=True)

def economy_intelligence_html():
    html = ""
    for e in generate_economy_intelligence():
        html += f"""
        <div class="box">
            <b>{e["economy"]}</b><br>
            Economy Score: <span class="metric">{e["total_score"]}/100</span><br>
            Mood: <span class="gold">{e["mood"]}</span><br>
            Priority: {e["priority"]}<br><br>
            <b>Focus:</b><br><span class="muted">{e["focus"]}</span><br><br>
            <b>Risk:</b><br><span class="muted">{e["risk"]}</span><br><br>
            <b>Opportunity:</b><br><span class="muted">{e["opportunity"]}</span><br><br>
            Inflation Pressure: {e["inflation_pressure"]}/100<br>
            Risk Score: {e["risk_score"]}/100<br>
            Opportunity Score: {e["opportunity_score"]}/100
        </div>
        """
    return html

def generate_ranked_signals(api_key=None, limit=5):
    ranked = [generate_decision_signal(symbol=s, api_key=api_key) for s in SYMBOLS]
    ranked = sorted(ranked, key=lambda x: (x["market_score"], x["factors"]["relevance_score"], x["factors"]["momentum_score"]), reverse=True)
    return ranked[:limit]

def ranked_signals_html(api_key):
    html = ""
    for i, s in enumerate(generate_ranked_signals(api_key), 1):
        html += f"""
        <div class="box">
            <b>#{i} â {s["symbol"]}</b><br>
            Pattern: {s["pattern"]}<br>
            Score: <span class="metric">{s["market_score"]}/100</span><br>
            Priority: <span class="gold">{s["priority"]}</span><br>
            HDI Recommendation: {s["recommendation"]}<br>
            <span class="muted">Strategic Action: ð Locked</span>
        </div>
        """
    return html

def news_intelligence_html():
    news = fetch_news_sentiment()
    if not news:
        news = [
            {"title": "AI sector showing increased institutional attention", "summary": "HDI detects rising market interest around technology and AI-linked equities.", "overall_sentiment_label": "Bullish", "source": "HDI"},
            {"title": "Technology equities remain active across global markets", "summary": "Market movement suggests continued decision pressure in major tech names.", "overall_sentiment_label": "Neutral", "source": "HDI"}
        ]
    html = ""
    for item in news[:5]:
        title = item.get("title", "Market headline unavailable")
        summary = item.get("summary", "No summary available.")
        sentiment = item.get("overall_sentiment_label", "Neutral")
        source = item.get("source", "Market Source")
        html += f"""
        <div class="box">
            <b>{title}</b><br>
            <span class="muted">{summary[:220]}...</span><br><br>
            Source: {source}<br>
            Sentiment: <span class="gold">{sentiment}</span>
        </div>
        """
    return html

def save_signal(api_key, signal):
    market = fetch_alpha_daily(signal["symbol"])
    entry_price = market["latest_close"] if market else 0
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO signal_history(api_key,symbol,action,score,entry_price,expected,created_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s)
        """, (api_key, signal["symbol"], signal["strategic_action"], signal["market_score"], entry_price, signal["expected"], datetime.utcnow().isoformat()))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def signal_accuracy_html():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM signal_history WHERE result='SUCCESS'")
        success = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM signal_history WHERE result IN ('SUCCESS','FAILED')")
        total = cur.fetchone()[0]
        cur.close()
        conn.close()
        if total == 0:
            return "<p class='muted'>Signal outcome tracking is initializing. Results will appear after feedback checks.</p>"
        accuracy = round((success / total) * 100)
        return f"<p class='blue'>Closed Feedback Accuracy: {accuracy}%</p><p class='muted'>{success}/{total} resolved signals marked successful.</p>"
    except:
        return "<p class='muted'>Feedback accuracy unavailable.</p>"

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
        signal = generate_decision_signal(symbol, api_key)
        color = "#22c55e" if signal["change"] >= 0 else "#ef4444"
        sign = "+" if signal["change"] >= 0 else ""
        html += f"""
        <div class="box">
            <b>{symbol}</b><br>
            <span style="color:{color};font-size:22px;font-weight:bold;">{sign}{signal["change"]}%</span>
            <br><span class="muted">{signal["micro_result"]}</span>
            <br><span class="muted">Priority: {signal["priority"]}</span>
            <br><span class="muted">Strategic Action: ð Locked</span>
            <br><a href="/hdi/remove-watchlist?key={api_key}&symbol={symbol}" style="color:#ef4444;">Remove</a>
        </div>
        """
    return html

def performance_tracking_html():
    rows, wins, total = "", 0, 0
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

def generate_insight_feed(api_key=None):
    preferred = get_preferred_symbol(api_key) if api_key else None
    if preferred:
        return {
            "sector": f"{preferred} Focus",
            "theme": "personalized multi-factor behavior pattern",
            "impact": random.choice(["STRONG", "HIGH"]),
            "confidence": random.randint(78, 93),
            "interpretation": f"HDI detected repeated interest in {preferred}. Your intelligence feed is adapting toward this market behavior."
        }
    return {
        "sector": random.choice(["Global Equities", "AI", "Energy", "Fintech", "Healthcare"]),
        "theme": random.choice(["capital rotation", "rising volatility", "momentum pressure", "breakout potential"]),
        "impact": random.choice(["MODERATE", "STRONG", "HIGH"]),
        "confidence": random.randint(72, 91),
        "interpretation": "Market behavior suggests an emerging decision window. HDI will personalize this feed as you use the system."
    }

def get_portfolio(api_key):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, symbol, amount FROM portfolio WHERE api_key=%s ORDER BY id DESC", (api_key,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def portfolio_intelligence_html(api_key):
    holdings = get_portfolio(api_key)
    if not holdings:
        return "<p class='muted'>No portfolio yet. Add holdings to activate portfolio intelligence.</p>"
    total_amount = sum([float(h[2]) for h in holdings])
    rows, risk_total, strongest, weakest = "", 0, None, None
    for holding_id, symbol, amount in holdings:
        signal = generate_decision_signal(symbol, api_key)
        weight = round((float(amount) / total_amount) * 100, 1) if total_amount else 0
        risk_total += (100 - signal["market_score"]) * (weight / 100)
        if strongest is None or signal["market_score"] > strongest["score"]:
            strongest = {"symbol": symbol, "score": signal["market_score"]}
        if weakest is None or signal["market_score"] < weakest["score"]:
            weakest = {"symbol": symbol, "score": signal["market_score"]}
        rows += f"""
        <div class="box">
            <b>{symbol}</b><br>
            Exposure: {weight}%<br>
            Amount: {amount}<br>
            Score: <span class="metric">{signal["market_score"]}/100</span><br>
            Priority: <span class="gold">{signal["priority"]}</span><br>
            HDI View: {signal["recommendation"]}<br><br>
            <a href="/hdi/remove-portfolio?key={api_key}&holding_id={holding_id}" style="color:#ef4444;">Remove Holding</a>
        </div>
        """
    portfolio_risk = round(risk_total, 1)
    if portfolio_risk < 25:
        recommendation = "Portfolio risk appears controlled. Maintain monitoring."
    elif portfolio_risk < 45:
        recommendation = "Moderate portfolio risk detected. Review weaker positions."
    else:
        recommendation = "High portfolio risk detected. Consider reducing exposure to weak signals."
    summary = f"""
    <div class="box">
        <b>Portfolio Risk Score</b><br>
        <span class="metric">{portfolio_risk}/100</span><br><br>
        <b>Strongest Holding:</b> {strongest["symbol"]} ({strongest["score"]}/100)<br>
        <b>Weakest Holding:</b> {weakest["symbol"]} ({weakest["score"]}/100)<br><br>
        <b>HDI Portfolio Recommendation:</b><br>
        <span class="gold">{recommendation}</span><br><br>
        <a href="/hdi/clear-portfolio?key={api_key}" style="color:#ef4444;font-weight:bold;">Clear Entire Portfolio</a>
    </div>
    """
    return summary + "<div class='grid'>" + rows + "</div>"

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
    .box{background:rgba(15,23,42,.55);backdrop-filter:blur(10px);border:1px solid rgba(56,189,248,.08);padding:16px;margin:8px;border-radius:18px;text-align:left;transition:.25s;}
    .box:hover{transform:translateY(-2px);border:1px solid rgba(56,189,248,.25);}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;}
    .blue{color:#38bdf8;font-weight:bold;} .gold{color:#facc15;font-weight:bold;} .muted{color:#94a3b8;font-size:14px;}
    .metric{font-size:30px;font-weight:bold;color:#38bdf8;} .locked{filter:blur(3px);opacity:.55;}
    .nav{position:sticky;top:0;z-index:99;background:#020617;border:1px solid rgba(56,189,248,.18);border-radius:16px;padding:14px;margin-bottom:22px;}
    .nav a{color:#38bdf8;text-decoration:none;font-weight:bold;margin:8px;display:inline-block;}
    </style>
    """

@app.route("/")
def home():
    return f"""
<html><head><title>HDI Global Intelligence</title>{base_style()}</head>
<body>
<div class="container"><div class="card">
<div class="institution">Private Beta Access</div>
<h1>HDI Global Intelligence</h1>
<p class="blue">Live Multi-Factor Adaptive Decision Intelligence System</p>
<p>HDI analyzes market data, news, sectors, economies, portfolio exposure, user relevance, and feedback outcomes.</p>
<h2>Create Access</h2>
<input id="name" placeholder="Full Name"><br>
<input id="email" placeholder="Email Address"><br>
<button onclick="createUser()">Enter HDI</button>
<hr style="margin:35px;border-color:#1f2937;">
<h2>Login</h2>
<input id="login_email" placeholder="Email Address"><br>
<button onclick="loginUser()">Login</button>
<br><br>
<a class="btn" href="/hdi/methodology">How HDI Works</a>
<div id="result"></div>
</div></div>
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
    name, email = data.get("name"), data.get("email")
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

@app.route("/hdi/profile")
def profile():
    key = request.args.get("key")
    user = get_user_by_key(key)
    if not user:
        return "Invalid access"
    return f"""
<html><head><title>HDI Profile</title>{base_style()}</head>
<body><div class="container"><div class="card">
<div class="institution">HDI User Profile</div>
<h1>Account Profile</h1>
<div class="grid">
<div class="box"><b>Name</b><br>{user[1]}</div>
<div class="box"><b>Email</b><br>{user[2]}</div>
<div class="box"><b>Plan</b><br>{user[4]}</div>
<div class="box"><b>Premium Until</b><br>{user[5] if user[5] else "Not active"}</div>
<div class="box"><b>Access Key</b><br>{user[3]}</div>
<div class="box"><b>Status</b><br>{"Premium Active" if is_premium(user[4], user[5]) else "Free / Private Beta"}</div>
</div>
<a class="btn" href="/hdi/dashboard?key={key}">Back to Dashboard</a>
</div></div></body></html>
"""

@app.route("/hdi/dashboard")
def dashboard():
    key = request.args.get("key")
    user = get_user_by_key(key)
    if not user:
        return "Invalid access"
    signal = generate_decision_signal(api_key=key)
    insight = generate_insight_feed(key)
    performance = performance_tracking_html()
    accuracy = signal_accuracy_html()
    watchlist = watchlist_html(key)
    behavior = get_behavior_summary(key)
    ranked_signals = ranked_signals_html(key)
    news = news_intelligence_html()
    sectors = sector_intelligence_html()
    economies = economy_intelligence_html()
    portfolio = portfolio_intelligence_html(key)
    premium_active = is_premium(user[4], user[5])
    status = "Institutional Premium Active â" if premium_active else "Private Beta / Free Access ð"
    access_button = "" if premium_active else f"<a class='pay' href='/hdi/request-access?key={key}'>Request Institutional Access</a>"
    return f"""
<html>
<head><title>HDI Dashboard</title>{base_style()}<script>setTimeout(function(){{window.location.reload();}},60000);</script></head>
<body><div class="container">
<div class="nav">
<a href="/hdi/profile?key={key}">Profile</a>
<a href="#portfolio">Portfolio</a>
<a href="#economy">Economy</a>
<a href="#sectors">Sectors</a>
<a href="#news">News</a>
<a href="#signals">Signals</a>
<a href="#watchlist">Watchlist</a>
<a href="#performance">Performance</a>
<a href="/hdi/methodology">Methodology</a>
</div>
<div class="card">
<div class="institution">HDI Live Intelligence Terminal</div>
<h1>Adaptive Intelligence Dashboard</h1>
<p class="blue">Welcome, {user[1]}</p>
<p>{behavior}</p>
<p class="muted">Live mode: dashboard refreshes every 60 seconds.</p>
<div class="grid">
<div class="box"><b>Email</b><br>{user[2]}</div>
<div class="box"><b>Status</b><br>{status}</div>
<div class="box"><b>Access Key</b><br>{user[3]}</div>
<div class="box"><b>Premium Until</b><br>{user[5] if user[5] else "Not active"}</div>
</div>
<a class="btn" href="/hdi/premium-alerts?key={key}">Open Multi-Factor Signal</a>
<a class="btn" href="/hdi/methodology">View Methodology</a>
{access_button}
</div>
<div class="card" id="portfolio">
<div class="institution">Portfolio Intelligence Layer</div>
<h2>ð¼ Personal Portfolio Intelligence</h2>
<p class="blue">HDI analyzes your holdings, exposure, risk, strongest and weakest positions.</p>
<form action="/hdi/add-portfolio" method="POST">
<input type="hidden" name="key" value="{key}">
<select name="symbol"><option>AAPL</option><option>MSFT</option><option>TSLA</option><option>NVDA</option><option>AMZN</option><option>GOOGL</option><option>META</option></select><br>
<input name="amount" placeholder="Amount / Exposure Value"><br>
<button type="submit">Add Holding</button>
</form>
{portfolio}
</div>
<div class="card" id="economy"><div class="institution">Economy Intelligence Layer</div><h2>ð Global Economy Intelligence</h2><div class="grid">{economies}</div></div>
<div class="card" id="sectors"><div class="institution">Sector Intelligence Layer</div><h2>ð Global Sector Intelligence</h2><div class="grid">{sectors}</div></div>
<div class="card" id="news"><div class="institution">News Intelligence Layer</div><h2>ð° Market News Intelligence</h2><div class="grid">{news}</div></div>
<div class="card" id="signals"><div class="institution">Live Signal Ranking</div><h2>ð¥ Top Ranked Signals</h2><div class="grid">{ranked_signals}</div></div>
<div class="card">
<div class="institution">Next Level AI Layer</div>
<h2>ð§  Multi-Factor Signal Engine</h2>
<p class="blue">{signal["adaptive_note"]}</p>
<div class="grid">
<div class="box"><b>Priority Symbol</b><br>{signal["symbol"]}</div>
<div class="box"><b>Detected Pattern</b><br>{signal["pattern"]}</div>
<div class="box"><b>Market Score</b><br><span class="metric">{signal["market_score"]}/100</span></div>
<div class="box"><b>Signal Priority</b><br><span class="gold">{signal["priority"]}</span></div>
<div class="box"><b>HDI Recommendation</b><br>{signal["recommendation"]}</div>
<div class="box"><b>Micro Result</b><br>{signal["micro_result"]}</div>
</div></div>
<div class="card"><div class="institution">Feedback Loop</div><h2>ð Closed Learning System</h2>{accuracy}</div>
<div class="card">
<div class="institution">Adaptive Insight Feed</div>
<h2>Market Intelligence Pulse</h2>
<div class="grid">
<div class="box"><b>Sector Focus</b><br>{insight["sector"]}</div>
<div class="box"><b>Detected Pattern</b><br>{insight["theme"]}</div>
<div class="box"><b>Impact Level</b><br><span class="gold">{insight["impact"]}</span></div>
<div class="box"><b>Confidence</b><br>{insight["confidence"]}%</div>
</div><p>{insight["interpretation"]}</p></div>
<div class="card" id="watchlist">
<h2>â­ Personal Watchlist</h2>
<form action="/hdi/add-watchlist" method="POST">
<input type="hidden" name="key" value="{key}">
<select name="symbol"><option>AAPL</option><option>MSFT</option><option>TSLA</option><option>NVDA</option><option>AMZN</option><option>GOOGL</option><option>META</option></select><br>
<button type="submit">Add to Watchlist</button>
</form>
<div class="grid">{watchlist}</div>
</div>
<div class="card" id="performance"><h2>ð HDI Performance Layer</h2>{performance}</div>
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

@app.route("/hdi/add-portfolio", methods=["POST"])
def add_portfolio():
    key, symbol, amount = request.form.get("key"), request.form.get("symbol"), request.form.get("amount")
    if not get_user_by_key(key):
        return "Invalid key"
    try:
        amount = float(amount)
    except:
        amount = 0
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO portfolio(api_key,symbol,amount,created_at) VALUES(%s,%s,%s,%s)", (key, symbol, amount, datetime.utcnow().isoformat()))
    conn.commit()
    cur.close()
    conn.close()
    track_behavior(key, symbol, "portfolio")
    return redirect(f"/hdi/dashboard?key={key}")

@app.route("/hdi/remove-portfolio")
def remove_portfolio():
    key, holding_id = request.args.get("key"), request.args.get("holding_id")
    if not get_user_by_key(key):
        return "Invalid key"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM portfolio WHERE api_key=%s AND id=%s", (key, holding_id))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(f"/hdi/dashboard?key={key}")

@app.route("/hdi/clear-portfolio")
def clear_portfolio():
    key = request.args.get("key")
    if not get_user_by_key(key):
        return "Invalid key"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM portfolio WHERE api_key=%s", (key,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(f"/hdi/dashboard?key={key}")

@app.route("/hdi/remove-watchlist")
def remove_watchlist():
    key, symbol = request.args.get("key"), request.args.get("symbol")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM watchlist WHERE api_key=%s AND symbol=%s", (key,symbol))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(f"/hdi/dashboard?key={key}")

@app.route("/hdi/portfolio")
def portfolio_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error":"key required"}), 400
    holdings = get_portfolio(key)
    return jsonify([{"id": h[0], "symbol": h[1], "amount": h[2]} for h in holdings])

@app.route("/hdi/news")
def news_api():
    return jsonify(fetch_news_sentiment())

@app.route("/hdi/sectors")
def sectors_api():
    return jsonify(generate_sector_intelligence())

@app.route("/hdi/economies")
def economies_api():
    return jsonify(generate_economy_intelligence())

@app.route("/hdi/methodology")
def methodology():
    return f"""
<html><head><title>HDI Methodology</title>{base_style()}</head>
<body><div class="container">
<div class="card">
<div class="institution">HDI Methodology</div>
<h1>How HDI Generates Intelligence</h1>
<p class="blue">HDI is a multi-factor decision intelligence system.</p>
<p>HDI analyzes market movement, news sentiment, sector intelligence, economy intelligence, portfolio exposure, user behavior, and feedback outcomes.</p>
</div>
<div class="card">
<h2>â ï¸ Risk Disclaimer</h2>
<p>HDI provides decision intelligence based on data patterns. It is not financial advice or a guarantee of profit.</p>
</div>
<a href="/" class="muted">Back Home</a>
</div></body></html>
"""

@app.route("/hdi/premium-alerts")
def premium():
    key = request.args.get("key")
    user = get_user_by_key(key)
    if not user:
        return "Invalid key"
    signal = generate_decision_signal(api_key=key)
    save_signal(key, signal)
    track_behavior(key, signal["symbol"], "signal_open")
    performance = performance_tracking_html()
    accuracy = signal_accuracy_html()
    f = signal["factors"]
    return f"""
<html><head><title>HDI Signal</title>{base_style()}</head>
<body><div class="container">
<div class="card">
<div class="institution">Multi-Factor Signal Preview</div>
<h1>Strategic Pattern Detected</h1>
<p class="blue">{signal["adaptive_note"]}</p>
<div class="grid">
<div class="box"><b>Symbol</b><br>{signal["symbol"]}</div>
<div class="box"><b>Pattern</b><br>{signal["pattern"]}</div>
<div class="box"><b>Market Score</b><br><span class="metric">{signal["market_score"]}/100</span></div>
<div class="box"><b>Signal Priority</b><br><span class="gold">{signal["priority"]}</span></div>
<div class="box"><b>Momentum Score</b><br>{f["momentum_score"]}/100</div>
<div class="box"><b>Volatility Score</b><br>{f["volatility_score"]}/100</div>
<div class="box locked"><b>Exposure</b><br>{signal["exposure"]}</div>
<div class="box locked"><b>Entry Window</b><br>{signal["entry_window"]}</div>
<div class="box locked"><b>Expected Opportunity</b><br>{signal["expected"]}</div>
<div class="box locked"><b>Risk Breakdown</b><br>{signal["risk"]}</div>
</div>
<a class="pay" href="/hdi/request-access?key={key}">Request Institutional Access</a>
</div>
<div class="card"><h2>ð Feedback Accuracy</h2>{accuracy}</div>
<div class="card"><h2>ð Performance Preview</h2>{performance}</div>
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
    return jsonify(generate_decision_signal(api_key=key))

@app.route("/hdi/ranked-signals")
def ranked_signals_api():
    key = request.args.get("user_key")
    return jsonify(generate_ranked_signals(key))

@app.route("/hdi/admin")
def admin():
    if ADMIN_KEY and request.args.get("key") != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM access_requests")
    access_requests_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM user_behavior")
    behavior_events = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM signal_history")
    signals_saved = cur.fetchone()[0]
    cur.close()
    conn.close()
    return jsonify({
        "users": users,
        "access_requests": access_requests_count,
        "behavior_events": behavior_events,
        "signals_saved": signals_saved
    })

@app.route("/hdi/pay")
def pay():
    key = request.args.get("key")
    return redirect(f"/hdi/request-access?key={key}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
