import time
import json
import os
import subprocess
import requests
import ccxt
import pandas as pd
from datetime import datetime

# ========================================================
# 1. إعدادات التليجرام وبيانات Binance Testnet
# ========================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN1")
TELEGRAM_CHAT_ID = "7760401819"

BINANCE_API_KEY = "eEQI3GrUGBdGzHmjSTxg7us7uPM2ZZ69mQddzj3rw6zDL4TbSwEVAHWgp5BU1cAO"
BINANCE_SECRET = "pwQHVpCsrO1DXxxpgrSf4gGZZddOUHZRPEL448kO3IMZILDFR6HNcgUjD4EWemou"

POSITION_SIZE_PERCENT = 0.10    # 10% لكل صفقة
MAX_OPEN_TRADES = 10            # الحد الأقصى الصارم: 10 صفقات متزامنة (10 × 10% = 100% من المحفظة)

# ========================================================
# 🛡️ المعايير الدفاعية الفائقة لتعطيل الخسائر وحماية الأرباح
# ========================================================
MIN_TECHNICAL_SL_PCT = 2.2      # رفع الحد الأدنى للوقف لمنع ضربه بالضجيج السعري (بين 2.2% إلى 3.5%)
MAX_TECHNICAL_SL_PCT = 3.5      # الحد الأقصى لوقف الخسارة الفني
BOS_VOLUME_MULTIPLIER = 1.30    # رفع شرط فوليوم الكسر إلى 130% لضمان الانطلاقة المؤسساتية
COOLDOWN_AFTER_LOSSES = 2       # عدد الخسائر المتتالية لتفعيل قاطع الأمان
COOLDOWN_HOURS = 2              # عدد ساعات التهدئة عند تفعيل قاطع الأمان
HISTORY_FILE = "trades_permanent_history.json"

RAW_COINS = [
    'BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'DOT',
    'POL', 'NEAR', 'SHIB', 'LTC', 'UNI', 'ICP', 'BCH', 'ATOM', 'XLM', 'ETC',
    'FIL', 'HBAR', 'INJ', 'IMX', 'RENDER', 'OP', 'ARB', 'SUI', 'TIA', 'SEI',
    'GRT', 'AAVE', 'ALGO', 'THETA', 'FLOW', 'CHZ', 'GALA', 'SAND', 'MANA', 'AXS',
    'KAVA', 'CELO', 'AR', 'PYTH', 'MANTA', 'JUP', 'BONK', 'FLOKI', 'PEPE', 'WIF',
    'NOT', 'TAO', 'FET', 'PIXEL', 'XEC', 'PENDLE', 'STRK', 'ALT', 'PORTAL', 'XAI',
    'NEXO', 'GMX', 'CRV', 'CAKE', '1INCH', 'SNX', 'COMP', 'ZK', 'ZRO', 'ENA',
    'SAGA', 'IOST', 'JTO', 'QTUM', 'MINA', 'APT', 'BOME', 'GAS', 'TRUMP', 'ZIL',
    'IOTA', 'DASH', 'ZEC', 'RVN', 'KSM', 'BICO', 'HMSTR', 'CVC', 'BAND', 'DUSK',
    'LSK', 'SNDKB', 'XPL', 'VANA', 'AVA', 'OGN', 'OG', 'SENT', 'PUMP', 'ONT',
    'WLD', 'HYPE', 'SKL', 'CATI', 'MUUB', 'JST', 'ONE', 'SUPER', 'AMP', 'OPG',
    'EPIC', 'EDEN', 'BEAMX', 'GPS', 'AVNT', 'OPEN', 'OSMO', 'SPK', 'TRX', 'ADBEB',
    'MBL', 'MUBARAK', 'QUICK', 'CHIP', 'AT', 'SHELL', 'BROCCOLI714', 'ERA', 'AGLD', 'GNS',
    'IOTX', 'CETUS', 'PENGU', 'TUT', 'TWT', 'HOME', 'PEOPLE', 'CITY', 'RED', 'BANANA',
    'VET', 'MOVE', 'BANK', '1000SATS', 'PSG', 'ATM', 'PORTO', 'MEME', 'NVDAB', '1000CAT',
    'GTC', 'BB', 'HOT', 'C98', 'MANTRA', 'KMNO', 'SOLV', 'FLUX', 'HEMI', 'VTHO',
    'CYPHB', 'ANIME', 'ZAMA', 'CRCLB', 'PROM', 'BLUR', 'COINB', 'ONDO', 'FF', 'EDU',
    'ASTSB', 'AERO', 'JASMY'
]

