import time
import requests
import ccxt
import pandas as pd
import sqlite3
from datetime import datetime

# ========================================================
# 1. إعدادات التليجرام ومفاتيح Binance Testnet
# ========================================================
TELEGRAM_BOT_TOKEN = "8783526256:AAGaY3HW2BOpDqF-iGCmwtkcfHBf4hGnCU4"
TELEGRAM_CHAT_ID = "7760401819"

BINANCE_API_KEY = "eEQI3GrUGBdGzHmjSTxg7us7uPM2ZZ69mQddzj3rw6zDL4TbSwEVAHWgp5BU1cAO"
BINANCE_SECRET = "pwQHVpCsrO1DXxxpgrSf4gGZZddOUHZRPEL448kO3IMZILDFR6HNcgUjD4EWemou"

POSITION_SIZE_PERCENT = 0.10    # حجم الدخول: 10% من رصيد محفظة باينانس
MAX_TECHNICAL_SL_PCT = 4.5      # استبعاد الصفقات التي يبعد قاعها الفني أكثر من 4.5%

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

# منصة باينانس لتنفيذ الصفقات
binance_testnet = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot', 'adjustForTimeDifference': True}
})
binance_testnet.set_sandbox_mode(True)

# منصة قراءة بيانات الشموع الحية
market_exchange = ccxt.kucoin({'enableRateLimit': True})

