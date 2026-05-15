from flask import Flask, jsonify
from flask_cors import CORS
import ccxt

app = Flask(__name__)
# Разрешаем твоему сайту на GitHub получать данные отсюда
CORS(app) 

# Инициализация BingX
exchange = ccxt.bingx({'enableRateLimit': True})

@app.route('/')
def home():
    return "[SYSTEM_OFFLINE] Ping-Pong Scanner API is running."

@app.route('/api/ping-pong')
def get_ping_pong_data():
    # Сейчас здесь тестовый массив данных. 
    # Как только сервер запустится, мы заменим это на реальный парсинг стакана BingX.
    data = [
        {"ticker": "CHILLHOUSE/USDT", "spread": "8.5%", "low": "0.02428", "high": "0.02679", "hits": 6, "vol": "$1,200"},
        {"ticker": "NUMI/USDT", "spread": "4.1%", "low": "0.0575", "high": "0.0598", "hits": 3, "vol": "$500"}
    ]
    return jsonify(data)

if __name__ == '__main__':
    # Запуск сервера на порту 10000 (стандарт для Render)
    app.run(host='0.0.0.0', port=10000)