SYMBOLS = list(dict.fromkeys([f"{coin.strip().upper()}/USDT" for coin in RAW_COINS]))
TIMEFRAME = '1h'

binance_testnet = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot', 'adjustForTimeDifference': True}
})
binance_testnet.set_sandbox_mode(True)

market_exchange = ccxt.kucoin({'enableRateLimit': True})

# ========================================================
# 2. إدارة السجل الدائم للصفقات مع نظام الحماية من التكرار
# ========================================================
def deduplicate_ledger(data):
    if not isinstance(data, dict):
        return data

    # 1. تنقية الصفقات المفتوحة من أي تكرار
    seen_open = set()
    clean_open = []
    for t in data.get("open_trades", []):
        sym = t.get("symbol")
        if sym and sym not in seen_open:
            seen_open.add(sym)
            clean_open.append(t)
    data["open_trades"] = clean_open

    # 2. تنقية الصفقات الرابحة من أي تكرار
    seen_wins = set()
    clean_wins = []
    for w in data.get("winning_trades", []):
        key = (w.get("symbol"), w.get("entry"), w.get("time"))
        if key not in seen_wins:
            seen_wins.add(key)
            clean_wins.append(w)
    data["winning_trades"] = clean_wins

    # 3. تنقية الصفقات الخاسرة من أي تكرار
    seen_losses = set()
    clean_losses = []
    for l in data.get("losing_trades", []):
        key = (l.get("symbol"), l.get("entry"), l.get("time"))
        if key not in seen_losses:
            seen_losses.add(key)
            clean_losses.append(l)
    data["losing_trades"] = clean_losses

    # 4. إعادة احتساب الأرباح والرصيد بدقة رياضية متناهية
    total_profit = sum(w.get("profit", 0.0) for w in clean_wins) + sum(l.get("loss", 0.0) for l in clean_losses)
    data["total_profit_usdt"] = total_profit
    data["current_balance"] = data.get("starting_balance", 1000.0) + total_profit

    return data

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return deduplicate_ledger(data)
        except:
            pass
    return {
        "starting_balance": 1000.0,
        "current_balance": 1000.0,
        "total_profit_usdt": 0.0,
        "winning_trades": [],
        "losing_trades": [],
        "open_trades": [],
        "cooldown_until": 0
    }

def save_history(data):
    data = deduplicate_ledger(data)
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        subprocess.run(['git', 'config', 'user.name', 'SMC-Bot'], check=False)
        subprocess.run(['git', 'config', 'user.email', 'bot@github.actions'], check=False)
        subprocess.run(['git', 'add', HISTORY_FILE], check=False)
        subprocess.run(['git', 'commit', '-m', 'chore: update trades ledger [skip ci]'], check=False)
        subprocess.run(['git', 'push'], check=False)
    except:
        pass

