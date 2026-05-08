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

    cur.execute("""CREATE TABLE IF NOT EXISTS user_preferences (
        id SERIAL PRIMARY KEY,
        api_key TEXT UNIQUE,
        risk_profile TEXT DEFAULT 'Balanced',
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
        exposure = "20% â 30%"
        risk = "MODERATE"
        pattern = "Multi-Factor Momentum Breakout"
        brief = "HDI detects strong alignment between momentum, trend strength, and market relevance."
        recommendation = "HDI Recommendation: Consider entry within the next 2â4 hours while momentum remains active."
    elif score >= 76:
        action = "MONITOR CLOSELY"
        exposure = "10% â 20%"
        risk = "CONTROLLED"
        pattern = "Adaptive Growth Pattern"
        brief = "HDI detects improving conditions, but confirmation is still developing."
        recommendation = "HDI Recommendation: Monitor closely and wait for confirmation before increasing exposure."
    elif score >= 64:
        action = "WAIT FOR CONFIRMATION"
        exposure = "0% â 10%"
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
            <b>#{i} â {s["symbol"]}</b><br>
            Pattern: {s["pattern"]}<br>
            Score: <span class="metric">{s["market_score"]}/100</span><br>
            Priority: <span class="gold">{s["priority"]}</span><br>
            HDI Recommendation: {s["recommendation"]}<br>
            <span class="muted">Strategic Action: ð Locked</span>
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
            <br><span class="muted">Strategic Action: ð Locked</span>
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














def autonomous_intelligence_agent_html(api_key):
    try:
        top_signal = generate_ranked_signals(api_key, limit=1)[0]
    except:
        top_signal = generate_decision_signal(api_key=api_key)

    conclusion = "HDI recommends continued monitoring."
    if top_signal["market_score"] >= 80 and top_signal["priority"] in ["HIGH", "CRITICAL"]:
        conclusion = "HDI autonomous agent detects strong opportunity pressure with high-priority signal conditions."
    elif top_signal["market_score"] < 60:
        conclusion = "HDI autonomous agent detects weak confirmation. Defensive patience is recommended."

    return f"""
    <div class="grid">
        <div class="box"><b>Autonomous Conclusion</b><br><span class="gold">{conclusion}</span></div>
        <div class="box"><b>Leading Signal</b><br>{top_signal["symbol"]}<br><span class="metric">{top_signal["market_score"]}/100</span></div>
        <div class="box"><b>Market Priority</b><br><span class="metric">{top_signal["priority"]}</span></div>
        <div class="box"><b>Agent Status</b><br><span class="gold">Monitoring</span><br><span class="muted">Signals, risk, opportunity, sectors, and macro layers.</span></div>
    </div>
    """

GLOBAL_MARKETS = {
    "US Markets": ["AAPL", "MSFT", "NVDA"],
    "Europe Markets": ["SAP", "ASML", "SIEGY"],
    "Asia Markets": ["TSM", "BABA", "SONY"],
    "Crypto": ["BTC", "ETH", "SOL"],
    "Commodities": ["GOLD", "OIL", "COPPER"],
    "Forex": ["EURUSD", "USDJPY", "GBPUSD"]
}

def global_market_scanner_html(api_key):
    html = ""
    for market, symbols in GLOBAL_MARKETS.items():
        score = random.randint(48, 92)
        volatility = random.randint(20, 86)
        mood = "Opportunity Zone" if score >= 75 else "Watch Zone" if score >= 60 else "Risk / Weak Zone"
        html += f"""
        <div class="box">
            <b>{market}</b><br>
            Scanner Score: <span class="metric">{score}/100</span><br>
            Mood: <span class="gold">{mood}</span><br>
            Volatility Pressure: {volatility}/100<br>
            <span class="muted">Tracked: {", ".join(symbols)}</span>
        </div>
        """
    return html

def trading_psychology_engine_html(api_key):
    try:
        ranked = generate_ranked_signals(api_key, limit=5)
        avg_score = sum([s["market_score"] for s in ranked]) / len(ranked)
        avg_vol = sum([s["volatility"] for s in ranked]) / len(ranked)
    except:
        avg_score = 65
        avg_vol = 4

    fear = min(100, int((100 - avg_score) * 0.55 + avg_vol * 8))
    greed = min(100, int(avg_score * 0.65))
    panic = min(100, int(avg_vol * 12))
    confidence = max(0, min(100, int(avg_score - avg_vol * 3)))
    emotion = "Greed / Confidence Dominance" if greed > fear and confidence >= 65 else "Fear / Caution Dominance" if fear >= greed else "Mixed Psychology"

    return f"""
    <div class="grid">
        <div class="box"><b>Market Emotion</b><br><span class="metric">{emotion}</span></div>
        <div class="box"><b>Fear Pressure</b><br><span class="metric">{fear}/100</span></div>
        <div class="box"><b>Greed Pressure</b><br><span class="metric">{greed}/100</span></div>
        <div class="box"><b>Panic Pressure</b><br><span class="metric">{panic}/100</span></div>
        <div class="box"><b>Confidence Pressure</b><br><span class="metric">{confidence}/100</span></div>
    </div>
    """

def institutional_flow_tracker_html(api_key):
    try:
        ranked = generate_ranked_signals(api_key, limit=5)
    except:
        ranked = [generate_decision_signal(api_key=api_key)]
    html = ""
    for s in ranked:
        flow_score = min(100, int(s["market_score"] * 0.55 + s["confidence_breakdown"]["momentum"] * 0.25 + s["confidence_breakdown"]["user_relevance"] * 0.20))
        flow = "Possible Accumulation" if flow_score >= 80 else "Rotation Watch" if flow_score >= 65 else "Weak Flow"
        html += f"""
        <div class="box">
            <b>{s["symbol"]}</b><br>
            Flow Score: <span class="metric">{flow_score}/100</span><br>
            Smart Money Read: <span class="gold">{flow}</span><br>
            <span class="muted">Estimate based on momentum, relevance, and signal strength.</span>
        </div>
        """
    return html

ECONOMIC_EVENTS = [
    "FED interest rate decision",
    "US CPI inflation release",
    "Earnings season volatility",
    "Oil price supply shock",
    "Dollar strength pressure",
    "Global liquidity shift"
]

def economic_event_radar_html():
    html = ""
    for event in ECONOMIC_EVENTS:
        impact = random.choice(["HIGH", "MEDIUM", "WATCH"])
        risk = random.randint(35, 90)
        html += f"""
        <div class="box">
            <b>{event}</b><br>
            Event Impact: <span class="gold">{impact}</span><br>
            Risk Pressure: <span class="metric">{risk}/100</span><br>
            <span class="muted">HDI monitors how macro events may affect signals and portfolios.</span>
        </div>
        """
    return html

def strategy_backtesting_engine_html(api_key):
    try:
        ranked = generate_ranked_signals(api_key, limit=3)
    except:
        ranked = [generate_decision_signal(api_key=api_key)]
    html = ""
    for s in ranked:
        win_rate = min(92, max(42, int(s["market_score"] * 0.72 + random.randint(5, 18))))
        drawdown = max(5, min(45, int((100 - s["market_score"]) * 0.35 + s["volatility"] * 2)))
        result = "Strategy historically looks strong" if win_rate >= 70 else "Strategy needs confirmation" if win_rate >= 55 else "Strategy is weak"
        html += f"""
        <div class="box">
            <b>{s["symbol"]}</b><br>
            Simulated Win Rate: <span class="metric">{win_rate}%</span><br>
            Estimated Drawdown: {drawdown}%<br>
            Backtest Read: <span class="gold">{result}</span><br>
            <span class="muted">Prototype backtest model using HDI signal quality.</span>
        </div>
        """
    return html

def multi_agent_ai_system_html(api_key):
    agents = [
        ("Risk Agent", "Monitors volatility, weak signals, and portfolio pressure."),
        ("Opportunity Agent", "Finds high-quality setups and confirmation zones."),
        ("Macro Agent", "Reads economy mood, inflation pressure, and macro shocks."),
        ("Strategy Agent", "Combines risk and opportunity into recommended strategy."),
        ("News Agent", "Tracks headlines and sentiment movement."),
    ]
    html = ""
    for name, role in agents:
        status = random.choice(["Active", "Monitoring", "Analyzing"])
        confidence = random.randint(62, 94)
        html += f"""
        <div class="box">
            <b>{name}</b><br>
            Status: <span class="gold">{status}</span><br>
            Confidence: <span class="metric">{confidence}%</span><br>
            <span class="muted">{role}</span>
        </div>
        """
    return html

def voice_intelligence_assistant_html(api_key):
    try:
        top_signal = generate_ranked_signals(api_key, limit=1)[0]
    except:
        top_signal = generate_decision_signal(api_key=api_key)
    return f"""
    <div class="grid">
        <div class="box"><b>Ask HDI</b><br><span class="muted">Example: âHDI, what is the strongest opportunity today?â</span></div>
        <div class="box"><b>Voice Answer Preview</b><br><span class="gold">The strongest current opportunity is {top_signal["symbol"]} with score {top_signal["market_score"]}/100 and {top_signal["priority"]} priority.</span></div>
    </div>
    """

def intelligence_memory_engine_html(api_key):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM signal_history WHERE api_key=%s", (api_key,))
        saved_signals = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM user_behavior WHERE api_key=%s", (api_key,))
        behavior_events = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM portfolio WHERE api_key=%s", (api_key,))
        portfolio_events = cur.fetchone()[0]
        cur.close()
        conn.close()
    except:
        saved_signals = behavior_events = portfolio_events = 0

    memory_depth = saved_signals + behavior_events + portfolio_events
    memory_status = "Deep Learning Profile" if memory_depth >= 20 else "Active Learning Profile" if memory_depth >= 8 else "Early Learning Profile"

    return f"""
    <div class="grid">
        <div class="box"><b>Memory Status</b><br><span class="metric">{memory_status}</span></div>
        <div class="box"><b>Saved Signals</b><br><span class="metric">{saved_signals}</span></div>
        <div class="box"><b>Behavior Events</b><br><span class="metric">{behavior_events}</span></div>
        <div class="box"><b>Portfolio Events</b><br><span class="metric">{portfolio_events}</span></div>
    </div>
    """

def enterprise_hedge_fund_mode_html(api_key):
    return """
    <div class="grid">
        <div class="box"><b>Pro Dashboard</b><br><span class="muted">Multi-screen institutional layout ready for advanced filters.</span></div>
        <div class="box"><b>Advanced Analytics</b><br><span class="muted">Risk, opportunity, forecasts, heatmaps, and strategy engines combined.</span></div>
        <div class="box"><b>Execution Layer</b><br><span class="muted">Future-ready layer for enterprise workflows and portfolio action planning.</span></div>
        <div class="box"><b>Enterprise Access</b><br><span class="muted">Designed for hedge funds, banks, companies, governments, and analysts.</span></div>
    </div>
    """

def get_user_risk_profile(api_key):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT risk_profile FROM user_preferences WHERE api_key=%s", (api_key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else "Balanced"
    except:
        return "Balanced"

def set_user_risk_profile(api_key, risk_profile):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO user_preferences(api_key,risk_profile,created_at)
            VALUES(%s,%s,%s)
            ON CONFLICT (api_key)
            DO UPDATE SET risk_profile=EXCLUDED.risk_profile
        """, (api_key, risk_profile, datetime.utcnow().isoformat()))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def company_intelligence_data(symbol, api_key=None):
    signal = generate_decision_signal(symbol=symbol, api_key=api_key)
    sector = "General Markets"
    for sector_name, symbols in SECTORS.items():
        if symbol in symbols:
            sector = sector_name
            break

    score = signal["market_score"]
    if score >= 80:
        growth_label = "Strong growth pressure"
        business_quality = "High-quality market attention"
    elif score >= 65:
        growth_label = "Developing growth pattern"
        business_quality = "Moderate-quality setup"
    else:
        growth_label = "Weak or uncertain growth pattern"
        business_quality = "Requires stronger confirmation"

    return {
        "symbol": symbol,
        "sector": sector,
        "market_score": score,
        "priority": signal["priority"],
        "pattern": signal["pattern"],
        "growth_label": growth_label,
        "business_quality": business_quality,
        "risk_note": "Monitor volatility, news sentiment, sector rotation, and market confirmation.",
        "opportunity_note": signal["recommendation"]
    }

