from flask import Flask, jsonify
from flask_cors import CORS
import ccxt
import time
import threading

app = Flask(__name__)
CORS(app)

exchange = ccxt.bingx({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

latest_ping_pong = []
latest_densities = []
scanner_started = False
lock = threading.Lock()

def scan_market():
    global latest_ping_pong, latest_densities
    while True:
        try:
            print("\n[РАДАР] Запрашиваю монеты с BingX...", flush=True)
            tickers = exchange.fetch_tickers()
            symbols_to_check = []
            
            for symbol, ticker in tickers.items():
                if symbol.endswith('/USDT') and ticker.get('quoteVolume') is not None:
                    if 5000 < ticker['quoteVolume'] < 200000:
                        symbols_to_check.append(symbol)
            
            total_coins = len(symbols_to_check)
            live_ping_pong = []
            live_densities = []
            
            for i, symbol in enumerate(symbols_to_check):
                try:
                    if i % 10 == 0:
                        print(f"[{i}/{total_coins}] Сканирую стакан: {symbol}", flush=True)

                    orderbook = exchange.fetch_order_book(symbol, limit=20)
                    bids = orderbook['bids']
                    asks = orderbook['asks']
                    
                    if not bids or not asks:
                        continue
                        
                    current_price = (bids[0][0] + asks[0][0]) / 2

                    # ==========================================
                    # СТРАТЕГИЯ 1: ПЛОТНОСТИ (Стенки от $5000)
                    # ==========================================
                    DENSITY_MIN_USD = 5000
                    
                    for price, amount in bids:
                        vol_usd = price * amount
                        if vol_usd >= DENSITY_MIN_USD:
                            dist = ((current_price - price) / current_price) * 100
                            live_densities.append({
                                "ticker": symbol, "type": "LONG", "price": price, 
                                "vol": int(vol_usd), "dist": f"{dist:.2f}%"
                            })
                            
                    for price, amount in asks:
                        vol_usd = price * amount
                        if vol_usd >= DENSITY_MIN_USD:
                            dist = ((price - current_price) / current_price) * 100
                            live_densities.append({
                                "ticker": symbol, "type": "SHORT", "price": price, 
                                "vol": int(vol_usd), "dist": f"{dist:.2f}%"
                            })

                    # ==========================================
                    # СТРАТЕГИЯ 2: ПИНГ-ПОНГ (Спред от 1.5%)
                    # ==========================================
                    PP_MIN_WALL = 300 
                    best_bid_wall = next((p for p, a in bids if (p * a) >= PP_MIN_WALL), None)
                    best_ask_wall = next((p for p, a in asks if (p * a) >= PP_MIN_WALL), None)
                            
                    if best_bid_wall and best_ask_wall:
                        spread = ((best_ask_wall - best_bid_wall) / best_bid_wall) * 100
                        if spread >= 1.5:
                            trades_activity = "~"
                            try:
                                trades = exchange.fetch_trades(symbol, limit=100)
                                curr_ms = int(time.time() * 1000)
                                c1, c5, c15 = 0, 0, 0
                                for t in trades:
                                    if t['timestamp']:
                                        d = curr_ms - t['timestamp']
                                        if d <= 60000: c1 += 1
                                        if d <= 300000: c5 += 1
                                        if d <= 900000: c15 += 1
                                trades_activity = f"{c1} / {c5} / {c15}"
                            except: pass
                            
                            live_ping_pong.append({
                                "ticker": symbol, "spread": f"{spread:.2f}%", 
                                "low": best_bid_wall, "high": best_ask_wall,
                                "hits": trades_activity, "vol": f"> ${PP_MIN_WALL}"
                            })
                    
                    # === ОПТИМИЗАЦИЯ ВЫДАЧИ ===
                    if live_ping_pong:
                        latest_ping_pong = sorted(live_ping_pong, key=lambda x: float(x["spread"].strip('%')), reverse=True)
                    else:
                        if i % 3 == 0: 
                            latest_ping_pong = [{"ticker": f"СКАНИРОВАНИЕ ({i}/{total_coins})...", "spread": "-", "low": "-", "high": "-", "hits": "-", "vol": "-"}]

                    if live_densities:
                        # Берем только ТОП-100 самых крупных стенок, чтобы не вешать браузер
                        latest_densities = sorted(live_densities, key=lambda x: x["vol"], reverse=True)[:100]
                    else:
                        if i % 3 == 0: 
                            latest_densities = [{"ticker": f"СКАНИРОВАНИЕ ({i}/{total_coins})...", "type": "-", "price": "-", "vol": "-", "dist": "-"}]

                    time.sleep(0.2) 
                except Exception as e:
                    time.sleep(0.2)
                    continue
            
            if not live_ping_pong:
                 latest_ping_pong = [{"ticker": "ЖДЕМ СИТУАЦИЙ...", "spread": "-", "low": "-", "high": "-", "hits": "-", "vol": "-"}]
            if not live_densities:
                 latest_densities = [{"ticker": "ПЛОТНОСТЕЙ НЕТ...", "type": "-", "price": "-", "vol": "-", "dist": "-"}]
            
            print(f"[РАДАР] Круг завершен! Спим 15 сек...", flush=True)
            time.sleep(15)
            
        except Exception as e:
            print(f"[РАДАР] Глобальная ошибка: {e}", flush=True)
            time.sleep(15)

def start_scanner():
    global scanner_started
    with lock:
        if not scanner_started:
            scanner_thread = threading.Thread(target=scan_market, daemon=True)
            scanner_thread.start()
            scanner_started = True

@app.route('/')
def home():
    return "[SYSTEM_OFFLINE] Ping-Pong Scanner API is running."

@app.route('/api/ping-pong')
def get_ping_pong_data():
    start_scanner()
    if not latest_ping_pong:
         return jsonify([{"ticker": "ИНИЦИАЛИЗАЦИЯ...", "spread": "-", "low": "-", "high": "-", "hits": "-", "vol": "-"}])
    return jsonify(latest_ping_pong)

@app.route('/api/densities')
def get_densities_data():
    start_scanner()
    if not latest_densities:
         return jsonify([{"ticker": "ИНИЦИАЛИЗАЦИЯ...", "type": "-", "price": "-", "vol": "-", "dist": "-"}])
    return jsonify(latest_densities)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
