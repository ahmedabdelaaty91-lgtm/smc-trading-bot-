import time
import requests
import ccxt
import pandas as pd
import sqlite3
from datetime import datetime

# ========================================================
# 1. إعدادات التليجرام وقائمة الـ 50 عملة
# ========================================================
TELEGRAM_BOT_TOKEN = "8783526256:AAGaY3HW2BOpDqF-iGCmwtkcfHBf4hGnCU4"
TELEGRAM_CHAT_ID = "7760401819"

# أقوى 50 عملة سيولة على باينانس و كوكوين
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

exchange = ccxt.kucoin({
    'enableRateLimit': True
})

# ========================================================
# 2. قاعدة بيانات تتبع صفقات السبوت
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
            status TEXT,
            pnl_r REAL,
            open_time TEXT,
            close_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ========================================================
# 3. إرسال الرسائل إلى التليجرام
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
# 4. إدارة صفقات السبوت
# ========================================================
def add_trade(symbol, entry, sl, tp):
    conn = sqlite3.connect('trades_journal.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (symbol, direction, entry_price, stop_loss, take_profit, status, pnl_r, open_time)
        VALUES (?, 'BUY', ?, ?, ?, 'OPEN', 0, ?)
    ''', (symbol, entry, sl, tp, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
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
# 5. متابعة صفقات الشراء المفتوحة (هل وصلت للهدف أم الوقف؟)
# ========================================================
def track_open_trades():
    conn = sqlite3.connect('trades_journal.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, symbol, entry_price, stop_loss, take_profit FROM trades WHERE status = 'OPEN'")
    open_trades = cursor.fetchall()
    conn.close()

    for trade in open_trades:
        trade_id, symbol, entry, sl, tp = trade
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']

            # تحقق الهدف
            if current_price >= tp:
                update_trade_result(trade_id, 'WIN', 3.0)
                msg = (
                    f"🎉 *مبروك! تحقق الهدف بنجاح (SPOT TAKE PROFIT)* 🎉\n\n"
                    f"🪙 *العملة:* `{symbol}`\n"
                    f"📥 *سعر الشراء:* `{entry}`\n"
                    f"💰 *سعر البيع الحالي:* `{tp}`\n"
                    f"📈 *الربح المحقق:* `+3R` (نسبة ممتازة)\n\n"
                    f"يمكنك جني الأرباح وبيع العملة الآن."
                )
                send_telegram(msg)

            # كسر وقف الخسارة
            elif current_price <= sl:
                update_trade_result(trade_id, 'LOSS', -1.0)
                msg = (
                    f"🛑 *تنبيه وقف خسارة سبوت (STOP LOSS)* 🛑\n\n"
                    f"🪙 *العملة:* `{symbol}`\n"
                    f"📥 *سعر الشراء:* `{entry}`\n"
                    f"🛑 *سعر الخروج:* `{sl}`\n"
                    f"📉 *النتيجة:* `-1R`\n\n"
                    f"يُفضل الخروج لحماية رأس المال وإعادة الدخول من قاع أفضل."
                )
                send_telegram(msg)

        except Exception as e:
            print(f"Error checking trade #{trade_id}: {e}")

# ========================================================
# 6. إرسال تقرير الأداء اليومي الشامل للسبوت
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
        f"📊 *تقرير أداء صفقات السبوت (SMC SPOT)* 📊\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔢 *إجمالي الصفقات المنتهية:* `{total_closed}`\n"
        f"✅ *الصفقات الرابحة:* `{wins}` 🟢\n"
        f"❌ *الصفقات الخاسرة:* `{losses}` 🔴\n"
        f"⏳ *الصفقات المستمرة حالياً:* `{active}` 🟡\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 *نسبة النجاح (Win Rate):* `{win_rate:.1f}%`\n"
        f"💰 *صافي الأرباح:* `{total_r:+.1f}R`\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    send_telegram(report)

# ========================================================
# 7. فحص السوق لاكتشاف فرص الشراء فقط (BUY ONLY)
# ========================================================
def scan_smc():
    for symbol in SYMBOLS:
        if has_open_trade(symbol):
            continue

        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=60)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # تحديد القمم والقيعان
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

            # شرط الشراء السبوت: كسر هيكل صاعد (BOS/CHoCH) + فجوة FVG شرائية
            if curr_price > last_high and c3_low > c1_high:
                entry = curr_price
                sl = last_low
                risk = entry - sl
                
                # أهداف بيع السبوت بربح
                tp1 = entry + (risk * 2)   # هدف أول (1:2)
                tp2 = entry + (risk * 3.5) # هدف ثانٍ رئيسي (1:3.5)

                add_trade(symbol, entry, sl, tp2)
                msg = (
                    f"🟢 *إشارة شراء سبوت جديدة (SPOT BUY)* 🟢\n\n"
                    f"🪙 *العملة:* `{symbol}`\n"
                    f"⏰ *الفريم:* `{TIMEFRAME}`\n\n"
                    f"✅ *السبب:* كسر هيكل صاعد (BOS) مع فجوة سيولة (FVG)\n\n"
                    f"📥 *سعر الشراء المقترح:* `{entry:.4f}`\n"
                    f"🛑 *وقف الخسارة:* `{sl:.4f}`\n"
                    f"🎯 *الهدف الأول (بيع نصف الكمية):* `{tp1:.4f}`\n"
                    f"💰 *الهدف الثاني (بيع باقي الكمية):* `{tp2:.4f}`\n\n"
                    f"⚡ *البوت بدأ تتبع هذه الصفقة وسيخبرك عند الوصول للأهداف.*"
                )
                send_telegram(msg)

            time.sleep(0.3)

        except Exception as e:
            print(f"Error scanning {symbol}: {e}")

# ========================================================
# 8. التشغيل المستمر
# ========================================================
def main():
    print("✅ تم تشغيل بوت السبوت بنجاح (شراء فقط)!")
    send_telegram("🚀 *تم تحديث البوت لنظام السبوت الفوري (SPOT ONLY)! سيبحث الآن عن أقوى صفقات الشراء فقط.*")
    
    last_report_time = time.time()

    while True:
        try:
            track_open_trades()
            scan_smc()

            if time.time() - last_report_time > 86400:
                send_summary_report()
                last_report_time = time.time()

            time.sleep(60)

        except Exception as e:
            print(f"خطأ في الدورة العامة: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()