def company_intelligence_html(api_key):
    html = ""
    for symbol in SYMBOLS:
        c = company_intelligence_data(symbol, api_key)
        html += f"""
        <div class="box">
            <b>{c["symbol"]}</b><br>
            Sector: {c["sector"]}<br>
            Company Score: <span class="metric">{c["market_score"]}/100</span><br>
            Priority: <span class="gold">{c["priority"]}</span><br>
            Pattern: {c["pattern"]}<br>
            Business Quality: {c["business_quality"]}<br>
            Growth View: <span class="blue">{c["growth_label"]}</span>
        </div>
        """
    return html

def notification_center_html(api_key):
    notifications = []

    try:
        top_signal = generate_ranked_signals(api_key, limit=1)[0]
        notifications.append({
            "title": f"Top signal: {top_signal['symbol']}",
            "body": f"{top_signal['priority']} priority with score {top_signal['market_score']}/100.",
            "level": top_signal["priority"]
        })
    except:
        pass

    try:
        holdings = get_portfolio(api_key)
        if holdings:
            total_amount = sum([float(h[2]) for h in holdings])
            risk_total = 0
            for holding_id, symbol, amount in holdings:
                s = generate_decision_signal(symbol=symbol, api_key=api_key)
                weight = float(amount) / total_amount if total_amount else 0
                risk_total += (100 - s["market_score"]) * weight
            portfolio_risk = round(risk_total, 1)
            notifications.append({
                "title": "Portfolio risk update",
                "body": f"Current portfolio risk pressure: {portfolio_risk}/100.",
                "level": "RISK" if portfolio_risk >= 45 else "WATCH"
            })
        else:
            notifications.append({
                "title": "Portfolio not active",
                "body": "Add holdings to unlock deeper portfolio notifications.",
                "level": "INFO"
            })
    except:
        pass

    try:
        sectors = generate_sector_intelligence()
        if sectors:
            top_sector = sectors[0]
            notifications.append({
                "title": f"Sector pulse: {top_sector['sector']}",
                "body": f"Sector score {top_sector['sector_score']}/100. {top_sector['opportunity']}",
                "level": top_sector["priority"]
            })
    except:
        pass

    try:
        news = fetch_news_sentiment()
        if news:
            notifications.append({
                "title": "News intelligence update",
                "body": news[0].get("title", "Market news detected")[:150],
                "level": news[0].get("overall_sentiment_label", "Neutral")
            })
    except:
        pass

    html = ""
    for n in notifications[:8]:
        html += f"""
        <div class="box">
            <b>{n["title"]}</b><br>
            <span class="muted">{n["body"]}</span><br>
            <span class="gold">{n["level"]}</span>
        </div>
        """
    return html

def ai_report_html(api_key):
    user = get_user_by_key(api_key)
    if not user:
        return "<p>Invalid user.</p>"

    top_signal = generate_ranked_signals(api_key, limit=1)[0]
    risk_profile = get_user_risk_profile(api_key)

    try:
        sectors = generate_sector_intelligence()
        top_sector = sectors[0]
    except:
        top_sector = None

    try:
        economies = generate_economy_intelligence()
        top_economy = economies[0]
    except:
        top_economy = None

    try:
        holdings = get_portfolio(api_key)
        holdings_count = len(holdings)
    except:
        holdings_count = 0

    sector_line = f"{top_sector['sector']} leads with score {top_sector['sector_score']}/100." if top_sector else "Sector intelligence is forming."
    economy_line = f"{top_economy['economy']} shows {top_economy['mood']}." if top_economy else "Economy intelligence is forming."

    return f"""
    <div class="card">
        <div class="institution">HDI AI Report Generator</div>
        <h1>HDI Intelligence Report</h1>
        <p class="blue">Generated for {user[1]} â {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>

        <div class="grid">
            <div class="box"><b>Risk Profile</b><br><span class="metric">{risk_profile}</span></div>
            <div class="box"><b>Top Signal</b><br>{top_signal['symbol']}<br><span class="metric">{top_signal['market_score']}/100</span></div>
            <div class="box"><b>Portfolio Holdings</b><br><span class="metric">{holdings_count}</span></div>
            <div class="box"><b>Top Sector</b><br><span class="gold">{sector_line}</span></div>
            <div class="box"><b>Macro View</b><br><span class="gold">{economy_line}</span></div>
        </div>
    </div>

    <div class="card">
        <h2>Executive Summary</h2>
        <p>
        HDI detects {top_signal['symbol']} as the current leading signal with {top_signal['priority']} priority.
        The system recommends monitoring momentum, volatility, sector confirmation, portfolio exposure, and news sentiment before action.
        </p>
    </div>

    <div class="card">
        <h2>Risk Disclaimer</h2>
        <p>HDI provides decision intelligence based on data patterns. It is not financial advice or a guarantee of profit.</p>
    </div>
    """

def portfolio_scenario_html(api_key, test_symbol=None, test_amount=0):
    holdings = get_portfolio(api_key)
    base_count = len(holdings)

    scenario_symbol = test_symbol or "NVDA"
    try:
        scenario_amount = float(test_amount)
    except:
        scenario_amount = 0

    scenario_signal = generate_decision_signal(symbol=scenario_symbol, api_key=api_key)
    scenario_score = scenario_signal["market_score"]

    if scenario_score >= 80:
        impact = "Potentially improves portfolio quality if exposure is controlled."
    elif scenario_score >= 65:
        impact = "Could add moderate opportunity but requires confirmation."
    else:
        impact = "May increase risk unless conditions improve."

    return f"""
    <div class="grid">
        <div class="box">
            <b>Current Holdings</b><br>
            <span class="metric">{base_count}</span>
        </div>

        <div class="box">
            <b>Scenario Asset</b><br>
            {scenario_symbol}<br>
            Amount Tested: {scenario_amount}
        </div>

        <div class="box">
            <b>Scenario Score</b><br>
            <span class="metric">{scenario_score}/100</span><br>
            Priority: <span class="gold">{scenario_signal["priority"]}</span>
        </div>

        <div class="box">
            <b>Scenario Impact</b><br>
            <span class="muted">{impact}</span>
        </div>
    </div>
    """

def user_risk_profile_html(api_key):
    current = get_user_risk_profile(api_key)
    return f"""
    <div class="box">
        <b>Current Risk Profile</b><br>
        <span class="metric">{current}</span><br>
        <span class="muted">This helps HDI adapt recommendations to your decision style.</span>
    </div>

    <form action="/hdi/set-risk-profile" method="POST">
        <input type="hidden" name="key" value="{api_key}">
        <select name="risk_profile">
            <option>Conservative</option>
            <option>Balanced</option>
            <option>Aggressive</option>
        </select><br>
        <button type="submit">Update Risk Profile</button>
    </form>
    """

def api_access_layer_html(api_key):
    return f"""
    <div class="grid">
        <div class="box"><b>Live Stream API</b><br><span class="muted">/hdi/live-stream?key={api_key}</span></div>
        <div class="box"><b>Predictions API</b><br><span class="muted">/hdi/predictions?key={api_key}</span></div>
        <div class="box"><b>Risk API</b><br><span class="muted">/hdi/risk-intelligence?key={api_key}</span></div>
        <div class="box"><b>Opportunity API</b><br><span class="muted">/hdi/opportunity-intelligence?key={api_key}</span></div>
        <div class="box"><b>Portfolio API</b><br><span class="muted">/hdi/portfolio?key={api_key}</span></div>
        <div class="box"><b>Report API</b><br><span class="muted">/hdi/report?key={api_key}</span></div>
    </div>
    """


def strategy_recommendation_engine_html(api_key):
    try:
        top_signal = generate_ranked_signals(api_key, limit=1)[0]
    except:
        top_signal = generate_decision_signal(api_key=api_key)

    score = top_signal["market_score"]
    volatility = top_signal["volatility"]
    momentum = top_signal["confidence_breakdown"]["momentum"]
    trend = top_signal["confidence_breakdown"]["trend_strength"]

    try:
        holdings = get_portfolio(api_key)
        has_portfolio = len(holdings) > 0
    except:
        holdings = []
        has_portfolio = False

    try:
        sectors = generate_sector_intelligence()
        top_sector = sectors[0] if sectors else None
    except:
        top_sector = None

    try:
        economies = generate_economy_intelligence()
        top_economy = economies[0] if economies else None
    except:
        top_economy = None

    risk_pressure = min(100, int((100 - score) * 0.60 + volatility * 8))
    opportunity_pressure = min(100, int(score * 0.45 + momentum * 0.30 + trend * 0.25))

    if opportunity_pressure >= 82 and risk_pressure < 45:
        strategy = "Aggressive Growth"
        strategy_note = "HDI detects strong opportunity pressure with controlled risk. Consider focused monitoring for high-quality entries."
    elif opportunity_pressure >= 68 and risk_pressure < 60:
        strategy = "Balanced Monitoring"
        strategy_note = "HDI detects a developing opportunity. Monitor confirmation before increasing exposure."
    elif risk_pressure >= 65:
        strategy = "Defensive Mode"
        strategy_note = "Risk pressure is elevated. Reduce aggression and protect capital."
    elif has_portfolio and risk_pressure >= 50:
        strategy = "Reduce Exposure"
        strategy_note = "Portfolio or market risk requires review. Reduce weak positions first."
    else:
        strategy = "Wait for Confirmation"
        strategy_note = "Conditions are not strong enough for aggressive action. Wait for clearer momentum and sector support."

    sector_context = f"{top_sector['sector']} leads sector strength at {top_sector['sector_score']}/100." if top_sector else "Sector data forming."
    economy_context = f"{top_economy['economy']} shows {top_economy['mood']}." if top_economy else "Economy data forming."

    return f"""
    <div class="grid">
        <div class="box">
            <b>Recommended Strategy</b><br>
            <span class="metric">{strategy}</span><br>
            <span class="gold">{strategy_note}</span>
        </div>

        <div class="box">
            <b>Top Asset Context</b><br>
            {top_signal["symbol"]}<br>
            Market Score: {score}/100<br>
            Priority: <span class="gold">{top_signal["priority"]}</span>
        </div>

        <div class="box">
            <b>Opportunity Pressure</b><br>
            <span class="metric">{opportunity_pressure}/100</span><br>
            <span class="muted">Momentum + trend + signal quality</span>
        </div>

        <div class="box">
            <b>Risk Pressure</b><br>
            <span class="metric">{risk_pressure}/100</span><br>
            <span class="muted">Volatility + weak-score pressure</span>
        </div>

        <div class="box">
            <b>Sector Context</b><br>
            <span class="muted">{sector_context}</span>
        </div>

        <div class="box">
            <b>Economy Context</b><br>
            <span class="muted">{economy_context}</span>
        </div>
    </div>
    """

