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

# Заглушка при самом первом старте
latest_results = [{"ticker": "ЗАПУСК РАДАРА...", "spread": "-", "low": "-", "high": "-", "hits": "-", "vol": "-"}]

def scan_market():
    global latest_results
    while True:
        try:
            print("\n[РАДАР] Запрашиваю монеты с биржи BingX...", flush=True)
            tickers = exchange.fetch_tickers()
            symbols_to_check = []
            
            for symbol, ticker in tickers.items():
                if symbol.endswith('/USDT') and ticker.get('quoteVolume') is not None:
                    if 5000 < ticker['quoteVolume'] < 200000:
                        symbols_to_check.append(symbol)
            
            total_coins = len(symbols_to_check)
            print(f"[РАДАР] Начинаю сканировать {total_coins} стаканов...", flush=True)
            live_results = []
            
            for i, symbol in enumerate(symbols_to_check):
                try:
                    # Выводим в лог каждую 10-ю монету, чтобы видеть, что процесс идет
                    if i % 10 == 0:
                        print(f"[{i}/{total_coins}] Сканирую...", flush=True)

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
                            print(f"💰 НАЙДЕН СПРЕД! {symbol} - {spread:.2f}%", flush=True)
                            live_results.append({
                                "ticker": symbol,
                                "spread": f"{spread:.2f}%",
                                "low": best_bid_wall,
                                "high": best_ask_wall,
                                "hits": "~",
                                "vol": f"> ${MIN_WALL_USD}"
                            })
                    
                    # === ЖИВОЕ ОБНОВЛЕНИЕ ДАННЫХ ДЛЯ САЙТА ===
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
            
            print(f"[РАДАР] Круг завершен! Спим 15 сек...", flush=True)
            time.sleep(15)
            
        except Exception as e:
            print(f"[РАДАР] Глобальная ошибка: {e}", flush=True)
            time.sleep(15)

scanner_thread = threading.Thread(target=scan_market, daemon=True)
scanner_thread.start()

@app.route('/')
def home():
    return "[SYSTEM_OFFLINE] Ping-Pong Scanner API is running."

@app.route('/api/ping-pong')
def get_ping_pong_data():
    return jsonify(latest_results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
