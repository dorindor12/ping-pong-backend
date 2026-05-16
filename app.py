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

# Глобальная переменная (наша "коробочка"), где сервер хранит готовые результаты
latest_results = []

def scan_market():
    global latest_results
    while True:
        try:
            tickers = exchange.fetch_tickers()
            symbols_to_check = []
            
            # Отбираем весь неликвид (от 5k до 200k USDT в сутки)
            for symbol, ticker in tickers.items():
                if symbol.endswith('/USDT') and ticker.get('quoteVolume') is not None:
                    if 5000 < ticker['quoteVolume'] < 200000:
                        symbols_to_check.append(symbol)
            
            temp_results = []
            
            # Сканируем весь список без ограничений
            for symbol in symbols_to_check:
                try:
                    orderbook = exchange.fetch_order_book(symbol, limit=20)
                    bids = orderbook['bids']
                    asks = orderbook['asks']
                    
                    if not bids or not asks:
                        continue
                        
                    # Ищем плотности от $300
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
                            
                    # Считаем спред
                    if best_bid_wall and best_ask_wall:
                        spread = ((best_ask_wall - best_bid_wall) / best_bid_wall) * 100
                        
                        # Отбираем только спред от 1.5%
                        if spread >= 1.5:
                            temp_results.append({
                                "ticker": symbol,
                                "spread": f"{spread:.2f}%",
                                "low": best_bid_wall,
                                "high": best_ask_wall,
                                "hits": "~",
                                "vol": f"> ${MIN_WALL_USD}"
                            })
                            
                    # Микро-пауза, чтобы биржа не забанила за спам запросами
                    time.sleep(0.1) 
                except Exception as e:
                    time.sleep(0.1)
                    continue
            
            # Если рынок совсем пустой
            if not temp_results:
                temp_results.append({
                    "ticker": "ЖДЕМ СИТУАЦИЙ...",
                    "spread": "-",
                    "low": "-",
                    "high": "-",
                    "hits": "-",
                    "vol": "-"
                })
                
            # Перекладываем свежие данные в "коробочку"
            latest_results = temp_results
            
            # Отдыхаем 15 секунд перед новым кругом сканирования
            time.sleep(15)
            
        except Exception as e:
            time.sleep(15)

# Запускаем радар в фоновом режиме при старте сервера
scanner_thread = threading.Thread(target=scan_market, daemon=True)
scanner_thread.start()

@app.route('/')
def home():
    return "[SYSTEM_OFFLINE] Ping-Pong Scanner API is running."

@app.route('/api/ping-pong')
def get_ping_pong_data():
    # Если радар еще делает самый первый круг после запуска
    if not latest_results:
         return jsonify([{
            "ticker": "ИНИЦИАЛИЗАЦИЯ РАДАРА...",
            "spread": "-",
            "low": "-",
            "high": "-",
            "hits": "-",
            "vol": "-"
        }])
    # Отдаем данные моментально
    return jsonify(latest_results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