# ========================================================
# 3. دوال التليجرام وفحص صحة البيتكوين
# ========================================================
def send_telegram(message, chat_id=None):
    cid = chat_id or TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            payload.pop("parse_mode", None)
            requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def check_btc_health():
    """درع البيتكوين الصارم: فحص اتجاه البيتكوين اللحظي على فريم 1H لمنع الشراء في مسار هابط"""
    try:
        btc_ohlcv = market_exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=35)
        if btc_ohlcv and len(btc_ohlcv) >= 20:
            df = pd.DataFrame(btc_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
            curr_c = df['close'].iloc[-1]
            ema_20 = df['ema_20'].iloc[-1]

            ticker = market_exchange.fetch_ticker('BTC/USDT')
            chg_24h = ticker.get('percentage', 0.0) or 0.0

            # البيتكوين صحي فقط إذا كان سعره فوق متوسط EMA 20 ولم يهبط انهيارياً (> -3.0%)
            is_above_ema = curr_c >= (ema_20 * 0.998)
            is_macro_ok = chg_24h >= -3.0

            status_str = f"صاعد فوق EMA20 ({chg_24h:+.2f}%) 🟢" if is_above_ema else f"هابط تحت EMA20 ({chg_24h:+.2f}%) 🔴 مسار تصحيحي"
            return (is_above_ema and is_macro_ok), status_str, curr_c, chg_24h
    except:
        pass
    return True, "طبيعي 🟡", 0.0, 0.0

def get_binance_balance():
    try:
        bal = binance_testnet.fetch_balance()
        usdt = bal['free'].get('USDT', 0.0)
        return float(usdt) if usdt > 0 else 1000.0
    except:
        hist = load_history()
        return hist.get("current_balance", 1000.0)

# ========================================================
# 4. رادار نبض السوق الساعي (يبعث كل ساعة لتوضيح حالة السوق)
# ========================================================
last_scan_stats = {
    "below_ema": 0,
    "no_bos": 0,
    "low_vol": 0,
    "rsi_fail": 0,
    "btc_desc": "",
    "btc_blocked": False,
    "cooldown_active": False,
    "cooldown_rem": 0,
    "total": len(SYMBOLS)
}

def send_hourly_market_radar(chat_id=None):
    hist = load_history()
    bal = hist.get("current_balance", 1000.0)
    open_count = len(hist.get("open_trades", []))
    btc_ok, btc_desc, btc_price, btc_chg = check_btc_health()

    b_ema = last_scan_stats.get("below_ema", 0)
    n_bos = last_scan_stats.get("no_bos", 0)
    l_vol = last_scan_stats.get("low_vol", 0)

    # تشخيص حالة الأمان الخاصة
    safety_notes = []
    if last_scan_stats.get("cooldown_active", False):
        rem = last_scan_stats.get("cooldown_rem", 0)
        safety_notes.append(f"🛑 *قاطع أمان المحفظة نشط:* تجميد الشراء مؤقتاً لحماية رصيدك (متبقي `{rem}` دقيقة).")
    
    if last_scan_stats.get("btc_blocked", False) or not btc_ok:
        safety_notes.append("🛡️ *درع البيتكوين مفعل:* البيتكوين تحت متوسط EMA20 (تم حظر صفقات الشراء لتجنب النزيف الجماعي).")
    
    safety_msg = "\n".join(safety_notes)
    if safety_msg:
        safety_msg = f"{safety_msg}\n━━━━━━━━━━━━━━━━━━\n"

    msg = (
        f"📡 *رادار السوق الدفاعي ونبض شمعة الساعة* ⏰\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *البيتكوين (BTC):* `${btc_price:,.1f}` ({btc_chg:+.2f}%)\n"
        f"🌐 *اتجاه البيتكوين اللحظي:* {btc_desc}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{safety_msg}"
        f"🔍 *تشخيص الفحص المؤسساتي (+130% Volume):*\n"
        f"• *فلتر الاتجاه (EMA20):* `{b_ema}` عملة تحت المسار الصاعد.\n"
        f"• *فلتر الكسر (BOS):* `{n_bos}` عملة لم تحقق كسر قمة فني حقيقي.\n"
        f"• *فلتر السيولة المؤسساتية:* `{l_vol}` عملة فشلت في تحقيق شرط السيولة (+130%).\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💼 *المحفظة:* `{open_count}/{MAX_OPEN_TRADES}` صفقات نشطة\n"
        f"💵 *إجمالي الرصيد المحمي:* `${bal:,.2f}` USDT\n"
        f"🛡️ *نظام حماية الأرباح وقاطع الأمان شغال 24/7 ولن يدخل إلا في الصفقات المضمونة فنياً!*"
    )
    send_telegram(msg, chat_id=chat_id)

# ========================================================
# 5. تقرير الأداء الشامل عند إرسال كلمة (تقرير)
# ========================================================
def send_full_detailed_report(chat_id=None):
    hist = load_history()
    bal = hist.get("current_balance", 1000.0)
    wins = hist.get("winning_trades", [])
    losses = hist.get("losing_trades", [])
    open_tr = hist.get("open_trades", [])

    total_closed = len(wins) + len(losses)
    win_rate = (len(wins) / total_closed * 100) if total_closed > 0 else 0.0
    net_pnl = hist.get("total_profit_usdt", 0.0)

    wins_text = "".join([f"• `{w['symbol']}`: دخول `${w['entry']}` ⬅️ خروج `${w['exit']}` (+${w['profit']:.2f})\n" for w in wins[-5:]]) or "لا توجد صفقات رابحة مغلقة بعد.\n"
    losses_text = "".join([f"• `{l['symbol']}`: دخول `${l['entry']}` ⬅️ وقف `${l['exit']}` (${l['loss']:.2f})\n" for l in losses[-5:]]) or "لا توجد صفقات خاسرة حتى الآن.\n"
    open_text = "".join([f"• `{o['symbol']}`: دخول `${o['entry']}` | وقف `${o['sl']}` | هدف `${o['tp2']}`\n" for o in open_tr[-10:]]) or "لا توجد صفقات مفتوحة الآن.\n"

    msg = (
        f"📊 *السجل الدائم لأداء صفقات SMC Pro المحمي* 📊\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💼 *إجمالي رصيد المحفظة الحالي:* `${bal:,.2f}` USDT 💵\n"
        f"💰 *صافي الأرباح الكلية المحققة:* `{net_pnl:+.2f}$` USDT\n"
        f"🎯 *نسبة الفوز الحقيقية:* `{win_rate:.1f}%` ({len(wins)} رابحة / {len(losses)} خاسرة)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ *آخر الصفقات الرابحة:* 🟢\n"
        f"{wins_text}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"❌ *آخر صفقات ضرب الوقف:* 🔴\n"
        f"{losses_text}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏳ *الصفقات النشطة بالمحفظة ({len(open_tr)}/{MAX_OPEN_TRADES}):* 🟡\n"
        f"{open_text}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 *أرسل كلمة (تقرير) أو (رادار) في أي وقت لتحديث كشف الحساب فوراً!*"
    )
    send_telegram(msg, chat_id=chat_id)

last_telegram_update_id = 0
def check_telegram_commands():
    global last_telegram_update_id
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_telegram_update_id + 1}&timeout=1"
        res = requests.get(url, timeout=3).json()
        if res.get('ok') and res.get('result'):
            for item in res['result']:
                last_telegram_update_id = item['update_id']
                msg_obj = item.get('message') or item.get('edited_message') or {}
                text = msg_obj.get('text', '').strip().lower()
                sender_chat_id = msg_obj.get('chat', {}).get('id')
                
                # تقرير كشف الحساب
                if any(w in text for w in ['تقرير', 'report', 'صفقات', 'trades', 'ارباح', 'أرباح', 'رصيد', 'balance']):
                    send_full_detailed_report(chat_id=sender_chat_id)
                # رادار نبض السوق
                elif any(w in text for w in ['رادار', 'radar', 'السوق', 'market', 'وضع السوق']):
                    send_hourly_market_radar(chat_id=sender_chat_id)
    except Exception as e:
        pass

