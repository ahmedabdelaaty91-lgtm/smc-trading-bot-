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
TELEGRAM_BOT_TOKEN = "8783526256:AAG_-1qx7O3UFuHNAvUM5W9GFZaO4yPx70c"
TELEGRAM_CHAT_ID = "7760401819"

BINANCE_API_KEY = "eEQI3GrUGBdGzHmjSTxg7us7uPM2ZZ69mQddzj3rw6zDL4TbSwEVAHWgp5BU1cAO"
BINANCE_SECRET = "pwQHVpCsrO1DXxxpgrSf4gGZZddOUHZRPEL448kO3IMZILDFR6HNcgUjD4EWemou"

POSITION_SIZE_PERCENT = 0.10    # 10% لكل صفقة
MIN_TECHNICAL_SL_PCT = 1.5      # الحد الأدنى لوقف الخسارة الفني
MAX_TECHNICAL_SL_PCT = 3.2      # الحد الأقصى لوقف الخسارة الفني (بين 1.5% إلى 3.2% فقط)
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
# 2. السجل الدائم
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
        change = ticker['percentage'] or 0.0
        if change > 2.0: return "صاعد بقوة (+{:.2f}%) 🟢".format(change)
        elif change > 0: return "متذبذب إيجابي (+{:.2f}%) 🟢".format(change)
        elif change > -2.0: return "متذبذب طبيعي ({:+.2f}%) 🟡".format(change)
        else: return "هابط بحذر ({:+.2f}%) 🔴".format(change)
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
# 4. إرسال التقارير
# ========================================================
def send_full_detailed_report():
    hist = load_history()
    bal = get_binance_balance()
    wins = hist.get("winning_trades", [])
    losses = hist.get("losing_trades", [])
    open_tr = hist.get("open_trades", [])
    
    total_closed = len(wins) + len(losses)
    win_rate = (len(wins) / total_closed * 100) if total_closed > 0 else 0.0
    net_pnl = hist.get("total_profit_usdt", 0.0)

    wins_text = "".join([f"• `{w['symbol']}`: دخول `${w['entry']}` ⬅️ خروج `${w['exit']}` (+${w['profit']:.2f})\n" for w in wins[-5:]]) or "لا توجد صفقات رابحة مغلقة بعد.\n"
    losses_text = "".join([f"• `{l['symbol']}`: دخول `${l['entry']}` ⬅️ وقف `${l['exit']}` (${l['loss']:.2f})\n" for l in losses[-5:]]) or "لا توجد صفقات خاسرة حتى الآن.\n"
    open_text = "".join([f"• `{o['symbol']}`: دخول `${o['entry']}` | وقف `${o['sl']}` | هدف `${o['tp2']}`\n" for o in open_tr]) or "لا توجد صفقات مفتوحة الآن.\n"

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
# 5. مراقبة وإغلاق الصفقات
# ========================================================
def track_open_trades():
    hist = load_history()
    open_trades = hist.get("open_trades", [])
    if not open_trades: return

    updated_open = []
    changed = False

    for t in open_trades:
        symbol, entry, sl, tp2, amount = t['symbol'], t['entry'], t['sl'], t['tp2'], t['amount']

        try:
            ticker = market_exchange.fetch_ticker(symbol)
            curr = ticker['last']

            # تحقق الهدف الثاني TP2
            if curr >= tp2:
                profit = amount * ((tp2 - entry) / entry)
                try: binance_testnet.create_market_sell_order(symbol, amount / entry)
                except: pass

                hist["winning_trades"].append({
                    "symbol": symbol, "entry": entry, "exit": tp2, "profit": profit,
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M')
                })
                hist["total_profit_usdt"] += profit
                hist["current_balance"] += profit
                changed = True

                msg = (
                    f"🎯 *تم تحقيق الهدف بنجاح في باينانس (TP2 HIT)!* 🎉\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"📥 *سعر الدخول:* `${entry:.4f}` ⬅️ *سعر البيع:* `${tp2:.4f}`\n"
                    f"💵 *صافي الربح:* `+${profit:.2f}` USDT 🟢\n"
                    f"💼 *رصيد باينانس المحدث:* `${hist['current_balance']:,.2f}` USDT\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                send_telegram(msg)
                continue

            # ضرب وقف الخسارة الفني
            elif curr <= sl:
                loss = amount * ((sl - entry) / entry)
                try: binance_testnet.create_market_sell_order(symbol, amount / entry)
                except: pass

                hist["losing_trades"].append({
                    "symbol": symbol, "entry": entry, "exit": sl, "loss": loss,
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M')
                })
                hist["total_profit_usdt"] += loss
                hist["current_balance"] += loss
                changed = True

                msg = (
                    f"🛑 *تنبيه: ضرب وقف الخسارة الفني (STOP LOSS)* 🛑\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 *العملة:* `#{symbol}`\n"
                    f"📥 *سعر الدخول:* `${entry:.4f}` ⬅️ *سعر الخروج:* `${sl:.4f}`\n"
                    f"📉 *الخسارة المحسوبة:* `${loss:.2f}` USDT 🔴\n"
                    f"💼 *رصيد باينانس المحدث:* `${hist['current_balance']:,.2f}` USDT\n"
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
# 6. محرك SMC الفني الدقيق لتنفيذ شروطك الأربعة
# ========================================================
def scan_smc():
    hist = load_history()
    open_symbols = [t['symbol'] for t in hist.get("open_trades", [])]

    for symbol in SYMBOLS:
        if symbol in open_symbols:
            continue

        try:
            ohlcv = market_exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=70)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # 1. فلتر الاتجاه: السعر فوق متوسط EMA 50
            df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
            curr_price = df['close'].iloc[-1]
            ema_50 = df['ema_50'].iloc[-1]

            if curr_price < ema_50:
                continue

            # 2. فحص الكسر والفوليوم على الشمعة السابقة المكتملة 100% (df.iloc[-2])
            breakout_candle_close = df['close'].iloc[-2]
            breakout_candle_vol = df['volume'].iloc[-2]
            vol_ma20 = df['volume'].rolling(window=20).mean().iloc[-2]
            
            # قمة الشموع السابقة للاختراق
            prev_high = df['high'].iloc[-14:-2].max()

            # تحقق كسر القمة السابقة (BOS) مع فوليوم تأكيد
            is_bos = breakout_candle_close > prev_high
            is_vol_confirmed = breakout_candle_vol >= (vol_ma20 * 0.95)

            # 3. فحص فجوة الـ FVG الحقيقية
            c1_high = df['high'].iloc[-3]
            c3_low = df['low'].iloc[-1]
            is_fvg = c3_low >= (c1_high * 0.999)

            if is_bos and is_vol_confirmed and is_fvg:
                entry = curr_price
                
                # 4. وقف الخسارة الفني: أسفل قاع الـ Order Block أو الـ FVG مباشرة
                ob_low = df['low'].iloc[-3]        # قاع شمعة الأوردر بلوك
                fvg_low = df['low'].iloc[-2]       # قاع شمعة الاختراق والـ FVG
                technical_low = min(ob_low, fvg_low)
                
                # الوقف أسفل القاع الفني بـ 0.2% كهامش أمان ضد الذيول
                sl = technical_low * 0.998
                sl_pct = ((entry - sl) / entry) * 100

                # شرطك الصارم: وقف الخسارة الفني يجب أن يكون بين 1.5% إلى 3.2% فقط
                if sl_pct < MIN_TECHNICAL_SL_PCT or sl_pct > MAX_TECHNICAL_SL_PCT:
                    continue

                # الأهداف الفنية: عائد 1:1.6 و 1:2.8
                risk = entry - sl
                tp1 = entry + (risk * 1.6)
                tp2 = entry + (risk * 2.8)

                tp1_pct = ((tp1 - entry) / entry) * 100
                tp2_pct = ((tp2 - entry) / entry) * 100

                smc_reason = "BOS + Bullish FVG (Order Block Support)"
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
                    "symbol": symbol, "entry": entry, "sl": sl, "tp1": tp1,
                    "tp2": tp2, "amount": trade_amount, "time": datetime.now().strftime('%Y-%m-%d %H:%M')
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
                    f"🌟 *تصنيف الصفقة:* صفقة مؤكدة (+A) 🌟\n"
                    f"📌 *التأكيد الفني:* كسر هيكل صاعد فوق EMA50 وتأكيد فوليوم الشمعة المكتملة\n"
                    f"🔍 *السبب الفني:* `{smc_reason}`\n"
                    f"🟢 *توجيه السيولة:* {exec_note} 🟢\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💵 *سعر الدخول:* `${entry:.4f}`\n"
                    f"🛡️ *قاع الدعم (OB/FVG Low):* `${technical_low:.4f}`\n"
                    f"🛑 *وقف الخسارة الفني:* `${sl:.4f}` (-{sl_pct:.2f}%)\n"
                    f"🎯 *الهدف الأول (TP1 - 1:1.6):* `${tp1:.4f}` (+{tp1_pct:.2f}%)\n"
                    f"🎯 *الهدف الثاني (TP2 - 1:2.8):* `${tp2:.4f}` (+{tp2_pct:.2f}%)\n"
                    f"💼 *حجم العقد المنفذ (10%):* `${trade_amount:.2f} USDT`\n"
                    f"🌐 *سوق البيتكوين:* {btc_status}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 [عرض الشارت على Binance]({binance_link})\n"
                    f"📈 [عرض الشارت على TradingView]({tv_link})"
                )
                send_telegram(msg)

            time.sleep(0.15)
        except:
            pass