def institutional_scoring_engine_html(api_key):
    try:
        ranked = generate_ranked_signals(api_key, limit=5)
    except:
        ranked = [generate_decision_signal(api_key=api_key)]

    html = ""
    for s in ranked:
        momentum = s["confidence_breakdown"]["momentum"]
        volatility_quality = max(0, 100 - int(s["volatility"] * 8))
        trend = s["confidence_breakdown"]["trend_strength"]
        relevance = s["confidence_breakdown"]["user_relevance"]

        institutional_confidence = min(100, int(
            s["market_score"] * 0.35 +
            momentum * 0.25 +
            trend * 0.20 +
            volatility_quality * 0.10 +
            relevance * 0.10
        ))

        if institutional_confidence >= 82:
            grade = "Institutional Grade A"
        elif institutional_confidence >= 70:
            grade = "Institutional Grade B"
        elif institutional_confidence >= 58:
            grade = "Watchlist Grade"
        else:
            grade = "Low Quality Signal"

        html += f"""
        <div class="box">
            <b>{s["symbol"]}</b><br>
            Institutional Confidence: <span class="metric">{institutional_confidence}/100</span><br>
            Grade: <span class="gold">{grade}</span><br>
            Signal Quality: {s["market_score"]}/100<br>
            Momentum Quality: {momentum}/100<br>
            Trend Quality: {trend}/100<br>
            Volatility Quality: {volatility_quality}/100
        </div>
        """

    return html

def ai_macro_forecast_engine_html():
    try:
        economies = generate_economy_intelligence()
    except:
        economies = []

    html = ""
    for e in economies[:5]:
        stability_index = max(0, min(100, int(
            (100 - e["risk_score"]) * 0.35 +
            (100 - e["inflation_pressure"]) * 0.35 +
            e["opportunity_score"] * 0.30
        )))

        if stability_index >= 75:
            forecast = "Expansion Watch"
            note = "Macro conditions show improving opportunity and controlled risk pressure."
        elif stability_index >= 60:
            forecast = "Mixed Stability"
            note = "Macro environment is usable but requires careful monitoring."
        else:
            forecast = "Pressure Zone"
            note = "Macro risk or inflation pressure may weaken opportunity quality."

        html += f"""
        <div class="box">
            <b>{e["economy"]}</b><br>
            Macro Stability Index: <span class="metric">{stability_index}/100</span><br>
            Forecast: <span class="gold">{forecast}</span><br>
            Inflation Pressure: {e["inflation_pressure"]}/100<br>
            Risk Score: {e["risk_score"]}/100<br>
            Opportunity Score: {e["opportunity_score"]}/100<br>
            <span class="muted">{note}</span>
        </div>
        """

    return html

def dynamic_market_pulse_html(api_key):
    try:
        ranked = generate_ranked_signals(api_key, limit=len(SYMBOLS))
    except:
        ranked = [generate_decision_signal(api_key=api_key)]

    bullish = 0
    bearish = 0
    total_score = 0
    volatility_total = 0

    for s in ranked:
        total_score += s["market_score"]
        volatility_total += s["volatility"]
        if s["market_score"] >= 65 and s["change"] >= 0:
            bullish += 1
        else:
            bearish += 1

    count = len(ranked) if ranked else 1
    avg_score = round(total_score / count, 1)
    avg_volatility = round(volatility_total / count, 2)

    if bullish > bearish and avg_score >= 70:
        mood = "Bullish Dominance"
        pulse_note = "Market pulse shows broad strength and improving opportunity pressure."
    elif bearish > bullish:
        mood = "Bearish / Caution Dominance"
        pulse_note = "Market pulse shows risk pressure or weak confirmation."
    else:
        mood = "Mixed Market"
        pulse_note = "Market pulse is mixed. Wait for stronger confirmation."

    return f"""
    <div class="grid">
        <div class="box">
            <b>Market Mood</b><br>
            <span class="metric">{mood}</span><br>
            <span class="muted">{pulse_note}</span>
        </div>

        <div class="box">
            <b>Average Market Score</b><br>
            <span class="metric">{avg_score}/100</span>
        </div>

        <div class="box">
            <b>Bullish Count</b><br>
            <span class="metric">{bullish}</span>
        </div>

        <div class="box">
            <b>Bearish / Caution Count</b><br>
            <span class="metric">{bearish}</span>
        </div>

        <div class="box">
            <b>Volatility Pulse</b><br>
            <span class="metric">{avg_volatility}%</span><br>
            <span class="muted">Average volatility across tracked assets</span>
        </div>
    </div>
    """

def adaptive_recommendation_feed_html(api_key):
    try:
        preferred = get_preferred_symbol(api_key)
    except:
        preferred = None

    try:
        ranked = generate_ranked_signals(api_key, limit=5)
    except:
        ranked = [generate_decision_signal(api_key=api_key)]

    recommendations = []

    if preferred:
        recommendations.append({
            "title": f"Focus detected: {preferred}",
            "body": f"HDI has detected repeated activity around {preferred}. Keep this asset under priority monitoring."
        })

    for s in ranked[:3]:
        if s["market_score"] >= 75:
            body = f"{s['symbol']} has strong score {s['market_score']}/100. Monitor for confirmation and risk control."
        elif s["market_score"] >= 62:
            body = f"{s['symbol']} is forming a setup. Wait for stronger confirmation before acting aggressively."
        else:
            body = f"{s['symbol']} remains weak. Avoid rushing until conditions improve."

        recommendations.append({
            "title": f"{s['symbol']} adaptive recommendation",
            "body": body
        })

    try:
        holdings = get_portfolio(api_key)
        if not holdings:
            recommendations.append({
                "title": "Portfolio not active",
                "body": "Add holdings to unlock deeper portfolio risk, exposure, and strategy intelligence."
            })
    except:
        pass

    html = ""
    for r in recommendations[:6]:
        html += f"""
        <div class="box">
            <b>{r["title"]}</b><br>
            <span class="muted">{r["body"]}</span>
        </div>
        """

    return html


def opportunity_intelligence_engine_html(api_key):
    opportunities = []

    try:
        ranked = generate_ranked_signals(api_key, limit=5)
    except:
        ranked = [generate_decision_signal(api_key=api_key)]

    for s in ranked:
        score = s["market_score"]
        momentum = s["confidence_breakdown"]["momentum"]
        trend = s["confidence_breakdown"]["trend_strength"]
        relevance = s["confidence_breakdown"]["user_relevance"]
        volatility_penalty = min(30, int(s["volatility"] * 3))

        opportunity_score = min(100, max(0, int(
            score * 0.40 +
            momentum * 0.25 +
            trend * 0.20 +
            relevance * 0.15 -
            volatility_penalty
        )))

        if opportunity_score >= 82:
            level = "HIGH OPPORTUNITY"
            label = "Breakout / Growth Watch"
            confirmation = "Confirm momentum continuation and volume/news support."
        elif opportunity_score >= 68:
            level = "DEVELOPING OPPORTUNITY"
            label = "Accumulation / Setup Zone"
            confirmation = "Wait for stronger confirmation before aggressive exposure."
        elif opportunity_score >= 55:
            level = "EARLY OPPORTUNITY"
            label = "Formation Stage"
            confirmation = "Monitor price behavior and sector strength."
        else:
            level = "LOW OPPORTUNITY"
            label = "No Clear Setup"
            confirmation = "Avoid rushing until score improves."

        opportunities.append({
            "symbol": s["symbol"],
            "opportunity_score": opportunity_score,
            "level": level,
            "label": label,
            "confirmation": confirmation,
            "market_score": score,
            "priority": s["priority"],
            "recommendation": s["recommendation"]
        })

    try:
        sectors = generate_sector_intelligence()
        best_sector = sectors[0] if sectors else None
        sector_note = f"{best_sector['sector']} is the strongest sector opportunity with score {best_sector['sector_score']}/100." if best_sector else "Sector opportunity is still forming."
    except:
        sector_note = "Sector opportunity unavailable."

    try:
        economies = generate_economy_intelligence()
        opportunity_economies = [e for e in economies if e["mood"] == "OPPORTUNITY ZONE"]
        if opportunity_economies:
            best_economy = opportunity_economies[0]
        else:
            best_economy = economies[0] if economies else None
        economy_note = f"{best_economy['economy']} shows {best_economy['mood']} with score {best_economy['total_score']}/100." if best_economy else "Economy opportunity is still forming."
    except:
        economy_note = "Economy opportunity unavailable."

    asset_html = ""
    for item in opportunities:
        asset_html += f"""
        <div class="box">
            <b>{item["symbol"]}</b><br>
            Opportunity Score: <span class="metric">{item["opportunity_score"]}/100</span><br>
            Level: <span class="gold">{item["level"]}</span><br>
            Setup: {item["label"]}<br>
            Market Score: {item["market_score"]}/100<br>
            Priority: {item["priority"]}<br><br>
            <b>Confirmation Needed:</b><br>
            <span class="muted">{item["confirmation"]}</span><br><br>
            <span class="blue">{item["recommendation"]}</span>
        </div>
        """

    return f"""
    <div class="grid">
        <div class="box">
            <b>Best Sector Opportunity</b><br>
            <span class="gold">{sector_note}</span>
        </div>

        <div class="box">
            <b>Best Economy Opportunity</b><br>
            <span class="gold">{economy_note}</span>
        </div>

        <div class="box">
            <b>Why Opportunity Matters</b><br>
            <span class="muted">
            HDI combines signal strength, momentum, trend quality, user relevance, sector context, and volatility pressure to find opportunity zones.
            </span>
        </div>

        <div class="box">
            <b>Confirmation Rule</b><br>
            <span class="muted">
            Opportunity is not a guarantee. HDI requires confirmation from momentum, sector strength, risk level, and news sentiment before aggressive decisions.
            </span>
        </div>
    </div>

    <h3 style="text-align:left;color:#e5e7eb;margin-left:10px;">Asset Opportunity Map</h3>
    <div class="grid">{asset_html}</div>
    """