# ========================================================
# 6. متابعة الصفقات مع حجز الأرباح ونقل الوقف وقاطع الأمان
# ========================================================
def track_open_trades():
    hist = load_history()
    open_trades = hist.get("open_trades", [])
    if not open_trades: return

    updated_open = []
    changed = False

    for t in open_trades:
        symbol = t['symbol']
        entry = t['entry']
        sl = t['sl']
        tp1 = t.get('tp1', entry * 1.02)
        tp2 = t['tp2']
        amount = t['amount']
        tp1_hit = t.get('tp1_hit', False)

        try:
            ticker = market_exchange.fetch_ticker(symbol)
            curr = ticker['last']

            # 1. تحقق الهدف الأول (TP1): حجز ربح 50% ونقل الوقف لنقطة الدخول (Breakeven)
            if not tp1_hit and curr >= tp1:
                profit_50 = (amount * 0.5) * ((tp1 - entry) / entry)
                try:
                    qty_half = (amount * 0.5) / entry
                    binance_testnet.create_market_sell_order(symbol, qty_half)
                except:
                    pass

                t['sl'] = entry
                t['tp1_hit'] = True
                t['amount'] = round(amount * 0.5, 2)
                t['profit_locked'] = profit_50

                hist["total_profit_usdt"] += profit_50
                hist["current_balance"] += profit_50
                changed = True

                msg = (
                    f"🎯 *تم تحقيق الهدف الأول بنجاح (TP1 HIT)!* 🎉\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"📥 *الدخول:* `${entry:.4f}` ⬅️ *سعر الهدف الأول:* `${tp1:.4f}`\n"
                    f"💵 *تم حجز ربح (50%):* `+${profit_50:.2f}` USDT 🟢\n"
                    f"🛡️ *تم نقل وقف الخسارة إلى سعر الدخول (Breakeven):* `${entry:.4f}`\n"
                    f"💼 *إجمالي رصيد المحفظة المحدث:* `${hist['current_balance']:,.2f}` USDT 💵\n"
                    f"💰 *صافي أرباح المحفظة الكلية:* `${hist['total_profit_usdt']:+.2f}` USDT\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🚀 *الصفقة الآن خالية من أي مخاطرة تماماً وننتظر الهدف الثاني TP2!*"
                )
                send_telegram(msg)
                updated_open.append(t)
                continue

            # 2. تحقق الهدف الثاني بالكامل (TP2)
            elif curr >= tp2:
                rem_profit = amount * ((tp2 - entry) / entry)
                total_win = rem_profit + t.get('profit_locked', 0.0)
                try:
                    qty_rem = amount / entry
                    binance_testnet.create_market_sell_order(symbol, qty_rem)
                except:
                    pass

                hist["winning_trades"].append({
                    "symbol": symbol, "entry": entry, "exit": tp2, "profit": total_win,
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M')
                })
                hist["total_profit_usdt"] += rem_profit
                hist["current_balance"] += rem_profit
                changed = True

                msg = (
                    f"🚀 *تم تحقيق الهدف الثاني بالكامل (TP2 HIT)!* 🎉\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"📥 *سعر الدخول:* `${entry:.4f}` ⬅️ *سعر الخروج الأقصى:* `${tp2:.4f}`\n"
                    f"💵 *صافي الربح الكلي للصفقة:* `+${total_win:.2f}` USDT 🟢\n"
                    f"💼 *إجمالي رصيد المحفظة المحدث:* `${hist['current_balance']:,.2f}` USDT 💵\n"
                    f"💰 *صافي أرباح المحفظة الكلية:* `${hist['total_profit_usdt']:+.2f}` USDT\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                send_telegram(msg)
                continue

            # 3. ملامسة وقف الخسارة
            elif curr <= sl:
                try:
                    qty_close = amount / entry
                    binance_testnet.create_market_sell_order(symbol, qty_close)
                except:
                    pass

                if tp1_hit:
                    hist["winning_trades"].append({
                        "symbol": symbol, "entry": entry, "exit": sl,
                        "profit": t.get('profit_locked', 0.0),
                        "time": datetime.now().strftime('%Y-%m-%d %H:%M')
                    })
                    changed = True

                    msg = (
                        f"🛡️ *خروج على سعر الدخول (Breakeven Exit)* 🛡️\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 *العملة:* `#{symbol}`\n"
                        f"💡 النصف المتبقي خرج على سعر الدخول `${entry:.4f}` بدون أي خسارة.\n"
                        f"💰 *الصفقة انتهت بربح صافي من الهدف الأول:* `+${t.get('profit_locked', 0.0):.2f}` USDT 🟢\n"
                        f"💼 *إجمالي رصيد المحفظة المحدث:* `${hist['current_balance']:,.2f}` USDT 💵\n"
                        f"💰 *صافي أرباح المحفظة الكلية:* `${hist['total_profit_usdt']:+.2f}` USDT\n"
                        f"━━━━━━━━━━━━━━━━━━"
                    )
                    send_telegram(msg)
                    continue
                else:
                    loss = amount * ((sl - entry) / entry)
                    now_ts = time.time()
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
                    hist["losing_trades"].append({
                        "symbol": symbol, "entry": entry, "exit": sl, "loss": loss,
                        "time": now_str, "timestamp": now_ts
                    })
                    hist["total_profit_usdt"] += loss
                    hist["current_balance"] += loss
                    changed = True

                    # 🛡️ تفعيل قاطع الأمان التلقائي (Circuit Breaker)
                    # فحص إذا حدثت خسارتان متتاليتان خلال آخر ساعتين (7200 ثانية)
                    recent_losses = [
                        l for l in hist.get("losing_trades", [])
                        if (now_ts - l.get("timestamp", now_ts)) <= 7200
                    ]
                    if len(recent_losses) >= COOLDOWN_AFTER_LOSSES:
                        cooldown_end = now_ts + (COOLDOWN_HOURS * 3600)
                        hist["cooldown_until"] = cooldown_end
                        cb_msg = (
                            f"🛡️ *تفعيل قاطع أمان المحفظة (Circuit Breaker)!* 🛡️\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"⚠️ تم رصد ضرب وقفي خسارة متتاليين نتيجة تراجع عام في السوق.\n"
                            f"🛑 *تم تجميد فتح أي صفقات جديدة آلياً لمدة {COOLDOWN_HOURS} ساعات* لحماية رأس المال حتى تستقر السيولة!\n"
                            f"💼 *رصيد المحفظة الحالي:* `${hist['current_balance']:,.2f}` USDT"
                        )
                        send_telegram(cb_msg)

                    msg = (
                        f"🛑 *تنبيه: ضرب وقف الخسارة الفني (STOP LOSS)* 🛑\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 *العملة:* `#{symbol}`\n"
                        f"📥 *سعر الدخول:* `${entry:.4f}` ⬅️ *سعر الخروج:* `${sl:.4f}`\n"
                        f"📉 *الخسارة المحسوبة:* `${loss:.2f}` USDT 🔴\n"
                        f"💼 *إجمالي رصيد المحفظة المحدث:* `${hist['current_balance']:,.2f}` USDT 💵\n"
                        f"💰 *صافي أرباح المحفظة الكلية:* `${hist['total_profit_usdt']:+.2f}` USDT\n"
                        f"━━━━━━━━━━━━━━━━━━"
                    )
                    send_telegram(msg)
                    continue

            updated_open.append(t)
        except:
            updated_open.append(t)

    if changed:
        hist["open_trades"] = updated_open
        save_history(hist)

# ========================================================
# 7. محرك SMC الفائق الدفاعي (Max 10 صفقات + درع البيتكوين)
# ========================================================
def scan_smc():
    global last_scan_stats
    hist = load_history()
    open_trades = hist.get("open_trades", [])
    open_symbols = [t['symbol'] for t in open_trades]

    below_ema_c = 0
    no_bos_c = 0
    low_vol_c = 0
    rsi_fail_c = 0
    new_opened = 0

    # سقف الـ 10 صفقات
    if len(open_trades) >= MAX_OPEN_TRADES:
        return 0

    # 1. فحص قاطع أمان الصدمات (Circuit Breaker Cooldown)
    cooldown_until = hist.get("cooldown_until", 0)
    now_ts = time.time()
    if now_ts < cooldown_until:
        rem_min = int((cooldown_until - now_ts) / 60)
        last_scan_stats["cooldown_active"] = True
        last_scan_stats["cooldown_rem"] = rem_min
        return 0
    else:
        last_scan_stats["cooldown_active"] = False

    # 2. درع البيتكوين الصارم (منع الشراء إذا كان البيتكوين هابطاً تحت EMA20)
    btc_ok, btc_desc, btc_price, btc_chg = check_btc_health()
    last_scan_stats["btc_desc"] = btc_desc
    if not btc_ok:
        last_scan_stats["btc_blocked"] = True
        return 0
    last_scan_stats["btc_blocked"] = False

    for symbol in SYMBOLS:
        if len(open_trades) >= MAX_OPEN_TRADES:
            break

        if symbol in open_symbols:
            continue

        try:
            ohlcv = market_exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=70)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # 1. فلتر الاتجاه التوازني (EMA 20)
            df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
            curr_price = df['close'].iloc[-1]
            ema_20 = df['ema_20'].iloc[-1]

            if curr_price < ema_20:
                below_ema_c += 1
                continue

            # 2. فلتر عزم المومنتوم النقي RSI(14) بين 52 و 66 (تجنب الضعف والتشبع)
            delta = df['close'].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(window=14, min_periods=14).mean()
            avg_loss = loss.rolling(window=14, min_periods=14).mean()
            rs = avg_gain / avg_loss.replace(0, 1e-9)
            df['rsi'] = 100 - (100 / (1 + rs))
            rsi = df['rsi'].iloc[-1]

            if rsi < 52.0 or rsi > 66.0:
                rsi_fail_c += 1
                continue

            # 3. فحص الكسر والفوليوم المؤسساتي الصارم (+130%) على الشمعة السابقة المكتملة 100%
            breakout_candle_close = df['close'].iloc[-2]
            breakout_candle_vol = df['volume'].iloc[-2]
            vol_ma20 = df['volume'].rolling(window=20).mean().iloc[-2]

            prev_high = df['high'].iloc[-12:-2].max()
            is_bos = breakout_candle_close > prev_high
            is_vol_confirmed = breakout_candle_vol >= (vol_ma20 * BOS_VOLUME_MULTIPLIER)

            if not is_bos:
                no_bos_c += 1
                continue
            if not is_vol_confirmed:
                low_vol_c += 1
                continue

            # 4. فحص فجوة الـ FVG المؤسساتية
            c1_high = df['high'].iloc[-3]
            c3_low = df['low'].iloc[-1]
            is_fvg = c3_low >= (c1_high * 0.999)

            if is_bos and is_vol_confirmed and is_fvg:
                entry = curr_price

                # 5. وقف الخسارة الفني المنيع (بين 2.2% إلى 3.5% لعزل الضجيج العشوائي)
                ob_low = df['low'].iloc[-3]
                fvg_low = df['low'].iloc[-2]
                technical_low = min(ob_low, fvg_low)

                sl = technical_low * 0.998
                sl_pct = ((entry - sl) / entry) * 100

                if sl_pct < MIN_TECHNICAL_SL_PCT or sl_pct > MAX_TECHNICAL_SL_PCT:
                    continue

                risk = entry - sl
                tp1 = entry + (risk * 1.6)
                tp2 = entry + (risk * 2.8)

                tp1_pct = ((tp1 - entry) / entry) * 100
                tp2_pct = ((tp2 - entry) / entry) * 100

                smc_reason = "BOS + Institutional FVG + Bullish Momentum (130% Vol)"
                bal = get_binance_balance()
                trade_amount = round(bal * POSITION_SIZE_PERCENT, 2)

                try:
                    qty = trade_amount / entry
                    binance_testnet.create_market_buy_order(symbol, qty)
                    exec_note = "✅ تم الشراء في Binance Testnet"
                except:
                    exec_note = "⚡ تم التتبع آلياً بأسعار باينانس"

                new_trade = {
                    "symbol": symbol, "entry": entry, "sl": sl, "original_sl": sl,
                    "tp1": tp1, "tp2": tp2, "amount": trade_amount,
                    "tp1_hit": False, "profit_locked": 0.0,
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M')
                }
                hist["open_trades"].append(new_trade)
                open_symbols.append(symbol)
                save_history(hist)
                new_opened += 1

                coin_base = symbol.split('/')[0]
                binance_link = f"https://www.binance.com/en/trade/{coin_base}_USDT"
                tv_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{coin_base}USDT"

                msg = (
                    f"🚀 *إشارة تداول فنية فائقة الجودة (+A SMC Defended)!* 🟢\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"⏰ *فريم الإشارة:* `{TIMEFRAME}`\n"
                    f"🎯 *الاستراتيجية:* SMC Pro + RSI Momentum + BTC Health 🧠\n"
                    f"📊 *قوة الزخم (RSI):* `{rsi:.1f}` (منطقة الزخم الصاعد النقي)\n"
                    f"📌 *التأكيد الفني:* كسر هيكل صاعد فوق EMA20 بفوليوم مؤسساتي +130%\n"
                    f"🛡️ *حالة البيتكوين:* {btc_desc}\n"
                    f"🔍 *السبب الفني:* `{smc_reason}`\n"
                    f"🟢 *توجيه السيولة:* {exec_note} 🟢\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💵 *سعر الدخول:* `${entry:.4f}`\n"
                    f"🛡️ *قاع الدعم (OB/FVG Low):* `${technical_low:.4f}`\n"
                    f"🛑 *وقف الخسارة الفني المنيع:* `${sl:.4f}` (-{sl_pct:.2f}%)\n"
                    f"🎯 *الهدف الأول (TP1 - 1:1.6):* `${tp1:.4f}` (+{tp1_pct:.2f}%) *(حجز 50% + نقل الوقف للدخول)*\n"
                    f"🎯 *الهدف الثاني (TP2 - 1:2.8):* `${tp2:.4f}` (+{tp2_pct:.2f}%)\n"
                    f"💼 *حجم العقد المنفذ (10%):* `${trade_amount:.2f} USDT`\n"
                    f"🔢 *الصفقات النشطة بالمحفظة:* `{len(open_trades)}/{MAX_OPEN_TRADES}`\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 [عرض الشارت على Binance]({binance_link})\n"
                    f"📈 [عرض الشارت على TradingView]({tv_link})"
                )
                send_telegram(msg)

            time.sleep(0.15)
        except:
            pass

    last_scan_stats["below_ema"] = below_ema_c
    last_scan_stats["no_bos"] = no_bos_c
    last_scan_stats["low_vol"] = low_vol_c
    last_scan_stats["rsi_fail"] = rsi_fail_c
    last_scan_stats["total"] = len(SYMBOLS)
    return new_opened

