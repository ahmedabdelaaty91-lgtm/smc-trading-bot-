import time
import requests
import ccxt
import pandas as pd
import sqlite3
from datetime import datetime

# ========================================================
# 1. إعدادات التليجرام والـ 50 عملة المختارة بعناية
# ========================================================
TELEGRAM_BOT_TOKEN = "8783526256:AAGaY3HW2BOpDqF-iGCmwtkcfHBf4hGnCU4"
TELEGRAM_CHAT_ID = "8744541280"

  
# قائمة أقوى 50 عملة في باينانس من حيث السيولة وحجم التداول
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

TIMEFRAME = '1h'  # فريم الساعة (الأفضل والأدق لصفقات SMC)

exchange = ccxt.binance({
    'enableRateLimit': True
})

# ========================================================
# 2. إعداد قاعدة بيانات محلية لحفظ وتتبع الصفقات
# ========================================================
def init_db():
    conn = sqlite3.connect('trades_journal.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            direction TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            status TEXT,          -- OPEN, WIN, LOSS
            pnl_r REAL,           -- ربح/خسارة بمضاعف المخاطرة (R)
            open_time TEXT,
            close_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ========================================================
# 3. دوال التليجرام
# ========================================================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

# ========================================================
# 4. إدارة الصفقات في قاعدة البيانات
# ========================================================
def add_trade(symbol, direction, entry, sl, tp):
    conn = sqlite3.connect('trades_journal.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (symbol, direction, entry_price, stop_loss, take_profit, status, pnl_r, open_time)
        VALUES (?, ?, ?, ?, ?, 'OPEN', 0, ?)
    ''', (symbol, direction, entry, sl, tp, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

def has_open_trade(symbol):
    conn = sqlite3.connect('trades_journal.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM trades WHERE symbol = ? AND status = 'OPEN'", (symbol,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def update_trade_result(trade_id, status, pnl_r):
    conn = sqlite3.connect('trades_journal.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE trades 
        SET status = ?, pnl_r = ?, close_time = ?
        WHERE id = ?
    ''', (status, pnl_r, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), trade_id))
    conn.commit()
    conn.close()