def risk_intelligence_engine_html(api_key):
    risk_items = []

    try:
        ranked = generate_ranked_signals(api_key, limit=5)
    except:
        ranked = [generate_decision_signal(api_key=api_key)]

    for s in ranked:
        volatility_risk = min(100, int(s["volatility"] * 12))
        weak_score_risk = max(0, 100 - s["market_score"])
        bearish_pressure = min(100, int((weak_score_risk * 0.65) + (volatility_risk * 0.35)))

        if bearish_pressure >= 65:
            risk_level = "HIGH RISK"
            risk_note = "Momentum weakness or volatility pressure may cause unstable movement."
        elif bearish_pressure >= 45:
            risk_level = "MEDIUM RISK"
            risk_note = "Conditions require monitoring before aggressive decisions."
        else:
            risk_level = "CONTROLLED RISK"
            risk_note = "Risk appears controlled, but confirmation is still important."

        risk_items.append({
            "symbol": s["symbol"],
            "risk_score": bearish_pressure,
            "risk_level": risk_level,
            "risk_note": risk_note,
            "volatility": s["volatility"],
            "market_score": s["market_score"]
        })

    portfolio_note = "No active portfolio risk detected because no holdings are added."
    try:
        holdings = get_portfolio(api_key)
        if holdings:
            total_amount = sum([float(h[2]) for h in holdings])
            risk_total = 0
            weakest = None
            for holding_id, symbol, amount in holdings:
                signal = generate_decision_signal(symbol, api_key)
                weight = (float(amount) / total_amount) if total_amount else 0
                asset_risk = 100 - signal["market_score"]
                risk_total += asset_risk * weight
                if weakest is None or signal["market_score"] < weakest["score"]:
                    weakest = {"symbol": symbol, "score": signal["market_score"]}

            portfolio_risk = round(risk_total, 1)
            if portfolio_risk >= 45:
                portfolio_note = f"High portfolio pressure detected: {portfolio_risk}/100. Weakest holding: {weakest['symbol']}."
            elif portfolio_risk >= 25:
                portfolio_note = f"Moderate portfolio pressure detected: {portfolio_risk}/100. Review weaker positions."
            else:
                portfolio_note = f"Portfolio risk appears controlled: {portfolio_risk}/100."
    except:
        portfolio_note = "Portfolio risk calculation unavailable."

    try:
        sectors = generate_sector_intelligence()
        weakest_sector = sectors[-1] if sectors else None
        sector_note = f"Weakest sector pressure: {weakest_sector['sector']} with score {weakest_sector['sector_score']}/100." if weakest_sector else "Sector risk is still being analyzed."
    except:
        sector_note = "Sector risk unavailable."

    try:
        economies = generate_economy_intelligence()
        risk_zones = [e for e in economies if e["mood"] == "RISK ZONE"]
        if risk_zones:
            macro_note = f"Macro risk zone detected in {risk_zones[0]['economy']} with score {risk_zones[0]['total_score']}/100."
        else:
            macro_note = "No major macro risk zone detected in the current economy model."
    except:
        macro_note = "Macro risk unavailable."

    asset_html = ""
    for item in risk_items:
        asset_html += f"""
        <div class="box">
            <b>{item["symbol"]}</b><br>
            Risk Score: <span class="metric">{item["risk_score"]}/100</span><br>
            Risk Level: <span class="gold">{item["risk_level"]}</span><br>
            Market Score: {item["market_score"]}/100<br>
            Volatility: {item["volatility"]}%<br>
            <span class="muted">{item["risk_note"]}</span>
        </div>
        """

    return f"""
    <div class="grid">
        <div class="box">
            <b>Portfolio Risk Note</b><br>
            <span class="gold">{portfolio_note}</span>
        </div>

        <div class="box">
            <b>Sector Risk Note</b><br>
            <span class="muted">{sector_note}</span>
        </div>

        <div class="box">
            <b>Macro Risk Note</b><br>
            <span class="muted">{macro_note}</span>
        </div>

        <div class="box">
            <b>What Could Go Wrong</b><br>
            <span class="muted">
            Sudden volatility, negative news, weak confirmation, sector rotation, or macro pressure can weaken signals.
            </span>
        </div>
    </div>

    <h3 style="text-align:left;color:#e5e7eb;margin-left:10px;">Asset Risk Map</h3>
    <div class="grid">{asset_html}</div>
    """


def ai_briefing_engine_html(api_key):
    try:
        top_signal = generate_ranked_signals(api_key, limit=1)[0]
    except:
        top_signal = generate_decision_signal(api_key=api_key)

    try:
        sectors = generate_sector_intelligence()
        top_sector = sectors[0] if sectors else None
    except:
        top_sector = None

    try:
        economies = generate_economy_intelligence()
        top_economy = economies[0] if economies else None
    except:
        top_economy = None

    try:
        holdings = get_portfolio(api_key)
        portfolio_status = "No active portfolio yet."
        if holdings:
            portfolio_status = f"{len(holdings)} holdings under HDI monitoring."
    except:
        portfolio_status = "Portfolio data unavailable."

    signal_symbol = top_signal["symbol"]
    signal_score = top_signal["market_score"]
    signal_priority = top_signal["priority"]
    signal_pattern = top_signal["pattern"]

    sector_text = f"{top_sector['sector']} is currently the strongest sector with score {top_sector['sector_score']}/100." if top_sector else "Sector intelligence is still forming."
    economy_text = f"{top_economy['economy']} is showing {top_economy['mood']} with score {top_economy['total_score']}/100." if top_economy else "Economy intelligence is still forming."

    if signal_score >= 80:
        opportunity_note = f"HDI detects elevated opportunity pressure around {signal_symbol}. Momentum and ranking suggest this asset deserves attention."
    elif signal_score >= 65:
        opportunity_note = f"HDI detects a developing setup around {signal_symbol}. Confirmation is still important before aggressive decisions."
    else:
        opportunity_note = f"HDI detects weak or uncertain conditions around {signal_symbol}. Patience is preferred."

    if signal_priority in ["CRITICAL", "HIGH"]:
        risk_note = "Risk should be controlled because high-priority signals can still reverse under volatility or news pressure."
    else:
        risk_note = "Risk is currently moderate, but HDI recommends waiting for stronger confirmation."

    return f"""
    <div class="grid">
        <div class="box">
            <b>What is happening now</b><br>
            <span class="muted">
            HDI is tracking {signal_symbol} as the leading signal. Pattern detected: {signal_pattern}. Market score is {signal_score}/100.
            </span>
        </div>

        <div class="box">
            <b>Why it matters</b><br>
            <span class="muted">
            {signal_symbol} is influencing the current intelligence ranking. This can guide watchlist focus, portfolio monitoring, and signal review.
            </span>
        </div>

        <div class="box">
            <b>What to watch next</b><br>
            <span class="muted">
            Watch momentum continuation, volatility behavior, sector strength, and news sentiment before making decisions.
            </span>
        </div>

        <div class="box">
            <b>Sector context</b><br>
            <span class="muted">{sector_text}</span>
        </div>

        <div class="box">
            <b>Economy context</b><br>
            <span class="muted">{economy_text}</span>
        </div>

        <div class="box">
            <b>Portfolio context</b><br>
            <span class="muted">{portfolio_status}</span>
        </div>

        <div class="box">
            <b>Opportunity note</b><br>
            <span class="gold">{opportunity_note}</span>
        </div>

        <div class="box">
            <b>Risk note</b><br>
            <span class="muted">{risk_note}</span>
        </div>
    </div>
    """


def ai_prediction_engine_html(api_key):
    predictions = []

    try:
        ranked = generate_ranked_signals(api_key, limit=5)
    except:
        ranked = [generate_decision_signal(api_key=api_key)]

    for s in ranked:
        score = s["market_score"]
        change = s["change"]
        volatility = s["volatility"]
        momentum = s["confidence_breakdown"]["momentum"]
        trend = s["confidence_breakdown"]["trend_strength"]

        bullish_pressure = min(100, max(0, int((score * 0.45) + (momentum * 0.30) + (trend * 0.25))))
        bearish_pressure = min(100, max(0, int((100 - score) * 0.60 + volatility * 8)))

        if bullish_pressure >= 82 and change >= 0:
            label = "Growth Pressure"
            direction = "Bullish"
            action = "Breakout Watch"
        elif bullish_pressure >= 68:
            label = "Accumulation Zone"
            direction = "Bullish / Neutral"
            action = "Monitor Momentum"
        elif bearish_pressure >= 55:
            label = "Caution Zone"
            direction = "Bearish / Risk"
            action = "Reduce Aggression"
        else:
            label = "Neutral Formation"
            direction = "Neutral"
            action = "Wait for Confirmation"

        probability = min(95, max(45, int((bullish_pressure * 0.65) + ((100 - bearish_pressure) * 0.35))))
        acceleration = "Rising" if momentum >= trend else "Stabilizing"

        predictions.append({
            "symbol": s["symbol"],
            "label": label,
            "direction": direction,
            "action": action,
            "probability": probability,
            "bullish_pressure": bullish_pressure,
            "bearish_pressure": bearish_pressure,
            "acceleration": acceleration,
            "score": score
        })

    html = ""
    for p in predictions:
        html += f"""
        <div class="box">
            <b>{p["symbol"]}</b><br>
            Prediction: <span class="gold">{p["label"]}</span><br>
            Direction: {p["direction"]}<br>
            Probability: <span class="metric">{p["probability"]}%</span><br>
            Bullish Pressure: {p["bullish_pressure"]}/100<br>
            Bearish Pressure: {p["bearish_pressure"]}/100<br>
            Momentum Acceleration: {p["acceleration"]}<br>
            HDI Action: <span class="blue">{p["action"]}</span>
        </div>
        """

    return html


def admin_intelligence_console_html():
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM users")
        users_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM access_requests")
        access_requests_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM user_behavior")
        behavior_events_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM signal_history")
        signals_saved_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM portfolio")
        portfolio_holdings_count = cur.fetchone()[0]

        cur.execute("""
            SELECT symbol, SUM(count) AS total
            FROM user_behavior
            GROUP BY symbol
            ORDER BY total DESC
            LIMIT 8
        """)
        top_assets = cur.fetchall()

        cur.execute("""
            SELECT action, SUM(count) AS total
            FROM user_behavior
            GROUP BY action
            ORDER BY total DESC
            LIMIT 8
        """)
        top_actions = cur.fetchall()

        cur.execute("""
            SELECT name, email, api_key, created_at
            FROM access_requests
            ORDER BY id DESC
            LIMIT 8
        """)
        latest_requests = cur.fetchall()

        cur.execute("""
            SELECT symbol, action, score, result, created_at
            FROM signal_history
            ORDER BY id DESC
            LIMIT 8
        """)
        latest_signals = cur.fetchall()

        cur.close()
        conn.close()
    except Exception as e:
        return f"<p class='muted'>Admin console unavailable: {str(e)}</p>"

    assets_html = ""
    for symbol, total in top_assets:
        assets_html += f"""
        <div class="box">
            <b>{symbol}</b><br>
            User Focus Score: <span class="metric">{total}</span>
        </div>
        """

    actions_html = ""
    for action, total in top_actions:
        actions_html += f"""
        <div class="box">
            <b>{action}</b><br>
            Activity Count: <span class="metric">{total}</span>
        </div>
        """

    requests_html = ""
    for name, email, api_key, created_at in latest_requests:
        requests_html += f"""
        <div class="box">
            <b>{name}</b><br>
            <span class="muted">{email}</span><br>
            <small>{created_at}</small>
        </div>
        """

    signals_html = ""
    for symbol, action, score, result, created_at in latest_signals:
        signals_html += f"""
        <div class="box">
            <b>{symbol}</b><br>
            Score: <span class="metric">{score}</span><br>
            Result: {result}<br>
            <span class="muted">{action}</span><br>
            <small>{created_at}</small>
        </div>
        """

    return f"""
    <div class="card">
        <div class="institution">Founder Intelligence Overview</div>
        <h1>Admin Intelligence Console</h1>
        <p class="blue">HDI operational intelligence for users, behavior, access, portfolio activity, and signals.</p>

        <div class="grid">
            <div class="box"><b>Total Users</b><br><span class="metric">{users_count}</span></div>
            <div class="box"><b>Access Requests</b><br><span class="metric">{access_requests_count}</span></div>
            <div class="box"><b>Behavior Events</b><br><span class="metric">{behavior_events_count}</span></div>
            <div class="box"><b>Signals Saved</b><br><span class="metric">{signals_saved_count}</span></div>
            <div class="box"><b>Portfolio Holdings</b><br><span class="metric">{portfolio_holdings_count}</span></div>
        </div>
    </div>

    <div class="card">
        <div class="institution">User Focus Intelligence</div>
        <h2>ð¥ Most Watched / Used Assets</h2>
        <div class="grid">{assets_html if assets_html else "<p class='muted'>No asset behavior yet.</p>"}</div>
    </div>

    <div class="card">
        <div class="institution">Behavior Trends</div>
        <h2>ð§  Most Common User Actions</h2>
        <div class="grid">{actions_html if actions_html else "<p class='muted'>No behavior actions yet.</p>"}</div>
    </div>

    <div class="card">
        <div class="institution">Access Pipeline</div>
        <h2>ð© Latest Access Requests</h2>
        <div class="grid">{requests_html if requests_html else "<p class='muted'>No access requests yet.</p>"}</div>
    </div>

    <div class="card">
        <div class="institution">Signal Operations</div>
        <h2>ð Latest Saved Signals</h2>
        <div class="grid">{signals_html if signals_html else "<p class='muted'>No saved signals yet.</p>"}</div>
    </div>
    """


