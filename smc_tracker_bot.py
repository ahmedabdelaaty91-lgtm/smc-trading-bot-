import time
import requests
import ccxt
import pandas as pd
import sqlite3
from datetime import datetime

# ========================================================
# 1. إعدادات التليجرام والمنصة والمحفظة التجريبية (10%)
# ========================================================
TELEGRAM_BOT_TOKEN = "8783526256:AAGaY3HW2BOpDqF-iGCmwtkcfHBf4hGnCU4"
TELEGRAM_CHAT_ID = "7760401819"

INITIAL_BALANCE = 1000.0        # رصيد المحفظة التجريبية الابتدائي
POSITION_SIZE_PERCENT = 0.10    # حجم كل صفقة: 10% من رصيد المحفظة الحالي

SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
    'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'SUI/USDT', 'LINK/USDT',
    'NEAR/USDT', 'APT/USDT', 'DOT/USDT', 'LTC/USDT', 'PEPE/USDT',
    'SHIB/USDT', 'TRX/USDT', 'ICP/USDT', 'FET/USDT', 'RENDER/USDT',
    'TIA/USDT', 'INJ/USDT', 'ARB/USDT', 'OP/USDT', 'UNI/USDT',
    'AAVE/USDT', 'STX/USDT', 'FIL/USDT', 'ATOM/USDT', 'SEI/USDT',
    'WIF/USDT', 'FLOKI/USDT', 'BONK/USDT', 'GALA/USDT', 'RUNE/USDT',
    'GRT/USDT', 'SAND/USDT', 'MANA/USDT', 'CHZ/USDT', 'ALGO/USDT',
    'XLM/USDT', 'HBAR/USDT', 'VET/USDT', 'EOS/USDT', 'CRV/USDT',
    'MKR/USDT', 'LDO/USDT', 'DYDX/USDT', 'FTM/USDT', 'ENA/USDT'
]

TIMEFRAME = '1h'

exchange = ccxt.kucoin({'enableRateLimit': True})

