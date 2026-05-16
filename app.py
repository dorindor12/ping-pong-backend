from flask import Flask, jsonify
from flask_cors import CORS
import ccxt
import time

app = Flask(__name__)
CORS(app)

# Подключаемся к BingX (Спотовый рынок)
exchange = ccxt.bingx({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

@app.route('/')
def home():
    return "[SYSTEM_OFFLINE] Ping-Pong Scanner API is running."

@app.route('/api/ping-pong')
def get_ping_pong_data():
    try:
        # 1. Запрашиваем информацию по всем монетам
        tickers = exchange.fetch_tickers()
        
        symbols_to_check = []
        # 2. Ищем неликвидные монеты к USDT
        for symbol, ticker in tickers.items():
            if symbol.endswith('/USDT') and ticker.get('quoteVolume') is not None:
                # Берем монеты с объемом от $5k до $200k в сутки
                if 5000 < ticker['quoteVolume'] < 200000:
                    symbols_to_check.append(symbol)
                    
        # ВАЖНО: Для бесплатного сервера Render ограничиваем проверку до 20 монет за один раз,
        # иначе сервер не успеет ответить за 30 секунд и выдаст ошибку таймаута.
      symbols_to_check = symbols_to_check[:3] 
        
        results = []
        
        # 3. Сканируем стаканы выбранных монет
        for symbol in symbols_to_check:
            try:
                # Загружаем стакан (глубина 20 заявок)
                orderbook = exchange.fetch_order_book(symbol, limit=20)
                bids = orderbook['bids'] # Покупки [цена, объем монет]
                asks = orderbook['asks'] # Продажи [цена, объем монет]
                
                if not bids or not asks:
                    continue
                    
                # Ищем стенки (например, от $300 в одной заявке)
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
                        
                # 4. Считаем спред, если нашли обе стенки
                if best_bid_wall and best_ask_wall:
                    spread = ((best_ask_wall - best_bid_wall) / best_bid_wall) * 100
                    
                    # Забираем в таблицу только жирный спред (больше 1.5%)
                    if spread >= 1.5:
                        results.append({
                            "ticker": symbol,
                            "spread": f"{spread:.2f}%",
                            "low": best_bid_wall,
                            "high": best_ask_wall,
                            "hits": "~", # Касания пока не считаем, это следующий этап
                            "vol": f"> ${MIN_WALL_USD}"
                        })
                        
                # Маленькая пауза, чтобы биржа не забанила IP за спам
                time.sleep(0.1) 
                
            except Exception as e:
                continue # Если монета зависла, просто пропускаем её
                
        # Если рынок совсем мертвый и ситуаций нет, выводим заглушку
        if not results:
            results.append({
                "ticker": "СКАНИРОВАНИЕ...",
                "spread": "-",
                "low": "-",
                "high": "-",
                "hits": "-",
                "vol": "-"
            })

        return jsonify(results)

    except Exception as e:
        return jsonify([{"ticker": "ОШИБКА API", "spread": "ERROR", "low": "-", "high": "-", "hits": "-", "vol": "-"}]), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
