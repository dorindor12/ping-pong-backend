from flask import Flask, jsonify, request
from flask_cors import CORS
import ccxt
import time
import threading

app = Flask(__name__)
CORS(app)

# Подключаем две биржи
exchanges = {
    'bingx': ccxt.bingx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'bitget': ccxt.bitget({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
}

# Раздельная память для каждой биржи
latest_data = {
    'bingx': {'ping_pong': [], 'densities': []},
    'bitget': {'ping_pong': [], 'densities': []}
}

scanner_started = False
lock = threading.Lock()

def scan_market(ex_name):
    exchange = exchanges[ex_name]
    global latest_data
    
    while True:
        try:
            print(f"\n[{ex_name.upper()}] Запрашиваю монеты...", flush=True)
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
                        print(f"[{ex_name.upper()}] [{i}/{total_coins}] Сканирую: {symbol}", flush=True)

                    orderbook = exchange.fetch_order_book(symbol, limit=20)
                    bids = orderbook['bids']
                    asks = orderbook['asks']
                    
                    if not bids or not asks:
                        continue
                        
                    current_price = (bids[0][0] + asks[0][0]) / 2

                    # --- АНАЛИЗ ПЕРЕКОСА СТАКАНА ---
                    total_bid_vol = sum((p * a) for p, a in bids)
                    total_ask_vol = sum((p * a) for p, a in asks)
                    total_vol = total_bid_vol + total_ask_vol
                    bid_pct = int((total_bid_vol / total_vol) * 100) if total_vol > 0 else 50

                    # --- ПЛОТНОСТИ ---
                    DENSITY_MIN_USD = 5000
                    for price, amount in bids:
                        vol_usd = price * amount
                        if vol_usd >= DENSITY_MIN_USD:
                            dist = ((current_price - price) / current_price) * 100
                            live_densities.append({"ticker": symbol, "type": "LONG", "price": price, "vol": int(vol_usd), "dist": f"{dist:.2f}%"})
                            
                    for price, amount in asks:
                        vol_usd = price * amount
                        if vol_usd >= DENSITY_MIN_USD:
                            dist = ((price - current_price) / current_price) * 100
                            live_densities.append({"ticker": symbol, "type": "SHORT", "price": price, "vol": int(vol_usd), "dist": f"{dist:.2f}%"})

                    # --- ПИНГ-ПОНГ ---
                    PP_MIN_WALL = 300 
                    best_bid_wall = next((p for p, a in bids if (p * a) >= PP_MIN_WALL), None)
                    best_ask_wall = next((p for p, a in asks if (p * a) >= PP_MIN_WALL), None)
                            
                    if best_bid_wall and best_ask_wall:
                        spread = ((best_ask_wall - best_bid_wall) / best_bid_wall) * 100
                        if spread >= 1.5:
                            trades_count = "~"
                            trades_vol = "~"
                            try:
                                trades = exchange.fetch_trades(symbol, limit=300)
                                curr_ms = int(time.time() * 1000)
                                
                                c1, c5, c15 = 0, 0, 0
                                v1, v5, v15 = 0, 0, 0
                                
                                for t in trades:
                                    if t['timestamp']:
                                        d = curr_ms - t['timestamp']
                                        cost = t.get('cost')
                                        if cost is None:
                                            cost = t.get('amount', 0) * t.get('price', 0)
                                            
                                        if d <= 60000: 
                                            c1 += 1
                                            v1 += cost
                                        if d <= 300000: 
                                            c5 += 1
                                            v5 += cost
                                        if d <= 900000: 
                                            c15 += 1
                                            v15 += cost
                                        
                                def fmt_v(v):
                                    if v >= 1000: return f"{v/1000:.1f}k"
                                    return str(int(v))
                                    
                                trades_count = f"{c1} / {c5} / {c15}"
                                trades_vol = f"${fmt_v(v1)} / ${fmt_v(v5)} / ${fmt_v(v15)}"
                            except: pass
                            
                            live_ping_pong.append({
                                "ticker": symbol, "spread": f"{spread:.2f}%", 
                                "low": best_bid_wall, "high": best_ask_wall,
                                "hits": trades_count, "vol_act": trades_vol, "vol": f"> ${PP_MIN_WALL}",
                                "imbalance": bid_pct # Добавляем процент покупок
                            })
                    
                    if live_ping_pong:
                        latest_data[ex_name]['ping_pong'] = sorted(live_ping_pong, key=lambda x: float(x["spread"].strip('%')), reverse=True)
                    else:
                        if i % 3 == 0: latest_data[ex_name]['ping_pong'] = [{"ticker": f"СКАНИРОВАНИЕ ({i}/{total_coins})...", "spread": "-", "low": "-", "high": "-", "hits": "-", "vol_act": "-", "vol": "-", "imbalance": "-"}]

                    if live_densities:
                        latest_data[ex_name]['densities'] = sorted(live_densities, key=lambda x: x["vol"], reverse=True)[:100]
                    else:
                        if i % 3 == 0: latest_data[ex_name]['densities'] = [{"ticker": f"СКАНИРОВАНИЕ ({i}/{total_coins})...", "type": "-", "price": "-", "vol": "-", "dist": "-"}]

                    time.sleep(0.2) 
                except Exception as e:
                    time.sleep(0.2)
                    continue
            
            if not live_ping_pong:
                 latest_data[ex_name]['ping_pong'] = [{"ticker": "ЖДЕМ СИТУАЦИЙ...", "spread": "-", "low": "-", "high": "-", "hits": "-", "vol_act": "-", "vol": "-", "imbalance": "-"}]
            if not live_densities:
                 latest_data[ex_name]['densities'] = [{"ticker": "ПЛОТНОСТЕЙ НЕТ...", "type": "-", "price": "-", "vol": "-", "dist": "-"}]
            
            print(f"[{ex_name.upper()}] Круг завершен! Спим 15 сек...", flush=True)
            time.sleep(15)
            
        except Exception as e:
            print(f"[{ex_name.upper()}] Глобальная ошибка: {e}", flush=True)
            time.sleep(15)

def start_scanner():
    global scanner_started
    with lock:
        if not scanner_started:
            threading.Thread(target=scan_market, args=('bingx',), daemon=True).start()
            threading.Thread(target=scan_market, args=('bitget',), daemon=True).start()
            scanner_started = True

@app.route('/')
def home():
    return "[SYSTEM_OFFLINE] Ping-Pong Multi-Scanner API is running."

@app.route('/api/ping-pong')
def get_ping_pong_data():
    start_scanner()
    ex_name = request.args.get('exchange', 'bingx')
    if ex_name not in exchanges: ex_name = 'bingx'
    
    data = latest_data[ex_name]['ping_pong']
    if not data:
         return jsonify([{"ticker": "ИНИЦИАЛИЗАЦИЯ...", "spread": "-", "low": "-", "high": "-", "hits": "-", "vol_act": "-", "vol": "-", "imbalance": "-"}])
    return jsonify(data)

@app.route('/api/densities')
def get_densities_data():
    start_scanner()
    ex_name = request.args.get('exchange', 'bingx')
    if ex_name not in exchanges: ex_name = 'bingx'
    
    data = latest_data[ex_name]['densities']
    if not data:
         return jsonify([{"ticker": "ИНИЦИАЛИЗАЦИЯ...", "type": "-", "price": "-", "vol": "-", "dist": "-"}])
    return jsonify(data)

@app.route('/api/search')
def search_ticker():
    ticker = request.args.get('ticker')
    ex_name = request.args.get('exchange', 'bingx')
    if ex_name not in exchanges: ex_name = 'bingx'
    
    if not ticker: return jsonify({"error": "Введите тикер"}), 400
    
    ticker = ticker.upper().strip()
    if not ticker.endswith('USDT'): ticker += '/USDT'
    elif not ticker.endswith('/USDT') and ticker.endswith('USDT'): ticker = ticker.replace('USDT', '/USDT')
        
    try:
        orderbook = exchanges[ex_name].fetch_order_book(ticker, limit=50)
        bids = orderbook['bids']
        asks = orderbook['asks']
        
        if not bids or not asks: return jsonify({"error": "Стакан пуст или монета не торгуется"}), 404
            
        current_price = (bids[0][0] + asks[0][0]) / 2
        spread = ((asks[0][0] - bids[0][0]) / bids[0][0]) * 100
        
        nearest_bid = next(((p, p*a) for p, a in bids if p * a >= 1000), None)
        nearest_ask = next(((p, p*a) for p, a in asks if p * a >= 1000), None)
        
        return jsonify({
            "ticker": ticker,
            "price": current_price,
            "spread": f"{spread:.2f}%",
            "nearest_bid": {"price": nearest_bid[0], "vol": int(nearest_bid[1])} if nearest_bid else None,
            "nearest_ask": {"price": nearest_ask[0], "vol": int(nearest_ask[1])} if nearest_ask else None
        })
    except Exception as e:
        return jsonify({"error": f"Монета не найдена на {ex_name.capitalize()}"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