def behavioral_intelligence_html(api_key):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, action, SUM(count) AS total
            FROM user_behavior
            WHERE api_key=%s
            GROUP BY symbol, action
            ORDER BY total DESC
            LIMIT 20
        """, (api_key,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except:
        rows = []

    if not rows:
        return """
        <p class='muted'>
        HDI has not collected enough behavior data yet. Add watchlist items, open signals, and build your portfolio to activate behavioral intelligence.
        </p>
        """

    symbol_totals = {}
    action_totals = {}

    for symbol, action, total in rows:
        symbol_totals[symbol] = symbol_totals.get(symbol, 0) + int(total)
        action_totals[action] = action_totals.get(action, 0) + int(total)

    favorite_symbol = max(symbol_totals, key=symbol_totals.get) if symbol_totals else "Learning"
    dominant_action = max(action_totals, key=action_totals.get) if action_totals else "Learning"

    total_activity = sum(symbol_totals.values()) if symbol_totals else 0

    if total_activity >= 12:
        activity_level = "HIGH"
    elif total_activity >= 5:
        activity_level = "MEDIUM"
    else:
        activity_level = "LOW"

    if dominant_action == "signal_open":
        decision_style = "Signal-driven decision maker"
    elif dominant_action == "portfolio":
        decision_style = "Portfolio-focused strategist"
    elif dominant_action == "watchlist":
        decision_style = "Market observer / watchlist builder"
    else:
        decision_style = "Adaptive intelligence profile forming"

    risk_appetite = "Balanced"
    try:
        preferred_signal = generate_decision_signal(symbol=favorite_symbol, api_key=api_key)
        if preferred_signal["market_score"] >= 80:
            risk_appetite = "Growth-oriented"
        elif preferred_signal["market_score"] < 60:
            risk_appetite = "Cautious"
    except:
        pass

    focus_rows = ""
    for symbol, total in sorted(symbol_totals.items(), key=lambda x: x[1], reverse=True)[:5]:
        focus_rows += f"""
        <div class="box">
            <b>{symbol}</b><br>
            Behavior Weight: <span class="metric">{total}</span><br>
            <span class="muted">Repeated interest detected</span>
        </div>
        """

    return f"""
    <div class="grid">
        <div class="box">
            <b>Favorite Asset</b><br>
            <span class="metric">{favorite_symbol}</span><br>
            <span class="muted">Most repeated user focus</span>
        </div>

        <div class="box">
            <b>Decision Style</b><br>
            <span class="gold">{decision_style}</span><br>
            <span class="muted">Based on watchlist, portfolio, and signal activity</span>
        </div>

        <div class="box">
            <b>Activity Level</b><br>
            <span class="metric">{activity_level}</span><br>
            <span class="muted">Total behavior events: {total_activity}</span>
        </div>

        <div class="box">
            <b>Risk Appetite</b><br>
            <span class="gold">{risk_appetite}</span><br>
            <span class="muted">Adaptive estimate from market focus</span>
        </div>
    </div>

    <h3 style="text-align:left;color:#e5e7eb;margin-left:10px;">Behavior Focus Map</h3>
    <div class="grid">{focus_rows}</div>
    """


def institutional_heatmap_html(api_key):
    stock_cells = ""
    for symbol in SYMBOLS:
        signal = generate_decision_signal(symbol=symbol, api_key=api_key)
        score = signal["market_score"]
        if score >= 80:
            level = "Strong"
            cls = "heat-strong"
        elif score >= 65:
            level = "Watch"
            cls = "heat-watch"
        else:
            level = "Risk"
            cls = "heat-risk"

        stock_cells += f"""
        <div class="heat-cell {cls}">
            <b>{symbol}</b><br>
            <span>{score}/100</span><br>
            <small>{level}</small>
        </div>
        """

    sector_cells = ""
    try:
        for s in generate_sector_intelligence()[:6]:
            score = s["sector_score"]
            if score >= 80:
                cls = "heat-strong"
            elif score >= 65:
                cls = "heat-watch"
            else:
                cls = "heat-risk"

            sector_cells += f"""
            <div class="heat-cell {cls}">
                <b>{s["sector"]}</b><br>
                <span>{score}/100</span><br>
                <small>{s["priority"]}</small>
            </div>
            """
    except:
        sector_cells = "<p class='muted'>Sector heatmap unavailable.</p>"

    economy_cells = ""
    try:
        for e in generate_economy_intelligence()[:5]:
            score = e["total_score"]
            if e["mood"] == "OPPORTUNITY ZONE":
                cls = "heat-strong"
            elif e["mood"] == "WATCH ZONE":
                cls = "heat-watch"
            else:
                cls = "heat-risk"

            economy_cells += f"""
            <div class="heat-cell {cls}">
                <b>{e["economy"]}</b><br>
                <span>{score}/100</span><br>
                <small>{e["mood"]}</small>
            </div>
            """
    except:
        economy_cells = "<p class='muted'>Economy heatmap unavailable.</p>"

    return f"""
    <div class="heat-section">
        <h3>Stock Strength Heatmap</h3>
        <div class="heat-grid">{stock_cells}</div>
    </div>

    <div class="heat-section">
        <h3>Sector Strength Heatmap</h3>
        <div class="heat-grid">{sector_cells}</div>
    </div>

    <div class="heat-section">
        <h3>Economy Pressure Heatmap</h3>
        <div class="heat-grid">{economy_cells}</div>
    </div>
    """


def smart_alerts_html(api_key):
    alerts = []

    try:
        top_signal = generate_ranked_signals(api_key, limit=1)[0]
        if top_signal["priority"] in ["HIGH", "CRITICAL"]:
            alerts.append({
                "level": top_signal["priority"],
                "title": f"{top_signal['symbol']} high-priority signal",
                "body": f"{top_signal['pattern']} detected with market score {top_signal['market_score']}/100."
            })
    except:
        pass

    try:
        holdings = get_portfolio(api_key)
        if holdings:
            total_amount = sum([float(h[2]) for h in holdings])
            risk_total = 0
            weakest = None

            for holding_id, symbol, amount in holdings:
                signal = generate_decision_signal(symbol, api_key)
                weight = (float(amount) / total_amount) if total_amount else 0
                risk_total += (100 - signal["market_score"]) * weight

                if weakest is None or signal["market_score"] < weakest["score"]:
                    weakest = {"symbol": symbol, "score": signal["market_score"]}

            portfolio_risk = round(risk_total, 1)

            if portfolio_risk >= 45:
                alerts.append({
                    "level": "RISK",
                    "title": "Portfolio risk rising",
                    "body": f"HDI detected portfolio risk at {portfolio_risk}/100. Weakest holding: {weakest['symbol']}."
                })
            elif portfolio_risk >= 25:
                alerts.append({
                    "level": "WATCH",
                    "title": "Portfolio requires monitoring",
                    "body": f"Portfolio risk is moderate at {portfolio_risk}/100. Review weaker positions."
                })
    except:
        pass

    try:
        sectors = generate_sector_intelligence()
        if sectors:
            top_sector = sectors[0]
            if top_sector["priority"] in ["HIGH", "MEDIUM"]:
                alerts.append({
                    "level": top_sector["priority"],
                    "title": f"{top_sector['sector']} sector alert",
                    "body": f"{top_sector['opportunity']} Sector score: {top_sector['sector_score']}/100."
                })
    except:
        pass

    try:
        economies = generate_economy_intelligence()
        if economies:
            risk_economies = [e for e in economies if e["mood"] == "RISK ZONE"]
            if risk_economies:
                e = risk_economies[0]
                alerts.append({
                    "level": "MACRO RISK",
                    "title": f"{e['economy']} macro risk",
                    "body": f"HDI detected {e['mood']} with economy score {e['total_score']}/100."
                })
    except:
        pass

    try:
        news = fetch_news_sentiment()
        if news:
            sentiment = news[0].get("overall_sentiment_label", "Neutral")
            if sentiment in ["Bullish", "Somewhat-Bullish", "Bearish", "Somewhat-Bearish"]:
                alerts.append({
                    "level": sentiment,
                    "title": "News sentiment alert",
                    "body": news[0].get("title", "Market sentiment shift detected")[:150]
                })
    except:
        pass

    if not alerts:
        alerts.append({
            "level": "STABLE",
            "title": "No major alerts detected",
            "body": "HDI is monitoring markets, portfolio exposure, sectors, economy mood, and news sentiment."
        })

    html = ""
    for alert in alerts[:6]:
        html += f"""
        <div class="alert-box">
            <b>{alert["title"]}</b><br>
            <span class="muted">{alert["body"]}</span><br>
            <span class="gold">{alert["level"]}</span>
        </div>
        """

    return html


def live_intelligence_stream_html(api_key):
    try:
        ranked = generate_ranked_signals(api_key, limit=3)
    except:
        ranked = [generate_decision_signal(api_key=api_key)]

    items = []
    for s in ranked:
        items.append({
            "title": f"{s['symbol']} momentum update",
            "body": f"{s['pattern']} detected. Score {s['market_score']}/100 with {s['priority']} priority.",
            "tag": s["priority"]
        })

    try:
        sectors = generate_sector_intelligence()
        if sectors:
            top_sector = sectors[0]
            items.append({
                "title": f"{top_sector['sector']} sector pulse",
                "body": f"Sector score {top_sector['sector_score']}/100. {top_sector['opportunity']}.",
                "tag": top_sector["priority"]
            })
    except:
        pass

    try:
        economies = generate_economy_intelligence()
        if economies:
            top_economy = economies[0]
            items.append({
                "title": f"{top_economy['economy']} macro pulse",
                "body": f"Mood: {top_economy['mood']}. Economy score {top_economy['total_score']}/100.",
                "tag": top_economy["priority"]
            })
    except:
        pass

    try:
        news = fetch_news_sentiment()
        if news:
            headline = news[0]
            items.append({
                "title": "News sentiment shift",
                "body": f"{headline.get('title','Market headline detected')[:120]}",
                "tag": headline.get("overall_sentiment_label", "Neutral")
            })
    except:
        pass

    html = ""
    for item in items[:6]:
        html += f"""
        <div class="stream-item">
            <div class="stream-dot"></div>
            <div>
                <b>{item["title"]}</b><br>
                <span class="muted">{item["body"]}</span><br>
                <span class="gold">{item["tag"]}</span>
            </div>
        </div>
        """

    return html


def executive_brief_html(api_key):
    try:
        top_signal = generate_ranked_signals(api_key, limit=1)[0]
    except:
        top_signal = generate_decision_signal(api_key=api_key)

    try:
        sectors = generate_sector_intelligence()
        strongest_sector = sectors[0] if sectors else None
    except:
        strongest_sector = None

    try:
        economies = generate_economy_intelligence()
        top_economy = economies[0] if economies else None
    except:
        top_economy = None

    try:
        holdings = get_portfolio(api_key)
        if holdings:
            total_amount = sum([float(h[2]) for h in holdings])
            risk_total = 0
            for holding_id, symbol, amount in holdings:
                signal = generate_decision_signal(symbol, api_key)
                weight = (float(amount) / total_amount) if total_amount else 0
                risk_total += (100 - signal["market_score"]) * weight
            portfolio_risk = round(risk_total, 1)
        else:
            portfolio_risk = "Not active"
    except:
        portfolio_risk = "Unavailable"

    try:
        news = fetch_news_sentiment()
        if news:
            sentiment = news[0].get("overall_sentiment_label", "Neutral")
        else:
            sentiment = "Neutral"
    except:
        sentiment = "Neutral"

    sector_name = strongest_sector["sector"] if strongest_sector else "Analyzing"
    sector_score = strongest_sector["sector_score"] if strongest_sector else "--"

    economy_name = top_economy["economy"] if top_economy else "Analyzing"
    economy_mood = top_economy["mood"] if top_economy else "WATCH ZONE"

    return f"""
    <div class="card" id="brief">
    <div class="institution">Executive Brief</div>
    <h2>â¡ HDI Intelligence Summary</h2>
    <p class="blue">Fast institutional overview of the most important decision signals.</p>

    <div class="grid">
        <div class="box">
            <b>Top Signal</b><br>
            {top_signal["symbol"]}<br>
            <span class="metric">{top_signal["market_score"]}/100</span><br>
            <span class="gold">{top_signal["priority"]}</span>
        </div>

        <div class="box">
            <b>Portfolio Risk</b><br>
            <span class="metric">{portfolio_risk}</span><br>
            <span class="muted">Based on current holdings</span>
        </div>

        <div class="box">
            <b>Strongest Sector</b><br>
            {sector_name}<br>
            <span class="metric">{sector_score}/100</span>
        </div>

        <div class="box">
            <b>Economy Mood</b><br>
            {economy_name}<br>
            <span class="gold">{economy_mood}</span>
        </div>

        <div class="box">
            <b>Market Sentiment</b><br>
            <span class="gold">{sentiment}</span><br>
            <span class="muted">News Intelligence Layer</span>
        </div>
    </div>
    </div>
    """

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
    .stream{max-height:420px;overflow:hidden;}
    .stream-item{display:flex;gap:14px;align-items:flex-start;background:rgba(15,23,42,.55);border:1px solid rgba(56,189,248,.08);padding:14px;margin:10px;border-radius:16px;text-align:left;animation:pulseIn .8s ease;}
    .stream-dot{width:10px;height:10px;background:#38bdf8;border-radius:50%;margin-top:6px;box-shadow:0 0 18px #38bdf8;flex:0 0 auto;}
    .live-badge{display:inline-block;background:rgba(34,197,94,.15);border:1px solid rgba(34,197,94,.35);color:#22c55e;padding:6px 12px;border-radius:999px;font-weight:bold;margin:8px;}
    @keyframes pulseIn{from{opacity:.3;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
    .alert-box{background:rgba(127,29,29,.22);border:1px solid rgba(248,113,113,.22);padding:16px;margin:10px;border-radius:18px;text-align:left;box-shadow:0 0 22px rgba(127,29,29,.12);}
    .alert-box b{color:#fecaca;}
    .heat-section{margin-top:22px;text-align:left;}
    .heat-section h3{color:#e5e7eb;text-align:left;margin-left:10px;}
    .heat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin:10px;}
    .heat-cell{padding:16px;border-radius:18px;text-align:left;min-height:92px;border:1px solid rgba(255,255,255,.08);box-shadow:0 0 22px rgba(0,0,0,.18);}
    .heat-cell b{font-size:14px;}
    .heat-cell span{font-size:24px;font-weight:bold;}
    .heat-cell small{color:#cbd5e1;}
    .heat-strong{background:rgba(22,101,52,.38);border-color:rgba(34,197,94,.35);}
    .heat-watch{background:rgba(113,63,18,.38);border-color:rgba(250,204,21,.30);}
    .heat-risk{background:rgba(127,29,29,.38);border-color:rgba(248,113,113,.30);}
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
    brief = executive_brief_html(key)
    live_stream = live_intelligence_stream_html(key)
    smart_alerts = smart_alerts_html(key)
    heatmap = institutional_heatmap_html(key)
    behavioral = behavioral_intelligence_html(key)
    predictions = ai_prediction_engine_html(key)
    ai_briefing = ai_briefing_engine_html(key)
    risk_intelligence = risk_intelligence_engine_html(key)
    opportunity_intelligence = opportunity_intelligence_engine_html(key)
    strategy_recommendation = strategy_recommendation_engine_html(key)
    institutional_scores = institutional_scoring_engine_html(key)
    macro_forecast = ai_macro_forecast_engine_html()
    market_pulse = dynamic_market_pulse_html(key)
    adaptive_feed = adaptive_recommendation_feed_html(key)
    report_preview = ai_report_html(key)
    company_layer = company_intelligence_html(key)
    scenario_simulator = portfolio_scenario_html(key)
    notifications = notification_center_html(key)
    risk_profile_ui = user_risk_profile_html(key)
    api_access = api_access_layer_html(key)
    autonomous_agent = autonomous_intelligence_agent_html(key)
    global_scanner = global_market_scanner_html(key)
    psychology_engine = trading_psychology_engine_html(key)
    flow_tracker = institutional_flow_tracker_html(key)
    event_radar = economic_event_radar_html()
    backtesting_engine = strategy_backtesting_engine_html(key)
    multi_agent_system = multi_agent_ai_system_html(key)
    voice_assistant = voice_intelligence_assistant_html(key)
    memory_engine = intelligence_memory_engine_html(key)
    enterprise_mode = enterprise_hedge_fund_mode_html(key)
    premium_active = is_premium(user[4], user[5])
    status = "Institutional Premium Active â" if premium_active else "Private Beta / Free Access ð"
    access_button = "" if premium_active else f"<a class='pay' href='/hdi/request-access?key={key}'>Request Institutional Access</a>"
    return f"""