# ========================================================
# 8. نقطة الانطلاق الرئيسية
# ========================================================
def main():
    bal = get_binance_balance()
    print("✅ تم تثبيت المحرك الدفاعي المطور بنجاح (درع البيتكوين + قاطع أمان المحفظة + فوليوم 130% + وقف منيع 2.2% إلى 3.5%)!")
    send_telegram(
        f"🛡️ *تم تفعيل درع حماية الأرباح وقاطع الأمان الفائق للمحفظة!* 🟢\n\n"
        f"💼 رصيد باينانس: `${bal:,.2f}` USDT (دخول 10% لكل صفقة).\n"
        f"1. 🛡️ *درع البيتكوين الصارم:* منع أي شراء إذا كان البيتكوين تحت EMA20 على فريم الساعة.\n"
        f"2. 🛑 *قاطع الأمان التلقائي (Circuit Breaker):* تجميد الشراء ساعتين عند حدوث خسارتين متتاليتين.\n"
        f"3. 🎯 *فوليوم مؤسساتي +130%:* لا دخول إلا في الاختراقات الحقيقية ذات السيولة الهائلة.\n"
        f"4. 🧱 *وقف خسارة منيع (2.2% - 3.5%):* عزل كامل ضد ذيول الشموع والضجيج السعري.\n"
        f"💬 أرسل كلمة (تقرير) لكشف الحساب أو (رادار) لنبض السوق في أي وقت!"
    )

    last_night_day = -1
    last_hourly_radar_hour = -1
    hourly_trades_count = 0

    while True:
        try:
            check_telegram_commands()
            track_open_trades()
            opened_now = scan_smc()
            hourly_trades_count += opened_now

            now = datetime.now()

            # إرسال رادار نبض السوق الساعي عند الدقيقة 2 من كل ساعة جديدة إذا لم تُفتح صفقات
            if now.hour != last_hourly_radar_hour and now.minute >= 2:
                if hourly_trades_count == 0:
                    send_hourly_market_radar()
                hourly_trades_count = 0
                last_hourly_radar_hour = now.hour

            # التقرير الليلي الشامل الساعة 23:00
            if now.hour == 23 and now.day != last_night_day:
                send_full_detailed_report()
                last_night_day = now.day

            time.sleep(40)
        except Exception as e:
            time.sleep(15)

if __name__ == "__main__":
    main()
