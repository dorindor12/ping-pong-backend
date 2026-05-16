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

latest_results = []
scanner_started = False
lock = threading.Lock()

def scan_market():
    global latest_results
    while True:
        try:
            print("\n[РАДАР] Фоновый поток запущен! Запрашиваю монеты с BingX...", flush=True)
            tickers = exchange.fetch_tickers()
            symbols_to_check = []
            
            for symbol, ticker in tickers.items():
                if symbol.endswith('/USDT') and ticker.get('quoteVolume') is not None:
                    if 5000 < ticker['quoteVolume'] < 200000:
                        symbols_to_check.append(symbol)
            
            total_coins = len(symbols_to_check)
            print(f"[РАДАР] Найдено {total_coins} неликвидных пар. Анализируем...", flush=True)
            live_results = []
            
            for i, symbol in enumerate(symbols_to_check):
                try:
                    if i % 10 == 0:
                        print(f"[{i}/{total_coins}] Сканирую стакан: {symbol}", flush=True)

                    orderbook = exchange.fetch_order_book(symbol, limit=20)
                    bids = orderbook['bids']
                    asks = orderbook['asks']
                    
                    if not bids or not asks:
                        continue
                        
                    MIN_WALL_USD = 300 
                    
                    best_bid_wall = next((price for price, amount in bids if (price * amount) >= MIN_WALL_USD), None)
                    best_ask_wall = next((price for price, amount in asks if (price * amount) >= MIN_WALL_USD), None)
                            
                    if best_bid_wall and best_ask_wall:
                        spread = ((best_ask_wall - best_bid_wall) / best_bid_wall) * 100
                        if spread >= 1.5:
                            
                            # === СНАЙПЕРСКАЯ ПРОВЕРКА (1м / 5м / 15м) ===
                            trades_activity = "~"
                            try:
                                # Берем 100 последних сделок
                                trades = exchange.fetch_trades(symbol, limit=100)
                                current_time_ms = int(time.time() * 1000)
                                
                                count_1m = 0
                                count_5m = 0
                                count_15m = 0
                                
                                for t in trades:
                                    if t['timestamp']:
                                        diff = current_time_ms - t['timestamp']
                                        if diff <= 60000:       # 1 минута
                                            count_1m += 1
                                        if diff <= 300000:      # 5 минут
                                            count_5m += 1
                                        if diff <= 900000:      # 15 минут
                                            count_15m += 1
                                            
                                trades_activity = f"{count_1m} / {count_5m} / {count_15m}"
                            except Exception as e:
                                pass
                            # ============================================

                            print(f"💰 {symbol} | Спред: {spread:.2f}% | Сделок: {trades_activity}", flush=True)
                            
                            live_results.append({
                                "ticker": symbol,
                                "spread": f"{spread:.2f}%",
                                "low": best_bid_wall,
                                "high": best_ask_wall,
                                "hits": trades_activity, 
                                "vol": f"> ${MIN_WALL_USD}"
                            })
                    
                    if live_results:
                        latest_results = sorted(live_results, key=lambda x: float(x["spread"].strip('%')), reverse=True)
                    else:
                        if i % 3 == 0: 
                            latest_results = [{
                                "ticker": f"СКАНИРОВАНИЕ ({i}/{total_coins})...",
                                "spread": "-", "low": "-", "high": "-", "hits": "-", "vol": "-"
                            }]

                    time.sleep(0.2) 
                except Exception as e:
                    time.sleep(0.2)
                    continue
            
            if not live_results:
                 latest_results = [{"ticker": "ЖДЕМ СИТУАЦИЙ...", "spread": "-", "low": "-", "high": "-", "hits": "-", "vol": "-"}]
            
            print(f"[РАДАР] Круг завершен! Найдено {len(live_results)} монет. Спим 15 сек...", flush=True)
            time.sleep(15)
            
        except Exception as e:
            print(f"[РАДАР] Глобальная ошибка: {e}", flush=True)
            time.sleep(15)

@app.route('/')
def home():
    return "[SYSTEM_OFFLINE] Ping-Pong Scanner API is running."

@app.route('/api/ping-pong')
def get_ping_pong_data():
    global scanner_started
    if not scanner_started:
        with lock:
            if not scanner_started:
                scanner_thread = threading.Thread(target=scan_market, daemon=True)
                scanner_thread.start()
                scanner_started = True

    if not latest_results:
         return jsonify([{"ticker": "ИНИЦИАЛИЗАЦИЯ РАДАРА...", "spread": "-", "low": "-", "high": "-", "hits": "-", "vol": "-"}])
        
    return jsonify(latest_results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