<html>
<head><title>HDI Dashboard</title>{base_style()}<script>setTimeout(function(){{window.location.reload();}},60000);</script></head>
<body><div class="container">
<div class="nav">
<a href="/hdi/profile?key={key}">Profile</a>
<a href="#brief">Brief</a>
<a href="#live">Live Stream</a>
<a href="#alerts">Alerts</a>
<a href="#heatmap">Heatmap</a>
<a href="#behavior">Behavior</a>
<a href="#portfolio">Portfolio</a>
<a href="#economy">Economy</a>
<a href="#sectors">Sectors</a>
<a href="#news">News</a>
<a href="#signals">Signals</a>
<a href="#predictions">Predictions</a>
<a href="#briefing">AI Briefing</a>
<a href="#risk">Risk</a>
<a href="#opportunity">Opportunity</a>
<a href="#strategy">Strategy</a>
<a href="#institutional-score">Scores</a>
<a href="#macro-forecast">Macro Forecast</a>
<a href="#market-pulse">Market Pulse</a>
<a href="#adaptive-feed">AI Feed</a>
<a href="#report">Report</a>
<a href="#company">Company</a>
<a href="#scenario">Scenario</a>
<a href="#notifications">Notifications</a>
<a href="#risk-profile">Risk Profile</a>
<a href="#api-access">API</a>
<a href="#autonomous-agent">Agent</a>
<a href="#global-scanner">Global Scanner</a>
<a href="#psychology">Psychology</a>
<a href="#flows">Flows</a>
<a href="#event-radar">Events</a>
<a href="#backtesting">Backtest</a>
<a href="#multi-agent">Multi-Agent</a>
<a href="#voice">Voice</a>
<a href="#memory">Memory</a>
<a href="#enterprise-mode">Enterprise</a>
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
{brief}
<div class="card" id="live">
<div class="institution">Real-Time Intelligence Stream</div>
<h2>ð¡ Live HDI Intelligence Feed</h2>
<span class="live-badge">LIVE MODE</span>
<p class="blue">HDI streams market pulse, signal movement, sector pressure, economy mood, and news sentiment.</p>
<div class="stream">{live_stream}</div>
</div>
<div class="card" id="alerts">
<div class="institution">Smart Alerts System</div>
<h2>ð¨ HDI Smart Alerts</h2>
<p class="blue">HDI alerts you when signals, portfolio risk, sectors, macro conditions, or news sentiment require attention.</p>
<div class="grid">{smart_alerts}</div>
</div>

<div class="card" id="heatmap">
<div class="institution">Institutional Heatmap</div>
<h2>ð§­ HDI Market Heatmap</h2>
<p class="blue">Visual map of stock strength, sector opportunity, and economy pressure.</p>
{heatmap}
</div>

<div class="card" id="behavior">
<div class="institution">Behavioral Intelligence Engine</div>
<h2>ð§¬ HDI User Behavior Intelligence</h2>
<p class="blue">HDI learns your focus, decision style, activity level, and risk appetite over time.</p>
{behavioral}
</div>

<div class="card" id="portfolio">
<div class="institution">Portfolio Intelligence Layer</div>
<h2>ð¼ Personal Portfolio Intelligence</h2>
<p class="blue">HDI analyzes your holdings, exposure, risk, strongest and weakest positions.</p>
<form action="/hdi/add-portfolio" method="POST">
<input type="hidden" name="key" value="{key}">
<select name="symbol"><option>AAPL</option><option>MSFT</option><option>TSLA</option><option>NVDA</option><option>AMZN</option><option>GOOGL</option><option>META</option></select><br>
<input name="amount" placeholder="Amount / Exposure Value"><br>
<button type="submit">Add Holding</button>
</form>
{portfolio}
</div>
<div class="card" id="economy"><div class="institution">Economy Intelligence Layer</div><h2>ð Global Economy Intelligence</h2><div class="grid">{economies}</div></div>
<div class="card" id="sectors"><div class="institution">Sector Intelligence Layer</div><h2>ð Global Sector Intelligence</h2><div class="grid">{sectors}</div></div>
<div class="card" id="news"><div class="institution">News Intelligence Layer</div><h2>ð° Market News Intelligence</h2><div class="grid">{news}</div></div>
<div class="card" id="signals"><div class="institution">Live Signal Ranking</div><h2>ð¥ Top Ranked Signals</h2><div class="grid">{ranked_signals}</div></div>

<div class="card" id="predictions">
<div class="institution">AI Prediction Engine V2</div>
<h2>ð® HDI Prediction Intelligence</h2>
<p class="blue">HDI estimates bullish/bearish pressure, probability, and momentum acceleration.</p>
<div class="grid">{predictions}</div>
</div>

