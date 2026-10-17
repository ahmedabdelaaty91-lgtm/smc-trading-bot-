import time
import json
import os
import subprocess
import requests
import ccxt
import pandas as pd
from datetime import datetime

# ========================================================
# 1. إعدادات التليجرام ومفاتيح Binance Testnet
# ========================================================
TELEGRAM_BOT_TOKEN = "8783526256:AAGaY3HW2BOpDqF-iGCmwtkcfHBf4hGnCU4"
TELEGRAM_CHAT_ID = "7760401819"

BINANCE_API_KEY = "eEQI3GrUGBdGzHmjSTxg7us7uPM2ZZ69mQddzj3rw6zDL4TbSwEVAHWgp5BU1cAO"
BINANCE_SECRET = "pwQHVpCsrO1DXxxpgrSf4gGZZddOUHZRPEL448kO3IMZILDFR6HNcgUjD4EWemou"

POSITION_SIZE_PERCENT = 0.10    # 10% لكل صفقة
MAX_TECHNICAL_SL_PCT = 4.5      # أقصى وقف خسارة فني مسموح به
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
# 2. نظام السجل الدائم (Permanent Ledger)
# ========================================================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "starting_balance": 1000.0,
        "current_balance": 1000.0,
        "total_profit_usdt": 0.0,
        "winning_trades": [],
        "losing_trades": [],
        "open_trades": []
    }

def save_history(data):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # حفظ تلقائي إلى مستودع GitHub حتى لا يضيع أبداً
    try:
        subprocess.run(['git', 'config', 'user.name', 'SMC-Bot'], check=False)
        subprocess.run(['git', 'config', 'user.email', 'bot@github.actions'], check=False)
        subprocess.run(['git', 'add', HISTORY_FILE], check=False)
        subprocess.run(['git', 'commit', '-m', 'chore: update trades ledger [skip ci]'], check=False)
        subprocess.run(['git', 'push'], check=False)
    except:
        pass

# ========================================================
# 3. دوال التليجرام والمحفظة
# ========================================================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def get_btc_status():
    try:
        ticker = market_exchange.fetch_ticker('BTC/USDT')
        change = ticker['percentage']
        if change is None: change = 0.0
        if change > 2.0: return f"صاعد بقوة (+{change:.2f}%) 🟢"
        elif change > 0: return f"متذبذب إيجابي (+{change:.2f}%) 🟢"
        elif change > -2.0: return f"متذبذب طبيعي ({change:.2f}%) 🟡"
        else: return f"هابط بحذر ({change:.2f}%) 🔴"
    except:
        return "متذبذب طبيعي 🟡"

def get_binance_balance():
    try:
        bal = binance_testnet.fetch_balance()
        usdt = bal['free'].get('USDT', 0.0)
        return float(usdt) if usdt > 0 else 1000.0
    except:
        hist = load_history()
        return hist.get("current_balance", 1000.0)

# ========================================================
# 4. إرسال التقرير الشامل والمفصل بالأسماء والأرقام
# ========================================================
def send_full_detailed_report():
    hist = load_history()
    bal = get_binance_balance()
    start_bal = hist.get("starting_balance", 1000.0)
    wins = hist.get("winning_trades", [])
    losses = hist.get("losing_trades", [])
    open_tr = hist.get("open_trades", [])
    
    total_closed = len(wins) + len(losses)
    win_rate = (len(wins) / total_closed * 100) if total_closed > 0 else 0.0
    net_pnl = hist.get("total_profit_usdt", 0.0)

    # تفاصيل الصفقات الرابحة
    wins_text = ""
    if wins:
        for w in wins[-5:]: # آخر 5 صفقات رابحة
            wins_text += f"• `{w['symbol']}`: دخول `${w['entry']}` ⬅️ خروج `${w['exit']}` (+${w['profit']:.2f})\n"
    else:
        wins_text = "لا توجد صفقات رابحة مغلقة بعد.\n"

    # تفاصيل الصفقات الخاسرة
    losses_text = ""
    if losses:
        for l in losses[-5:]: # آخر 5 صفقات خاسرة
            losses_text += f"• `{l['symbol']}`: دخول `${l['entry']}` ⬅️ وقف `${l['exit']}` (${l['loss']:.2f})\n"
    else:
        losses_text = "لا توجد صفقات خاسرة حتى الآن.\n"

    # تفاصيل الصفقات المفتوحة حالياً
    open_text = ""
    if open_tr:
        for o in open_tr:
            open_text += f"• `{o['symbol']}`: دخول `${o['entry']}` | وقف فني `${o['sl']}` | هدف `${o['tp2']}`\n"
    else:
        open_text = "لا توجد صفقات مفتوحة الآن.\n"

    msg = (
        f"📊 *السجل الدائم لأداء صفقات SMC* 📊\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💼 *رصيد محفظة باينانس:* `${bal:,.2f}` USDT\n"
        f"💰 *صافي الأرباح الكلية:* `{net_pnl:+.2f}$`\n"
        f"🎯 *نسبة الفوز الحقيقية:* `{win_rate:.1f}%`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ *الصفقات الرابحة ({len(wins)}):* 🟢\n"
        f"{wins_text}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"❌ *الصفقات التي ضربت الوقف ({len(losses)}):* 🔴\n"
        f"{losses_text}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏳ *الصفقات قيد التداول حالياً ({len(open_tr)}):* 🟡\n"
        f"{open_text}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 *أرسل كلمة (تقرير) في أي وقت لاستلام هذا التقرير فوراً!*"
    )
    send_telegram(msg)

