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

def scan_market():
    global latest_results
    while True:
        try:
            print("\n[РАДАР] Запрашиваю монеты...", flush=True)
            tickers = exchange.fetch_tickers()
            symbols_to_check = []
            
            for symbol, ticker in tickers.items():
                if symbol.endswith('/USDT') and ticker.get('quoteVolume') is not None:
                    if 5000 < ticker['quoteVolume'] < 200000:
                        symbols_to_check.append(symbol)
            
            # ДЛЯ ТЕСТА: Оставляем только 10 монет!
            symbols_to_check = symbols_to_check[:10]
            
            print(f"[РАДАР] Начинаю сканировать {len(symbols_to_check)} стаканов...", flush=True)
            temp_results = []
            
            for i, symbol in enumerate(symbols_to_check):
                try:
                    print(f"[{i+1}/{len(symbols_to_check)}] Сканирую: {symbol}", flush=True)
                    
                    orderbook = exchange.fetch_order_book(symbol, limit=20)
                    bids = orderbook['bids']
                    asks = orderbook['asks']
                    
                    if not bids or not asks:
                        continue
                        
                    MIN_WALL_USD = 300 
                    
                    best_bid_wall = None
                    for bid in bids:
                        price, amount = bid[0], bid[1]
                        if (price * amount) >= MIN_WALL_USD:
                            best_bid_wall = price
                            break
                            
                    best_ask_wall = None
                    for ask in asks:
                        price, amount = ask[0], ask[1]
                        if (price * amount) >= MIN_WALL_USD:
                            best_ask_wall = price
                            break
                            
                    if best_bid_wall and best_ask_wall:
                        spread = ((best_ask_wall - best_bid_wall) / best_bid_wall) * 100
                        if spread >= 1.5:
                            print(f"💰 НАЙДЕН СПРЕД! {symbol} - {spread:.2f}%", flush=True)
                            temp_results.append({
                                "ticker": symbol,
                                "spread": f"{spread:.2f}%",
                                "low": best_bid_wall,
                                "high": best_ask_wall,
                                "hits": "~",
                                "vol": f"> ${MIN_WALL_USD}"
                            })
                            
                    time.sleep(0.2) 
                except Exception as e:
                    print(f"Ошибка {symbol}: {e}", flush=True)
                    time.sleep(0.2)
                    continue
            
            if not temp_results:
                temp_results.append({
                    "ticker": "ЖДЕМ СИТУАЦИЙ...",
                    "spread": "-",
                    "low": "-",
                    "high": "-",
                    "hits": "-",
                    "vol": "-"
                })
                
            latest_results = temp_results
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
    if not latest_results:
         return jsonify([{
            "ticker": "ИНИЦИАЛИЗАЦИЯ РАДАРА...",
            "spread": "-",
            "low": "-",
            "high": "-",
            "hits": "-",
            "vol": "-"
        }])
    return jsonify(latest_results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