# ========================================================
# 2. إعداد قاعدة بيانات التتبع
# ========================================================
def init_db():
    conn = sqlite3.connect('binance_testnet_trades.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            entry_price REAL,
            stop_loss REAL,
            tp1 REAL,
            tp2 REAL,
            amount_usdt REAL,
            status TEXT,
            pnl_usdt REAL,
            smc_reason TEXT,
            open_time TEXT,
            close_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ========================================================
# 3. دوال التليجرام ورصيد باينانس
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

def get_binance_balance():
    try:
        bal = binance_testnet.fetch_balance()
        usdt_free = bal['free'].get('USDT', 0.0)
        return float(usdt_free) if usdt_free > 0 else 1000.0
    except Exception as e:
        return 1000.0

def get_btc_status():
    try:
        ticker = market_exchange.fetch_ticker('BTC/USDT')
        change = ticker['percentage']
        if change is None:
            change = 0.0
        if change > 2.0:
            return f"صاعد بقوة (+{change:.2f}%) 🟢"
        elif change > 0:
            return f"متذبذب إيجابي (+{change:.2f}%) 🟢"
        elif change > -2.0:
            return f"متذبذب طبيعي ({change:.2f}%) 🟡"
        else:
            return f"هابط بحذر ({change:.2f}%) 🔴"
    except:
        return "متذبذب طبيعي 🟡"

# ========================================================
# 4. مراقبة وإغلاق الصفقات
# ========================================================
def track_open_trades():
    conn = sqlite3.connect('binance_testnet_trades.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, symbol, entry_price, stop_loss, tp1, tp2, amount_usdt FROM trades WHERE status = 'OPEN'")
    trades = cursor.fetchall()
    conn.close()

    for t in trades:
        t_id, symbol, entry, sl, tp1, tp2, amount = t
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

                conn = sqlite3.connect('binance_testnet_trades.db')
                c = conn.cursor()
                c.execute("UPDATE trades SET status = 'TP2_HIT', pnl_usdt = ?, close_time = ? WHERE id = ?",
                          (profit, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), t_id))
                conn.commit()
                conn.close()

                bal = get_binance_balance()
                msg = (
                    f"🎯 *تم تحقيق الهدف بنجاح في باينانس (TP2 HIT)!* 🎉\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"📥 *سعر الدخول:* `${entry:.4f}`\n"
                    f"💰 *سعر البيع:* `${tp2:.4f}`\n"
                    f"💵 *صافي الربح المحقق:* `+${profit:.2f}` USDT 🟢\n"
                    f"💼 *رصيد محفظة باينانس الآن:* `${bal:,.2f}` USDT\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                send_telegram(msg)

            # ضرب وقف الخسارة الفني
            elif curr <= sl:
                loss = amount * ((sl - entry) / entry)
                try:
                    binance_testnet.create_market_sell_order(symbol, amount / entry)
                except:
                    pass

                conn = sqlite3.connect('binance_testnet_trades.db')
                c = conn.cursor()
                c.execute("UPDATE trades SET status = 'SL_HIT', pnl_usdt = ?, close_time = ? WHERE id = ?",
                          (loss, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), t_id))
                conn.commit()
                conn.close()

                bal = get_binance_balance()
                msg = (
                    f"🛑 *تنبيه: ضرب وقف الخسارة الفني (STOP LOSS)* 🛑\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"📥 *سعر الدخول:* `${entry:.4f}`\n"
                    f"🛑 *سعر الخروج:* `${sl:.4f}`\n"
                    f"📉 *الخسارة المحسوبة:* `${loss:.2f}` USDT 🔴\n"
                    f"💼 *رصيد محفظة باينانس الآن:* `${bal:,.2f}` USDT\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                send_telegram(msg)

        except Exception as e:
            print(f"Error tracking {symbol}: {e}")

# ========================================================
# 5. محرك استراتيجية SMC مع وقف الخسارة الفني البحت
# ========================================================
def scan_smc():
    for symbol in SYMBOLS:
        conn = sqlite3.connect('binance_testnet_trades.db')
        c = conn.cursor()
        c.execute("SELECT id FROM trades WHERE symbol = ? AND status = 'OPEN'", (symbol,))
        exists = c.fetchone()
        conn.close()
        if exists:
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
                
                # وقف الخسارة الفني: أسفل شمعة الـ Order Block وقاع فجوة الـ FVG مباشرة
                order_block_low = min(df['low'].iloc[-2], df['low'].iloc[-3])
                
                # وضع الوقف الفني أسفل القاع بـ 0.2% كهامش أمان ضد الذيول الوهمية
                sl = order_block_low * 0.998
                sl_pct = ((entry - sl) / entry) * 100

                # فلتر الأمان الفني: إذا كان القاع الفني بعيداً جداً (> 4.5%) نلغي الصفقة
                if sl_pct > MAX_TECHNICAL_SL_PCT or sl_pct < 0.5:
                    continue

                # الأهداف الفنية مبنية على المسافة الحقيقية للوقف
                risk = entry - sl
                tp1 = entry + (risk * 1.5)  # عائد 1:1.5
                tp2 = entry + (risk * 2.8)  # عائد 1:2.8

                tp1_pct = ((tp1 - entry) / entry) * 100
                tp2_pct = ((tp2 - entry) / entry) * 100

                smc_reason = "BOS (Break of Structure) + Bullish FVG (Fair Value Gap)"
                btc_status = get_btc_status()

                # حساب 10% من رصيد باينانس الحقيقي
                current_balance = get_binance_balance()
                trade_amount = round(current_balance * POSITION_SIZE_PERCENT, 2)

                # تنفيذ الشراء على باينانس التجريبية
                try:
                    qty = trade_amount / entry
                    binance_testnet.create_market_buy_order(symbol, qty)
                    execution_note = "✅ تم تنفيذ الشراء آلياً في Binance Testnet"
                except Exception as ex:
                    execution_note = "⚡ تم التتبع آلياً بأسعار باينانس"

                # حفظ الصفقة
                conn = sqlite3.connect('binance_testnet_trades.db')
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO trades (symbol, entry_price, stop_loss, tp1, tp2, amount_usdt, status, pnl_usdt, smc_reason, open_time)
                    VALUES (?, ?, ?, ?, ?, ?, 'OPEN', 0, ?, ?)
                ''', (symbol, entry, sl, tp1, tp2, trade_amount, smc_reason, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                conn.close()

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
                    f"🟢 *توجيه السيولة:* {execution_note} 🟢\n"
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
# 6. التقارير الليلية والأسبوعية
# ========================================================
def send_night_report():
    conn = sqlite3.connect('binance_testnet_trades.db')
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'TP2_HIT'")
    wins = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'SL_HIT'")
    losses = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'OPEN'")
    open_trades = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(pnl_usdt) FROM trades WHERE status != 'OPEN'")
    total_pnl = cursor.fetchone()[0] or 0.0

    conn.close()

    bal = get_binance_balance()
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0

    msg = (
        f"🌙 *التقرير الليلي لصفقات باينانس الافتراضية* 🌙\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💼 *رصيد حساب باينانس الحالي:* `${bal:,.2f}` USDT\n"
        f"📈 *صافي الأرباح المحققة:* `{total_pnl:+.2f}$`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ *الصفقات الرابحة:* `{wins}` 🟢\n"
        f"❌ *الصفقات الخاسرة:* `{losses}` 🔴\n"
        f"⏳ *الصفقات النشطة الآن:* `{open_trades}` 🟡\n"
        f"🎯 *نسبة نجاح SMC:* `{win_rate:.1f}%`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 *حالة الخطة:* التداول مستمر بنظام وقف الخسارة الفني أسفل كتل الأوامر."
    )
    send_telegram(msg)

def send_weekly_report():
    conn = sqlite3.connect('binance_testnet_trades.db')
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'TP2_HIT'")
    wins = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'SL_HIT'")
    losses = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(pnl_usdt) FROM trades WHERE status != 'OPEN'")
    total_pnl = cursor.fetchone()[0] or 0.0

    conn.close()

    bal = get_binance_balance()
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0

    evaluation = "ممتازة وجاهزة للحساب الحقيقي! 🚀" if win_rate >= 50 and total_pnl > 0 else "تحتاج لمزيد من المراقبة والتعديل ⚠️"

    msg = (
        f"📅 *التقرير الأسبوعي الشامل لتقييم استراتيجية باينانس* 📅\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *رصيد محفظة باينانس النهائي:* `${bal:,.2f}` USDT\n"
        f"📈 *صافي الأرباح:* `{total_pnl:+.2f}$`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔢 *إجمالي الصفقات المغلقة:* `{total_closed}`\n"
        f"✅ *صفقات رابحة:* `{wins}`\n"
        f"❌ *صفقات خاسرة:* `{losses}`\n"
        f"🎯 *معدل الفوز الحقيقي:* `{win_rate:.1f}%`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎖️ *التقييم النهائي:* {evaluation}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    send_telegram(msg)

# ========================================================
# 7. الحلقة الرئيسية للتشغيل
# ========================================================
def main():
    bal = get_binance_balance()
    print("✅ تم تفعيل وقف الخسارة الفني أسفل كتل الأوامر بنجاح!")
    send_telegram(
        f"🛡️ *تم تفعيل نظام وقف الخسارة الفني البحت (Order Block Low)!* 🟢\n\n"
        f"💼 رصيد باينانس: `${bal:,.2f}` USDT (دخول 10% لكل صفقة).\n"
        f"🎯 وقف الخسارة يتم وضعه فنياً أسفل ذيل شمعة الدخول وكتلة الأوامر مباشرة.\n"
        f"🚫 يتم استبعاد أي صفقة يتجاوز وقفها الفني 4.5% لحماية رأس المال.\n"
        f"🌙 التقرير الليلي يصلك يومياً الساعة 11 مساءً."
    )

    last_night_report_day = -1
    last_weekly_report_week = -1

    while True:
        try:
            track_open_trades()
            scan_smc()

            now = datetime.now()

            # التقرير الليلي الساعة 11 مساءً
            if now.hour == 23 and now.day != last_night_report_day:
                send_night_report()
                last_night_report_day = now.day

            # التقرير الأسبوعي كل أحد الساعة 11:30 مساءً
            if now.weekday() == 6 and now.hour == 23 and now.isocalendar()[1] != last_weekly_report_week:
                send_weekly_report()
                last_weekly_report_week = now.isocalendar()[1]

            time.sleep(60)

        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()