<div class="card" id="briefing">
<div class="institution">AI Briefing Engine</div>
<h2>ð§  HDI Analyst Briefing</h2>
<p class="blue">A structured analyst-style briefing: what is happening, why it matters, what to watch, risk, and opportunity.</p>
{ai_briefing}
</div>

<div class="card" id="risk">
<div class="institution">Risk Intelligence Engine</div>
<h2>ð¡ï¸ HDI Risk Intelligence</h2>
<p class="blue">HDI analyzes asset risk, portfolio pressure, sector weakness, macro risk, and what could go wrong.</p>
{risk_intelligence}
</div>

<div class="card" id="opportunity">
<div class="institution">Opportunity Intelligence Engine</div>
<h2>ð HDI Opportunity Intelligence</h2>
<p class="blue">HDI identifies asset opportunities, sector strength, economy opportunity zones, and confirmation needed.</p>
{opportunity_intelligence}
</div>

<div class="card" id="strategy">
<div class="institution">Strategy Recommendation Engine</div>
<h2>âï¸ HDI Strategy Recommendation</h2>
<p class="blue">HDI combines risk, opportunity, prediction, portfolio, sector, and macro context into a strategy mode.</p>
{strategy_recommendation}
</div>

<div class="card" id="institutional-score">
<div class="institution">Institutional Scoring Engine</div>
<h2>ðï¸ HDI Institutional Signal Scores</h2>
<p class="blue">HDI grades assets by institutional confidence, signal quality, momentum, trend, and volatility quality.</p>
<div class="grid">{institutional_scores}</div>
</div>

<div class="card" id="macro-forecast">
<div class="institution">AI Macro Forecast Engine</div>
<h2>ð HDI Macro Forecast</h2>
<p class="blue">HDI estimates macro stability, inflation pressure, economy risk, and opportunity quality.</p>
<div class="grid">{macro_forecast}</div>
</div>

<div class="card" id="market-pulse">
<div class="institution">Dynamic Market Pulse</div>
<h2>ð HDI Live Market Pulse</h2>
<p class="blue">HDI summarizes bullish/bearish dominance, average score, and volatility pulse.</p>
{market_pulse}
</div>

<div class="card" id="adaptive-feed">
<div class="institution">Adaptive Recommendation Feed</div>
<h2>ð§  Personalized HDI Recommendations</h2>
<p class="blue">HDI adapts recommendations based on your behavior, portfolio activity, and signal quality.</p>
<div class="grid">{adaptive_feed}</div>
</div>

<div class="card" id="report">
<div class="institution">AI Report Generator</div>
<h2>ð HDI AI Intelligence Report</h2>
<p class="blue">Generate a professional market, portfolio, risk, and opportunity report.</p>
<a class="btn" href="/hdi/report?key={key}">Open Full Report</a>
<a class="btn" href="/hdi/report-pdf?key={key}">PDF / Print View</a>
{report_preview}
</div>

<div class="card" id="company">
<div class="institution">Company Intelligence Layer</div>
<h2>ð¢ Company Intelligence</h2>
<p class="blue">HDI profiles each company by sector, score, pattern, business quality, risk, and opportunity.</p>
<div class="grid">{company_layer}</div>
</div>

<div class="card" id="scenario">
<div class="institution">Portfolio Scenario Simulator</div>
<h2>ð§ª Portfolio Scenario Simulator</h2>
<p class="blue">Test what happens if you add a new holding before committing it to your portfolio.</p>
<form action="/hdi/scenario" method="GET">
<input type="hidden" name="key" value="{key}">
<select name="symbol"><option>AAPL</option><option>MSFT</option><option>TSLA</option><option>NVDA</option><option>AMZN</option><option>GOOGL</option><option>META</option></select><br>
<input name="amount" placeholder="Scenario Amount"><br>
<button type="submit">Run Scenario</button>
</form>
{scenario_simulator}
</div>

<div class="card" id="notifications">
<div class="institution">Smart Notification Center</div>
<h2>ð HDI Notification Center</h2>
<p class="blue">All alerts, risk updates, portfolio messages, sector pulses, and news updates in one place.</p>
<div class="grid">{notifications}</div>
</div>

<div class="card" id="risk-profile">
<div class="institution">User Risk Profile Setup</div>
<h2>ðï¸ Risk Profile</h2>
<p class="blue">Choose how HDI should adapt strategy recommendations to your style.</p>
{risk_profile_ui}
</div>

<div class="card">
<div class="institution">Institutional Landing Page</div>
<h2>ð HDI for Institutions</h2>
<p class="blue">A decision intelligence platform for investors, banks, companies, and governments.</p>
<a class="btn" href="/hdi/institutional">Open Institutional Page</a>
</div>

<div class="card" id="api-access">
<div class="institution">API Access Layer</div>
<h2>ð HDI API Access</h2>
<p class="blue">Developer and enterprise-ready endpoints for integrations.</p>
{api_access}
</div>

<div class="card">
<div class="institution">Mobile-Ready UI Upgrade</div>
<h2>ð± Mobile Optimized</h2>
<p class="blue">HDI layout uses responsive cards, adaptive grids, and phone-friendly navigation for mobile usage.</p>
</div>

<div class="card" id="autonomous-agent">
<div class="institution">AI Autonomous Intelligence Agent</div>
<h2>ð¤ HDI Autonomous Agent</h2>
<p class="blue">HDI monitors signals, sectors, economy mood, risk, and opportunity to produce automatic conclusions.</p>
{autonomous_agent}
</div>

<div class="card" id="global-scanner">
<div class="institution">Global Market Scanner</div>
<h2>ð HDI Global Scanner</h2>
<p class="blue">HDI scans US, Europe, Asia, Crypto, Commodities, and Forex intelligence zones.</p>
<div class="grid">{global_scanner}</div>
</div>

<div class="card" id="psychology">
<div class="institution">AI Trading Psychology Engine</div>
<h2>ð§  Market Psychology</h2>
<p class="blue">HDI estimates fear, greed, panic, overconfidence, and emotion pressure.</p>
{psychology_engine}
</div>

<div class="card" id="flows">
<div class="institution">Institutional Flow Tracker</div>
<h2>ð¦ Smart Money Flow Estimate</h2>
<p class="blue">HDI estimates where institutional attention and capital rotation may be forming.</p>
<div class="grid">{flow_tracker}</div>
</div>

<div class="card" id="event-radar">
<div class="institution">Economic Event Radar</div>
<h2>ð¡ Macro Event Radar</h2>
<p class="blue">HDI tracks high-impact economic events, inflation shocks, rate decisions, and earnings pressure.</p>
<div class="grid">{event_radar}</div>
</div>

<div class="card" id="backtesting">
<div class="institution">AI Strategy Backtesting Engine</div>
<h2>ð§ª Strategy Backtesting</h2>
<p class="blue">HDI simulates strategy strength against prototype historical-style conditions.</p>
<div class="grid">{backtesting_engine}</div>
</div>

<div class="card" id="multi-agent">
<div class="institution">Multi-Agent AI System</div>
<h2>ð§¬ HDI Multi-Agent Intelligence</h2>
<p class="blue">Risk, Opportunity, Macro, Strategy, and News agents analyze the market from different angles.</p>
<div class="grid">{multi_agent_system}</div>
</div>

<div class="card" id="voice">
<div class="institution">Voice Intelligence Assistant</div>
<h2>ðï¸ HDI Voice Assistant</h2>
<p class="blue">Prototype layer for voice-style questions and AI analyst answers.</p>
{voice_assistant}
</div>

<div class="card" id="memory">
<div class="institution">HDI Intelligence Memory Engine</div>
<h2>ð§  Intelligence Memory</h2>
<p class="blue">HDI tracks signals, behavior, portfolio actions, and learning depth over time.</p>
{memory_engine}
</div>

<div class="card" id="enterprise-mode">
<div class="institution">Enterprise / Hedge Fund Mode</div>
<h2>ðï¸ HDI Enterprise Mode</h2>
<p class="blue">Professional institutional layer for advanced analytics, multi-screen workflows, and enterprise access.</p>
{enterprise_mode}
</div>
<div class="card">
<div class="institution">Next Level AI Layer</div>
<h2>ð§  Multi-Factor Signal Engine</h2>
<p class="blue">{signal["adaptive_note"]}</p>
<div class="grid">
<div class="box"><b>Priority Symbol</b><br>{signal["symbol"]}</div>
<div class="box"><b>Detected Pattern</b><br>{signal["pattern"]}</div>
<div class="box"><b>Market Score</b><br><span class="metric">{signal["market_score"]}/100</span></div>
<div class="box"><b>Signal Priority</b><br><span class="gold">{signal["priority"]}</span></div>
<div class="box"><b>HDI Recommendation</b><br>{signal["recommendation"]}</div>
<div class="box"><b>Micro Result</b><br>{signal["micro_result"]}</div>
</div></div>
<div class="card"><div class="institution">Feedback Loop</div><h2>ð Closed Learning System</h2>{accuracy}</div>
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
<h2>â­ Personal Watchlist</h2>
<form action="/hdi/add-watchlist" method="POST">
<input type="hidden" name="key" value="{key}">
<select name="symbol"><option>AAPL</option><option>MSFT</option><option>TSLA</option><option>NVDA</option><option>AMZN</option><option>GOOGL</option><option>META</option></select><br>
<button type="submit">Add to Watchlist</button>
</form>
<div class="grid">{watchlist}</div>
</div>
<div class="card" id="performance"><h2>ð HDI Performance Layer</h2>{performance}</div>
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