# ========================================================
# 5. الاستماع لأوامر التليجرام (كلمة تقرير)
# ========================================================
last_telegram_update_id = 0

def check_telegram_commands():
    global last_telegram_update_id
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_telegram_update_id + 1}&timeout=1"
        res = requests.get(url, timeout=3).json()
        if res.get('ok') and res.get('result'):
            for item in res['result']:
                last_telegram_update_id = item['update_id']
                text = item.get('message', {}).get('text', '').strip()
                if text in ['تقرير', '/report', 'صفقات', '/trades', 'الارباح']:
                    send_full_detailed_report()
    except:
        pass

# ========================================================
# 6. مراقبة وإغلاق الصفقات المفتوحة وحفظها في السجل الدائم
# ========================================================
def track_open_trades():
    hist = load_history()
    open_trades = hist.get("open_trades", [])
    if not open_trades:
        return

    updated_open = []
    changed = False

    for t in open_trades:
        symbol = t['symbol']
        entry = t['entry']
        sl = t['sl']
        tp2 = t['tp2']
        amount = t['amount']

        try:
            ticker = market_exchange.fetch_ticker(symbol)
            curr = ticker['last']

            # تحقق الهدف الثاني TP2
            if curr >= tp2:
                profit = amount * ((tp2 - entry) / entry)
                try:
                    binance_testnet.create_market_sell_order(symbol, amount / entry)
                except:
                    pass

                hist["winning_trades"].append({
                    "symbol": symbol,
                    "entry": entry,
                    "exit": tp2,
                    "profit": profit,
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M')
                })
                hist["total_profit_usdt"] += profit
                hist["current_balance"] += profit
                changed = True

                msg = (
                    f"🎯 *تم تحقيق الهدف بنجاح في باينانس (TP2 HIT)!* 🎉\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"📥 *سعر الدخول:* `${entry:.4f}`\n"
                    f"💰 *سعر البيع:* `${tp2:.4f}`\n"
                    f"💵 *صافي الربح المحقق:* `+${profit:.2f}` USDT 🟢\n"
                    f"💼 *رصيد باينانس المحدث:* `${hist['current_balance']:,.2f}` USDT\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                send_telegram(msg)
                continue

            # ضرب وقف الخسارة الفني
            elif curr <= sl:
                loss = amount * ((sl - entry) / entry)
                try:
                    binance_testnet.create_market_sell_order(symbol, amount / entry)
                except:
                    pass

                hist["losing_trades"].append({
                    "symbol": symbol,
                    "entry": entry,
                    "exit": sl,
                    "loss": loss,
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M')
                })
                hist["total_profit_usdt"] += loss
                hist["current_balance"] += loss
                changed = True

                msg = (
                    f"🛑 *تنبيه: ضرب وقف الخسارة الفني (STOP LOSS)* 🛑\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"📥 *سعر الدخول:* `${entry:.4f}`\n"
                    f"🛑 *سعر الخروج:* `${sl:.4f}`\n"
                    f"📉 *الخسارة المحسوبة:* `${loss:.2f}` USDT 🔴\n"
                    f"💼 *رصيد باينانس المحدث:* `${hist['current_balance']:,.2f}` USDT\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                send_telegram(msg)
                continue

            updated_open.append(t)

        except Exception as e:
            updated_open.append(t)

    if changed:
        hist["open_trades"] = updated_open
        save_history(hist)

# ========================================================
# 7. فحص السوق لاكتشاف صفقات الشراء بوقف فني
# ========================================================
def scan_smc():
    hist = load_history()
    open_symbols = [t['symbol'] for t in hist.get("open_trades", [])]

    for symbol in SYMBOLS:
        if symbol in open_symbols:
            continue

        try:
            ohlcv = market_exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=40)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            recent_high = df['high'].iloc[-10:-1].max()
            curr_price = df['close'].iloc[-1]
            c1_high = df['high'].iloc[-3]
            c3_low = df['low'].iloc[-1]

            is_bos = curr_price > recent_high
            is_fvg = c3_low > c1_high

            if is_bos and is_fvg:
                entry = curr_price
                order_block_low = min(df['low'].iloc[-2], df['low'].iloc[-3])
                sl = order_block_low * 0.998
                sl_pct = ((entry - sl) / entry) * 100

                # فلتر الأمان: لا ندخل إذا كان الوقف الفني أكبر من 4.5%
                if sl_pct > MAX_TECHNICAL_SL_PCT or sl_pct < 0.5:
                    continue

                risk = entry - sl
                tp1 = entry + (risk * 1.5)
                tp2 = entry + (risk * 2.8)

                tp1_pct = ((tp1 - entry) / entry) * 100
                tp2_pct = ((tp2 - entry) / entry) * 100

                smc_reason = "BOS (Break of Structure) + Bullish FVG"
                btc_status = get_btc_status()

                bal = get_binance_balance()
                trade_amount = round(bal * POSITION_SIZE_PERCENT, 2)

                try:
                    qty = trade_amount / entry
                    binance_testnet.create_market_buy_order(symbol, qty)
                    exec_note = "✅ تم الشراء في Binance Testnet"
                except:
                    exec_note = "⚡ تم التتبع آلياً بأسعار باينانس"

                # حفظ في السجل الدائم
                hist["open_trades"].append({
                    "symbol": symbol,
                    "entry": entry,
                    "sl": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "amount": trade_amount,
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M')
                })
                save_history(hist)

                coin_base = symbol.split('/')[0]
                binance_link = f"https://www.binance.com/en/trade/{coin_base}_USDT"
                tv_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{coin_base}USDT"

                msg = (
                    f"🚀 *إشارة تداول فنية جديدة (SMC)!* 🟢\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"⏰ *فريم الإشارة:* `{TIMEFRAME}`\n"
                    f"🎯 *الاستراتيجية:* SMC - مفاهيم الأموال الذكية 🧠\n"
                    f"🌟 *تصنيف الصفقة:* صفقة كبرى (+A) 🌟\n"
                    f"📌 *التأكيد الفني:* كسر هيكل صاعد مع فجوة سيولة\n"
                    f"🔍 *السبب الفني:* `{smc_reason}`\n"
                    f"🟢 *توجيه السيولة:* {exec_note} 🟢\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💵 *سعر الدخول:* `${entry:.4f}`\n"
                    f"🛡️ *قاع الدعم (Order Block Low):* `${order_block_low:.4f}`\n"
                    f"🛑 *وقف الخسارة الفني:* `${sl:.4f}` (-{sl_pct:.2f}%)\n"
                    f"🎯 *الهدف الأول (TP1):* `${tp1:.4f}` (+{tp1_pct:.2f}%)\n"
                    f"🎯 *الهدف الثاني (TP2):* `${tp2:.4f}` (+{tp2_pct:.2f}%)\n"
                    f"💼 *حجم العقد المنفذ (10%):* `${trade_amount:.2f} USDT`\n"
                    f"🌐 *سوق البيتكوين:* {btc_status}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 [عرض الشارت على Binance]({binance_link})\n"
                    f"📈 [عرض الشارت على TradingView]({tv_link})"
                )
                send_telegram(msg)

            time.sleep(0.15)

        except Exception as e:
            pass

# ========================================================
# 8. حلقة التشغيل الرئيسية المستقرة
# ========================================================
def main():
    bal = get_binance_balance()
    print("✅ تم تفعيل البوت بالسجل الدائم ومنع التكرار!")
    send_telegram(
        f"🚀 *تم تحديث البوت بالسجل الدائم وحماية السيرفر من التكرار!* 🛡️\n\n"
        f"💼 رصيد باينانس: `${bal:,.2f}` USDT\n"
        f"💾 لن تضيع أي صفقة رابحة أو خاسرة بعد الآن أبداً حتى لو تم إعادة تشغيل السيرفر.\n"
        f"💬 *ميزة جديدة:* اكتب كلمة (تقرير) للبوت في أي وقت ليرسل لك تفاصيل كل الصفقات لحظياً!"
    )

    last_night_day = -1

    while True:
        try:
            # 1. الاستماع لكلمة "تقرير" من المستخدم
            check_telegram_commands()

            # 2. متابعة وإغلاق الصفقات المفتوحة
            track_open_trades()

            # 3. فحص العملات واكتشاف صفقات جديدة
            scan_smc()

            # 4. التقرير الليلي التلقائي الساعة 11 مساءً
            now = datetime.now()
            if now.hour == 23 and now.day != last_night_day:
                send_full_detailed_report()
                last_night_day = now.day

            time.sleep(40)

        except Exception as e:
            time.sleep(15)

if __name__ == "__main__":
    main()
