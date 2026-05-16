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
            tickers = exchange.fetch_tickers()
            symbols_to_check = []
            
            for symbol, ticker in tickers.items():
                if symbol.endswith('/USDT') and ticker.get('quoteVolume') is not None:
                    if 5000 < ticker['quoteVolume'] < 200000:
                        symbols_to_check.append(symbol)
            
            total_coins = len(symbols_to_check)
            live_results = []
            
            for i, symbol in enumerate(symbols_to_check):
                try:
                    orderbook = exchange.fetch_order_book(symbol, limit=20)
                    bids = orderbook['bids']
                    asks = orderbook['asks']
                    
                    if not bids or not asks:
                        continue
                        
                    MIN_WALL_USD = 300 
                    
                    # Быстрый поиск стенок
                    best_bid_wall = next((price for price, amount in bids if (price * amount) >= MIN_WALL_USD), None)
                    best_ask_wall = next((price for price, amount in asks if (price * amount) >= MIN_WALL_USD), None)
                            
                    if best_bid_wall and best_ask_wall:
                        spread = ((best_ask_wall - best_bid_wall) / best_bid_wall) * 100
                        if spread >= 1.5:
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
                        # Если нашли монеты - сразу сортируем и отдаем на сайт
                        latest_results = sorted(live_results, key=lambda x: float(x["spread"].strip('%')), reverse=True)
                    else:
                        # Если пока пусто - показываем счетчик прогресса (обновляем каждые 3 монеты)
                        if i % 3 == 0: 
                            latest_results = [{
                                "ticker": f"СКАНИРОВАНИЕ ({i}/{total_coins})...",
                                "spread": "-", "low": "-", "high": "-", "hits": "-", "vol": "-"
                            }]

                    time.sleep(0.2) 
                except Exception as e:
                    time.sleep(0.2)
                    continue
            
            # Если круг закончился, а ничего не нашли
            if not live_results:
                 latest_results = [{"ticker": "ЖДЕМ СИТУАЦИЙ...", "spread": "-", "low": "-", "high": "-", "hits": "-", "vol": "-"}]
            
            # Отдыхаем перед новым кругом
            time.sleep(15)
            
        except Exception as e:
            time.sleep(15)

# Запускаем радар
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