# ========================================================
# 2. إعداد قاعدة بيانات المحفظة والتتبع
# ========================================================
def init_db():
    conn = sqlite3.connect('paper_trading.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wallet (
            id INTEGER PRIMARY KEY,
            balance REAL,
            starting_balance REAL
        )
    ''')
    cursor.execute("SELECT COUNT(*) FROM wallet")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO wallet VALUES (1, ?, ?)", (INITIAL_BALANCE, INITIAL_BALANCE))

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            entry_price REAL,
            stop_loss REAL,
            tp1 REAL,
            tp2 REAL,
            amount_usdt REAL,
            status TEXT,          -- OPEN, TP1_HIT, TP2_HIT, SL_HIT
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
        ticker = exchange.fetch_ticker('BTC/USDT')
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

def get_wallet_balance():
    conn = sqlite3.connect('paper_trading.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance, starting_balance FROM wallet WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return row[0], row[1]

def update_wallet_balance(pnl_amount):
    conn = sqlite3.connect('paper_trading.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE wallet SET balance = balance + ? WHERE id = 1", (pnl_amount,))
    conn.commit()
    conn.close()

# ========================================================
# 4. مراقبة وإغلاق الصفقات التجريبية
# ========================================================
def track_open_trades():
    conn = sqlite3.connect('paper_trading.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, symbol, entry_price, stop_loss, tp1, tp2, amount_usdt FROM trades WHERE status = 'OPEN'")
    trades = cursor.fetchall()
    conn.close()

    for t in trades:
        t_id, symbol, entry, sl, tp1, tp2, amount = t
        try:
            ticker = exchange.fetch_ticker(symbol)
            curr = ticker['last']

            # تحقق الهدف الثاني TP2 (ربح كامل)
            if curr >= tp2:
                profit = amount * ((tp2 - entry) / entry)
                update_wallet_balance(profit)
                
                conn = sqlite3.connect('paper_trading.db')
                c = conn.cursor()
                c.execute("UPDATE trades SET status = 'TP2_HIT', pnl_usdt = ?, close_time = ? WHERE id = ?",
                          (profit, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), t_id))
                conn.commit()
                conn.close()

                bal, _ = get_wallet_balance()
                msg = (
                    f"🎯 *تم تحقيق الهدف بنجاح (TP HIT)!* 🎉\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"📥 *سعر الدخول:* `${entry:.4f}`\n"
                    f"💰 *سعر الخروج:* `${tp2:.4f}`\n"
                    f"💵 *صافي الربح:* `+${profit:.2f}` USDT 🟢\n"
                    f"💼 *رصيد المحفظة الآن:* `${bal:.2f}` USDT\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                send_telegram(msg)

            # ضرب وقف الخسارة
            elif curr <= sl:
                loss = amount * ((sl - entry) / entry)
                update_wallet_balance(loss)

                conn = sqlite3.connect('paper_trading.db')
                c = conn.cursor()
                c.execute("UPDATE trades SET status = 'SL_HIT', pnl_usdt = ?, close_time = ? WHERE id = ?",
                          (loss, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), t_id))
                conn.commit()
                conn.close()

                bal, _ = get_wallet_balance()
                msg = (
                    f"🛑 *تنبيه: ضرب وقف الخسارة (STOP LOSS)* 🛑\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"📥 *سعر الدخول:* `${entry:.4f}`\n"
                    f"🛑 *سعر الخروج:* `${sl:.4f}`\n"
                    f"📉 *الخسارة التجريبية:* `${loss:.2f}` USDT 🔴\n"
                    f"💼 *رصيد المحفظة الآن:* `${bal:.2f}` USDT\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                send_telegram(msg)

        except Exception as e:
            print(f"Error tracking {symbol}: {e}")

# ========================================================
# 5. محرك استراتيجية SMC وإرسال الإشارة (حجم 10%)
# ========================================================
def scan_smc():
    for symbol in SYMBOLS:
        conn = sqlite3.connect('paper_trading.db')
        c = conn.cursor()
        c.execute("SELECT id FROM trades WHERE symbol = ? AND status = 'OPEN'", (symbol,))
        exists = c.fetchone()
        conn.close()
        if exists:
            continue

        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=60)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            df['swing_high'] = df['high'][(df['high'] > df['high'].shift(1)) & (df['high'] > df['high'].shift(-1))]
            df['swing_low'] = df['low'][(df['low'] < df['low'].shift(1)) & (df['low'] < df['low'].shift(-1))]

            highs = df['swing_high'].dropna()
            lows = df['swing_low'].dropna()
            if len(highs) < 2 or len(lows) < 2:
                continue

            last_high = highs.iloc[-1]
            last_low = lows.iloc[-1]
            curr_price = df['close'].iloc[-1]
            c1_high = df['high'].iloc[-3]
            c3_low = df['low'].iloc[-1]

            is_bos = curr_price > last_high
            is_fvg = c3_low > c1_high

            if is_bos and is_fvg:
                entry = curr_price
                sl = last_low
                risk = entry - sl
                
                tp1 = entry + (risk * 1.5)
                tp2 = entry + (risk * 2.8)

                sl_pct = ((entry - sl) / entry) * 100
                tp1_pct = ((tp1 - entry) / entry) * 100
                tp2_pct = ((tp2 - entry) / entry) * 100

                smc_reason = "BOS (Break of Structure) + Bullish FVG (Fair Value Gap)"
                btc_status = get_btc_status()

                # حساب حجم العقد ديناميكياً = 10% من رصيد المحفظة الحالي
                curr_balance, _ = get_wallet_balance()
                trade_amount = round(curr_balance * POSITION_SIZE_PERCENT, 2)

                # تسجيل الصفقة التجريبية
                conn = sqlite3.connect('paper_trading.db')
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO trades (symbol, entry_price, stop_loss, tp1, tp2, amount_usdt, status, pnl_usdt, smc_reason, open_time)
                    VALUES (?, ?, ?, ?, ?, ?, 'OPEN', 0, ?, ?)
                ''', (symbol, entry, sl, tp1, tp2, trade_amount, smc_reason, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                conn.close()

                # روابط الشارت المباشرة
                coin_base = symbol.split('/')[0]
                binance_link = f"https://www.binance.com/en/trade/{coin_base}_USDT"
                tv_link = f"https://www.tradingview.com/chart/?symbol=BINANCE:{coin_base}USDT"

                msg = (
                    f"🚀 *إشارة تداول تجريبية جديدة!* 🟢\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"⏰ *فريم الإشارة:* `{TIMEFRAME}`\n"
                    f"🎯 *الاستراتيجية:* SMC - مفاهيم الأموال الذكية 🧠\n"
                    f"🌟 *تصنيف الصفقة:* صفقة كبرى (+A) 🌟\n"
                    f"📌 *التأكيد الفني:* كسر هيكل صاعد مع فجوة سيولة\n"
                    f"🔍 *السبب الفني:* `{smc_reason}`\n"
                    f"🟢 *توجيه السيولة:* استثمار آمن وممتاز 🟢\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💵 *سعر الدخول:* `${entry:.4f}`\n"
                    f"🛡️ *قاع الدعم (Swing Low):* `${sl:.4f}`\n"
                    f"🛑 *وقف الخسارة:* `${sl:.4f}` (-{sl_pct:.2f}%)\n"
                    f"🎯 *الهدف الأول (TP1):* `${tp1:.4f}` (+{tp1_pct:.2f}%)\n"
                    f"🎯 *الهدف الثاني (TP2):* `${tp2:.4f}` (+{tp2_pct:.2f}%)\n"
                    f"💼 *حجم العقد التجريبي (10%):* `${trade_amount:.2f} USDT`\n"
                    f"🌐 *سوق البيتكوين:* {btc_status}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 [عرض الشارت على Binance]({binance_link})\n"
                    f"📈 [عرض الشارت على TradingView]({tv_link})"
                )
                send_telegram(msg)

            time.sleep(0.3)

        except Exception as e:
            print(f"Error scanning {symbol}: {e}")

# ========================================================
# 6. التقارير الليلية والأسبوعية
# ========================================================
def send_night_report():
    conn = sqlite3.connect('paper_trading.db')
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

    bal, start_bal = get_wallet_balance()
    roi = ((bal - start_bal) / start_bal) * 100
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0

    msg = (
        f"🌙 *التقرير الليلي لصفقات التداول التجريبي* 🌙\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💼 *رصيد المحفظة الحالي:* `${bal:.2f}` USDT\n"
        f"📈 *العائد الكلي (ROI):* `{roi:+.2f}%` ({total_pnl:+.2f}$)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ *الصفقات الرابحة:* `{wins}` 🟢\n"
        f"❌ *الصفقات الخاسرة:* `{losses}` 🔴\n"
        f"⏳ *الصفقات النشطة الآن:* `{open_trades}` 🟡\n"
        f"🎯 *نسبة نجاح SMC:* `{win_rate:.1f}%`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 *حالة الخطة:* النظام يواصل اختبار الصفقات بدقة في السحابة."
    )
    send_telegram(msg)

def send_weekly_report():
    conn = sqlite3.connect('paper_trading.db')
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'TP2_HIT'")
    wins = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'SL_HIT'")
    losses = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(pnl_usdt) FROM trades WHERE status != 'OPEN'")
    total_pnl = cursor.fetchone()[0] or 0.0

    conn.close()

    bal, start_bal = get_wallet_balance()
    roi = ((bal - start_bal) / start_bal) * 100
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0

    evaluation = "ممتازة وجاهزة للحساب الحقيقي! 🚀" if win_rate >= 50 and roi > 0 else "تحتاج لمزيد من المراقبة والتعديل ⚠️"

    msg = (
        f"📅 *التقرير الأسبوعي الشامل لتقييم الاستراتيجية* 📅\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💼 *الرصيد الابتدائي:* `${start_bal:.2f}` USDT\n"
        f"💰 *الرصيد النهائي:* `${bal:.2f}` USDT\n"
        f"📈 *صافي الأرباح:* `{total_pnl:+.2f}$` ({roi:+.2f}%)\n"
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
    print("✅ تم تشغيل بوت التداول التجريبي الآلي SMC بنجاح (10% لكل صفقة)!")
    send_telegram(
        "🚀 *تم تفعيل نظام التداول التجريبي الآلي SMC (10% لكل صفقة)!* 🟢\n\n"
        "💼 حجم الدخول محسوب تلقائياً = 10% من رصيد المحفظة.\n"
        "🌙 التقرير الليلي يصلك يومياً الساعة 11 مساءً.\n"
        "📅 التقرير الأسبوعي الشامل يصلك مساء كل أحد لتقييم النتائج بدقة."
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