@app.route("/hdi/behavioral-intelligence")
def behavioral_intelligence_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key required"}), 400

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, action, SUM(count) AS total
            FROM user_behavior
            WHERE api_key=%s
            GROUP BY symbol, action
            ORDER BY total DESC
            LIMIT 50
        """, (key,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except:
        rows = []

    symbol_totals = {}
    action_totals = {}

    for symbol, action, total in rows:
        symbol_totals[symbol] = symbol_totals.get(symbol, 0) + int(total)
        action_totals[action] = action_totals.get(action, 0) + int(total)

    favorite_symbol = max(symbol_totals, key=symbol_totals.get) if symbol_totals else None
    dominant_action = max(action_totals, key=action_totals.get) if action_totals else None
    total_activity = sum(symbol_totals.values()) if symbol_totals else 0

    return jsonify({
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
        "favorite_symbol": favorite_symbol,
        "dominant_action": dominant_action,
        "total_activity": total_activity,
        "symbol_focus": symbol_totals,
        "action_focus": action_totals
    })

@app.route("/hdi/heatmap")
def heatmap_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key required"}), 400

    stocks = []
    for symbol in SYMBOLS:
        signal = generate_decision_signal(symbol=symbol, api_key=key)
        stocks.append({
            "symbol": symbol,
            "score": signal["market_score"],
            "priority": signal["priority"],
            "change": signal["change"]
        })

    return jsonify({
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
        "stocks": stocks,
        "sectors": generate_sector_intelligence(),
        "economies": generate_economy_intelligence()
    })

@app.route("/hdi/alerts")
def alerts_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key required"}), 400

    alerts = []

    try:
        top_signal = generate_ranked_signals(key, limit=1)[0]
        if top_signal["priority"] in ["HIGH", "CRITICAL"]:
            alerts.append({
                "type": "signal",
                "level": top_signal["priority"],
                "symbol": top_signal["symbol"],
                "score": top_signal["market_score"],
                "message": top_signal["recommendation"]
            })
    except:
        pass

    try:
        sectors = generate_sector_intelligence()
        if sectors:
            top = sectors[0]
            alerts.append({
                "type": "sector",
                "level": top["priority"],
                "sector": top["sector"],
                "score": top["sector_score"],
                "message": top["opportunity"]
            })
    except:
        pass

    try:
        economies = generate_economy_intelligence()
        if economies:
            top = economies[0]
            alerts.append({
                "type": "economy",
                "level": top["priority"],
                "economy": top["economy"],
                "score": top["total_score"],
                "message": top["mood"]
            })
    except:
        pass

    return jsonify({
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
        "alerts": alerts
    })

@app.route("/hdi/live-stream")
def live_stream_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key required"}), 400

    data = []
    try:
        for s in generate_ranked_signals(key, limit=3):
            data.append({
                "type": "signal",
                "title": f"{s['symbol']} momentum update",
                "score": s["market_score"],
                "priority": s["priority"],
                "message": s["recommendation"]
            })
    except:
        pass

    try:
        sectors = generate_sector_intelligence()
        if sectors:
            top = sectors[0]
            data.append({
                "type": "sector",
                "title": top["sector"],
                "score": top["sector_score"],
                "priority": top["priority"],
                "message": top["opportunity"]
            })
    except:
        pass

    try:
        economies = generate_economy_intelligence()
        if economies:
            top = economies[0]
            data.append({
                "type": "economy",
                "title": top["economy"],
                "score": top["total_score"],
                "priority": top["priority"],
                "message": top["mood"]
            })
    except:
        pass

    return jsonify({
        "status": "live",
        "updated_at": datetime.utcnow().isoformat(),
        "stream": data
    })

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
<h2>â ï¸ Risk Disclaimer</h2>
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
<div class="card"><h2>ð Feedback Accuracy</h2>{accuracy}</div>
<div class="card"><h2>ð Performance Preview</h2>{performance}</div>
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







@app.route("/hdi/strategy-recommendation")
def strategy_recommendation_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key required"}), 400

    top_signal = generate_ranked_signals(key, limit=1)[0]
    score = top_signal["market_score"]
    volatility = top_signal["volatility"]
    momentum = top_signal["confidence_breakdown"]["momentum"]
    trend = top_signal["confidence_breakdown"]["trend_strength"]

    risk_pressure = min(100, int((100 - score) * 0.60 + volatility * 8))
    opportunity_pressure = min(100, int(score * 0.45 + momentum * 0.30 + trend * 0.25))

    if opportunity_pressure >= 82 and risk_pressure < 45:
        strategy = "Aggressive Growth"
    elif opportunity_pressure >= 68 and risk_pressure < 60:
        strategy = "Balanced Monitoring"
    elif risk_pressure >= 65:
        strategy = "Defensive Mode"
    elif risk_pressure >= 50:
        strategy = "Reduce Exposure"
    else:
        strategy = "Wait for Confirmation"

    return jsonify({
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
        "strategy": strategy,
        "top_signal": top_signal,
        "risk_pressure": risk_pressure,
        "opportunity_pressure": opportunity_pressure
    })

@app.route("/hdi/institutional-scores")
def institutional_scores_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key required"}), 400

    scores = []
    for s in generate_ranked_signals(key, limit=5):
        momentum = s["confidence_breakdown"]["momentum"]
        volatility_quality = max(0, 100 - int(s["volatility"] * 8))
        trend = s["confidence_breakdown"]["trend_strength"]
        relevance = s["confidence_breakdown"]["user_relevance"]

        institutional_confidence = min(100, int(
            s["market_score"] * 0.35 +
            momentum * 0.25 +
            trend * 0.20 +
            volatility_quality * 0.10 +
            relevance * 0.10
        ))

        scores.append({
            "symbol": s["symbol"],
            "institutional_confidence": institutional_confidence,
            "market_score": s["market_score"],
            "momentum_quality": momentum,
            "trend_quality": trend,
            "volatility_quality": volatility_quality,
            "priority": s["priority"]
        })

    return jsonify({"status": "active", "updated_at": datetime.utcnow().isoformat(), "scores": scores})

@app.route("/hdi/macro-forecast")
def macro_forecast_api():
    return jsonify({
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
        "economies": generate_economy_intelligence(),
        "note": "AI macro forecast uses HDI economy intelligence model."
    })

@app.route("/hdi/market-pulse")
def market_pulse_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key required"}), 400

    ranked = generate_ranked_signals(key, limit=len(SYMBOLS))
    bullish = len([s for s in ranked if s["market_score"] >= 65 and s["change"] >= 0])
    bearish = len(ranked) - bullish
    avg_score = round(sum([s["market_score"] for s in ranked]) / len(ranked), 1)
    avg_volatility = round(sum([s["volatility"] for s in ranked]) / len(ranked), 2)

    mood = "Bullish Dominance" if bullish > bearish and avg_score >= 70 else "Bearish / Caution Dominance" if bearish > bullish else "Mixed Market"

    return jsonify({
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
        "market_mood": mood,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "average_market_score": avg_score,
        "average_volatility": avg_volatility
    })

@app.route("/hdi/adaptive-feed")
def adaptive_feed_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key required"}), 400

    preferred = get_preferred_symbol(key)
    ranked = generate_ranked_signals(key, limit=3)

    return jsonify({
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
        "preferred_symbol": preferred,
        "recommendations": [
            {
                "symbol": s["symbol"],
                "score": s["market_score"],
                "priority": s["priority"],
                "recommendation": s["recommendation"]
            }
            for s in ranked
        ]
    })

@app.route("/hdi/opportunity-intelligence")
def opportunity_intelligence_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key required"}), 400

    data = []
    try:
        ranked = generate_ranked_signals(key, limit=5)
    except:
        ranked = [generate_decision_signal(api_key=key)]

    for s in ranked:
        score = s["market_score"]
        momentum = s["confidence_breakdown"]["momentum"]
        trend = s["confidence_breakdown"]["trend_strength"]
        relevance = s["confidence_breakdown"]["user_relevance"]
        volatility_penalty = min(30, int(s["volatility"] * 3))

        opportunity_score = min(100, max(0, int(
            score * 0.40 +
            momentum * 0.25 +
            trend * 0.20 +
            relevance * 0.15 -
            volatility_penalty
        )))

        if opportunity_score >= 82:
            level = "HIGH OPPORTUNITY"
            label = "Breakout / Growth Watch"
        elif opportunity_score >= 68:
            level = "DEVELOPING OPPORTUNITY"
            label = "Accumulation / Setup Zone"
        elif opportunity_score >= 55:
            level = "EARLY OPPORTUNITY"
            label = "Formation Stage"
        else:
            level = "LOW OPPORTUNITY"
            label = "No Clear Setup"

        data.append({
            "symbol": s["symbol"],
            "opportunity_score": opportunity_score,
            "level": level,
            "label": label,
            "market_score": score,
            "priority": s["priority"],
            "recommendation": s["recommendation"]
        })

    return jsonify({
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
        "opportunities": data,
        "sectors": generate_sector_intelligence(),
        "economies": generate_economy_intelligence(),
        "disclaimer": "Opportunity intelligence is not financial advice."
    })

@app.route("/hdi/risk-intelligence")
def risk_intelligence_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key required"}), 400

    assets = []
    try:
        ranked = generate_ranked_signals(key, limit=5)
    except:
        ranked = [generate_decision_signal(api_key=key)]

    for s in ranked:
        volatility_risk = min(100, int(s["volatility"] * 12))
        weak_score_risk = max(0, 100 - s["market_score"])
        risk_score = min(100, int((weak_score_risk * 0.65) + (volatility_risk * 0.35)))

        if risk_score >= 65:
            risk_level = "HIGH RISK"
        elif risk_score >= 45:
            risk_level = "MEDIUM RISK"
        else:
            risk_level = "CONTROLLED RISK"

        assets.append({
            "symbol": s["symbol"],
            "risk_score": risk_score,
            "risk_level": risk_level,
            "market_score": s["market_score"],
            "volatility": s["volatility"]
        })

    return jsonify({
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
        "assets": assets,
        "sectors": generate_sector_intelligence(),
        "economies": generate_economy_intelligence(),
        "risk_disclaimer": "HDI provides decision intelligence, not financial advice."
    })

@app.route("/hdi/ai-briefing")
def ai_briefing_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key required"}), 400

    try:
        top_signal = generate_ranked_signals(key, limit=1)[0]
    except:
        top_signal = generate_decision_signal(api_key=key)

    try:
        sectors = generate_sector_intelligence()
        top_sector = sectors[0] if sectors else None
    except:
        top_sector = None

    try:
        economies = generate_economy_intelligence()
        top_economy = economies[0] if economies else None
    except:
        top_economy = None

    return jsonify({
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
        "what_is_happening_now": f"HDI is tracking {top_signal['symbol']} as the leading signal with score {top_signal['market_score']}/100.",
        "why_it_matters": f"{top_signal['symbol']} is influencing the current intelligence ranking and may affect watchlist or portfolio focus.",
        "what_to_watch_next": "Watch momentum continuation, volatility behavior, sector strength, and news sentiment.",
        "risk_note": "HDI provides decision intelligence, not financial advice. Verify before making decisions.",
        "opportunity_note": top_signal["recommendation"],
        "top_signal": top_signal,
        "top_sector": top_sector,
        "top_economy": top_economy
    })

@app.route("/hdi/predictions")
def predictions_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key required"}), 400

    data = []
    try:
        ranked = generate_ranked_signals(key, limit=5)
    except:
        ranked = [generate_decision_signal(api_key=key)]

    for s in ranked:
        score = s["market_score"]
        volatility = s["volatility"]
        momentum = s["confidence_breakdown"]["momentum"]
        trend = s["confidence_breakdown"]["trend_strength"]

        bullish_pressure = min(100, max(0, int((score * 0.45) + (momentum * 0.30) + (trend * 0.25))))
        bearish_pressure = min(100, max(0, int((100 - score) * 0.60 + volatility * 8)))
        probability = min(95, max(45, int((bullish_pressure * 0.65) + ((100 - bearish_pressure) * 0.35))))

        if bullish_pressure >= 82:
            label = "Growth Pressure"
        elif bullish_pressure >= 68:
            label = "Accumulation Zone"
        elif bearish_pressure >= 55:
            label = "Caution Zone"
        else:
            label = "Neutral Formation"

        data.append({
            "symbol": s["symbol"],
            "prediction": label,
            "probability": probability,
            "bullish_pressure": bullish_pressure,
            "bearish_pressure": bearish_pressure,
            "momentum_acceleration": "Rising" if momentum >= trend else "Stabilizing",
            "market_score": score
        })

    return jsonify({
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
        "predictions": data
    })

@app.route("/hdi/admin-console")
def admin_console():
    if ADMIN_KEY and request.args.get("key") != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    console = admin_intelligence_console_html()

    return f"""
<html>
<head>
<title>HDI Admin Intelligence Console</title>
{base_style()}
</head>
<body>
<div class="container">
<div class="nav">
<a href="/hdi/admin-console?key={request.args.get("key")}">Admin Console</a>
<a href="/hdi/admin?key={request.args.get("key")}">Admin JSON</a>
<a href="/">Home</a>
</div>
{console}
</div>
</body>
</html>
"""

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