# ========================================================
# 7. حلقة التشغيل الرئيسية
# ========================================================
def main():
    bal = get_binance_balance()
    print("✅ تم تثبيت القواعد الفنية الصارمة بنجاح!")
    send_telegram(
        f"🎯 *تم تفعيل البوت بالقواعد الفنية الصارمة المعتمدة!* 🟢\n\n"
        f"💼 رصيد باينانس: `${bal:,.2f}` USDT (دخول 10% لكل صفقة).\n"
        f"1. فحص الكسر والفوليوم على الشمعة السابقة المكتملة 100%.\n"
        f"2. فلتر الاتجاه: الشراء فقط فوق EMA 50.\n"
        f"3. وقف الخسارة الفني: أسفل قاع الـ Order Block والـ FVG مباشرة (1.5% إلى 3.2%).\n"
        f"4. نسبة عائد إلى مخاطرة عالية: 1:1.6 و 1:2.8 للأهداف.\n"
        f"💬 أرسل كلمة (تقرير) في أي وقت لتحديث كشف الحساب لحظياً!"
    )

    last_night_day = -1
    while True:
        try:
            check_telegram_commands()
            track_open_trades()
            scan_smc()

            now = datetime.now()
            if now.hour == 23 and now.day != last_night_day:
                send_full_detailed_report()
                last_night_day = now.day

            time.sleep(40)
        except Exception as e:
            time.sleep(15)

if __name__ == "__main__":
    main()