# ========================================================
# 5. مراقبة الصفقات المفتوحة (هل ضربت الهدف أم الوقف؟)
# ========================================================
def track_open_trades():
    conn = sqlite3.connect('trades_journal.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, symbol, direction, entry_price, stop_loss, take_profit FROM trades WHERE status = 'OPEN'")
    open_trades = cursor.fetchall()
    conn.close()

    for trade in open_trades:
        trade_id, symbol, direction, entry, sl, tp = trade
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']

            # حالة صفقة الشراء LONG
            if direction == 'LONG':
                if current_price >= tp:
                    update_trade_result(trade_id, 'WIN', 3.0)
                    msg = (
                        f"🎉 *مبروك! تحقق الهدف بنجاح (TAKE PROFIT)* 🎉\n\n"
                        f"🪙 *العملة:* `{symbol}` (LONG)\n"
                        f"🎯 *سعر الدخول:* `{entry}`\n"
                        f"💰 *سعر الهدف:* `{tp}`\n"
                        f"📈 *الربح المحقق:* `+3R` (3 أضعاف المخاطرة)\n\n"
                        f"تم تسجيل الصفقة رابحة في التقرير."
                    )
                    send_telegram(msg)

                elif current_price <= sl:
                    update_trade_result(trade_id, 'LOSS', -1.0)
                    msg = (
                        f"🛑 *ضرب وقف الخسارة (STOP LOSS)* 🛑\n\n"
                        f"🪙 *العملة:* `{symbol}` (LONG)\n"
                        f"🎯 *سعر الدخول:* `{entry}`\n"
                        f"🛑 *وقف الخسارة:* `{sl}`\n"
                        f"📉 *النتيجة:* `-1R`\n\n"
                        f"تم تسجيل الصفقة خاسرة في التقرير."
                    )
                    send_telegram(msg)

            # حالة صفقة البيع SHORT
            elif direction == 'SHORT':
                if current_price <= tp:
                    update_trade_result(trade_id, 'WIN', 3.0)
                    msg = (
                        f"🎉 *مبروك! تحقق الهدف بنجاح (TAKE PROFIT)* 🎉\n\n"
                        f"🪙 *العملة:* `{symbol}` (SHORT)\n"
                        f"🎯 *سعر الدخول:* `{entry}`\n"
                        f"💰 *سعر الهدف:* `{tp}`\n"
                        f"📈 *الربح المحقق:* `+3R`\n\n"
                        f"تم تسجيل الصفقة رابحة في التقرير."
                    )
                    send_telegram(msg)

                elif current_price >= sl:
                    update_trade_result(trade_id, 'LOSS', -1.0)
                    msg = (
                        f"🛑 *ضرب وقف الخسارة (STOP LOSS)* 🛑\n\n"
                        f"🪙 *العملة:* `{symbol}` (SHORT)\n"
                        f"🎯 *سعر الدخول:* `{entry}`\n"
                        f"🛑 *وقف الخسارة:* `{sl}`\n"
                        f"📉 *النتيجة:* `-1R`\n\n"
                        f"تم تسجيل الصفقة خاسرة في التقرير."
                    )
                    send_telegram(msg)

        except Exception as e:
            print(f"Error checking trade #{trade_id}: {e}")

# ========================================================
# 6. إرسال تقرير الأداء الشامل
# ========================================================
def send_summary_report():
    conn = sqlite3.connect('trades_journal.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM trades WHERE status != 'OPEN'")
    total_closed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'WIN'")
    wins = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'LOSS'")
    losses = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(pnl_r) FROM trades WHERE status != 'OPEN'")
    total_r = cursor.fetchone()[0] or 0.0

    cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'OPEN'")
    active = cursor.fetchone()[0]

    conn.close()

    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0

    report = (
        f"📊 *تقرير أداء صفقات SMC المحدث (50 عملة)* 📊\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔢 *إجمالي الصفقات المنتهية:* `{total_closed}`\n"
        f"✅ *الصفقات الرابحة:* `{wins}` 🟢\n"
        f"❌ *الصفقات الخاسرة:* `{losses}` 🔴\n"
        f"⏳ *الصفقات المفتوحة حالياً:* `{active}` 🟡\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 *نسبة النجاح (Win Rate):* `{win_rate:.1f}%`\n"
        f"💰 *صافي الأرباح (Net R):* `{total_r:+.1f}R`\n"
        f"*(ملاحظة: إذا كنت تخاطر بـ 1% لكل صفقة، فأنت ربحت {total_r:+.1f}% صافي)*\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    send_telegram(report)

# ========================================================
# 7. محرك استراتيجية SMC لاكتشاف الفرص
# ========================================================
def scan_smc():
    for symbol in SYMBOLS:
        if has_open_trade(symbol):
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

            # فرصة شراء LONG
            if curr_price > last_high and c3_low > c1_high:
                entry = curr_price
                sl = last_low
                risk = entry - sl
                tp = entry + (risk * 3)

                add_trade(symbol, 'LONG', entry, sl, tp)
                msg = (
                    f"🚨 *إشارة دخول شراء (LONG - SMC)* 🚨\n\n"
                    f"🪙 *العملة:* `{symbol}`\n"
                    f"⏰ *الفريم:* `{TIMEFRAME}`\n\n"
                    f"📥 *نقطة الدخول:* `{entry:.4f}`\n"
                    f"🛑 *وقف الخسارة:* `{sl:.4f}`\n"
                    f"🎯 *الهدف (1:3):* `{tp:.4f}`\n\n"
                    f"⚡ *البوت بدأ تتبع هذه الصفقة تلقائياً وسيخبرك بالنتيجة.*"
                )
                send_telegram(msg)

            # فرصة بيع SHORT
            elif curr_price < last_low:
                entry = curr_price
                sl = last_high
                risk = sl - entry
                tp = entry - (risk * 3)

                add_trade(symbol, 'SHORT', entry, sl, tp)
                msg = (
                    f"🚨 *إشارة دخول بيع (SHORT - SMC)* 🚨\n\n"
                    f"🪙 *العملة:* `{symbol}`\n"
                    f"⏰ *الفريم:* `{TIMEFRAME}`\n\n"
                    f"📥 *نقطة الدخول:* `{entry:.4f}`\n"
                    f"🛑 *وقف الخسارة:* `{sl:.4f}`\n"
                    f"🎯 *الهدف (1:3):* `{tp:.4f}`\n\n"
                    f"⚡ *البوت بدأ تتبع هذه الصفقة تلقائياً وسيخبرك بالنتيجة.*"
                )
                send_telegram(msg)

            # فاصل زمني صغير لحماية الاتصال من الضغط
            time.sleep(0.2)

        except Exception as e:
            print(f"Error scanning {symbol}: {e}")

# ========================================================
# 8. التشغيل المستمر
# ========================================================
def main():
    print("✅ تم تشغيل البوت بنجاح لمراقبة أقوى 50 عملة!")
    send_telegram("🚀 *تم تفعيل البوت لمراقبة أقوى 50 عملة بنجاح! نظام التتبع والتقارير يعمل الآن 24/7.*")
    
    last_report_time = time.time()

    while True:
        try:
            # 1. متابعة الصفقات الحالية هل ضربت الهدف أو الوقف
            track_open_trades()

            # 2. فحص الـ 50 عملة بحثاً عن صفقات SMC
            scan_smc()

            # 3. إرسال تقرير شامل تلقائياً كل 24 ساعة
            if time.time() - last_report_time > 86400:
                send_summary_report()
                last_report_time = time.time()

            # الانتظار 60 ثانية قبل الدورة التالية
            time.sleep(60)

        except Exception as e:
            print(f"خطأ في الدورة العامة: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()
