from flask import Flask, jsonify, request
from flask_cors import CORS
import ccxt
import time
import threading

app = Flask(__name__)
CORS(app)

# Подключаем СПОТ рынки
exchanges_spot = {
    'bingx': ccxt.bingx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'bitget': ccxt.bitget({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'mexc': ccxt.mexc({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
}

# Подключаем ФЬЮЧЕРСНЫЕ рынки
exchanges_swap = {
    'bingx': ccxt.bingx({'enableRateLimit': True, 'options': {'defaultType': 'swap'}}),
    'bitget': ccxt.bitget({'enableRateLimit': True, 'options': {'defaultType': 'swap'}}),
    'mexc': ccxt.mexc({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
}

latest_data = {
    'bingx': {'ping_pong': [], 'densities': [], 'arbitrage': []},
    'bitget': {'ping_pong': [], 'densities': [], 'arbitrage': []},
    'mexc': {'ping_pong': [], 'densities': [], 'arbitrage': []}
}

scanner_started = False
lock = threading.Lock()

# --- 1. СКАНЕР СПОТА (Пинг-Понг и Плотности) ---
def scan_spot(ex_name):
    exchange = exchanges_spot[ex_name]
    global latest_data
    
    while True:
        try:
            tickers = exchange.fetch_tickers()
            symbols_to_check = [sym for sym, t in tickers.items() if sym.endswith('/USDT') and t.get('quoteVolume') and 5000 < t['quoteVolume'] < 200000]
            
            live_ping_pong = []
            live_densities = []
            
            for i, symbol in enumerate(symbols_to_check):
                try:
                    orderbook = exchange.fetch_order_book(symbol, limit=20)
                    bids, asks = orderbook['bids'], orderbook['asks']
                    if not bids or not asks: continue
                        
                    current_price = (bids[0][0] + asks[0][0]) / 2
                    total_bid_vol = sum((p * a) for p, a in bids)
                    total_ask_vol = sum((p * a) for p, a in asks)
                    total_vol = total_bid_vol + total_ask_vol
                    bid_pct = int((total_bid_vol / total_vol) * 100) if total_vol > 0 else 50

                    DENSITY_MIN_USD = 5000
                    for price, amount in bids:
                        if price * amount >= DENSITY_MIN_USD:
                            live_densities.append({"ticker": symbol, "type": "LONG", "price": price, "vol": int(price * amount), "dist": f"{((current_price - price) / current_price) * 100:.2f}%"})
                    for price, amount in asks:
                        if price * amount >= DENSITY_MIN_USD:
                            live_densities.append({"ticker": symbol, "type": "SHORT", "price": price, "vol": int(price * amount), "dist": f"{((price - current_price) / current_price) * 100:.2f}%"})

                    PP_MIN_WALL = 300 
                    best_bid_wall = next((p for p, a in bids if (p * a) >= PP_MIN_WALL), None)
                    best_ask_wall = next((p for p, a in asks if (p * a) >= PP_MIN_WALL), None)
                            
                    if best_bid_wall and best_ask_wall:
                        spread = ((best_ask_wall - best_bid_wall) / best_bid_wall) * 100
                        if spread >= 1.5:
                            trades_count, trades_vol = "~", "~"
                            try:
                                trades = exchange.fetch_trades(symbol, limit=300)
                                curr_ms = int(time.time() * 1000)
                                c1, c5, c15, v1, v5, v15 = 0, 0, 0, 0, 0, 0
                                for t in trades:
                                    if t['timestamp']:
                                        d = curr_ms - t['timestamp']
                                        cost = t.get('cost') or (t.get('amount', 0) * t.get('price', 0))
                                        if d <= 60000: c1 += 1; v1 += cost
                                        if d <= 300000: c5 += 1; v5 += cost
                                        if d <= 900000: c15 += 1; v15 += cost
                                def fmt_v(v): return f"{v/1000:.1f}k" if v >= 1000 else str(int(v))
                                trades_count = f"{c1} / {c5} / {c15}"
                                trades_vol = f"${fmt_v(v1)} / ${fmt_v(v5)} / ${fmt_v(v15)}"
                            except: pass
                            
                            live_ping_pong.append({
                                "ticker": symbol, "spread": f"{spread:.2f}%", "low": best_bid_wall, "high": best_ask_wall,
                                "hits": trades_count, "vol_act": trades_vol, "vol": f"> ${PP_MIN_WALL}", "imbalance": bid_pct 
                            })
                    
                    if live_ping_pong: latest_data[ex_name]['ping_pong'] = sorted(live_ping_pong, key=lambda x: float(x["spread"].strip('%')), reverse=True)
                    if live_densities: latest_data[ex_name]['densities'] = sorted(live_densities, key=lambda x: x["vol"], reverse=True)[:100]
                    time.sleep(0.2) 
                except: time.sleep(0.2); continue
            
            if not live_ping_pong: latest_data[ex_name]['ping_pong'] = [{"ticker": "ЖДЕМ СИТУАЦИЙ...", "spread": "-", "low": "-", "high": "-", "hits": "-", "vol_act": "-", "vol": "-", "imbalance": "-"}]
            if not live_densities: latest_data[ex_name]['densities'] = [{"ticker": "ПЛОТНОСТЕЙ НЕТ...", "type": "-", "price": "-", "vol": "-", "dist": "-"}]
            time.sleep(15)
        except: time.sleep(15)

# --- 2. СКАНЕР АРБИТРАЖА (Спот vs Фьючерс) ---
def scan_arbitrage():
    global latest_data
    while True:
        for ex_name in ['bingx', 'bitget', 'mexc']:
            try:
                spot_tickers = exchanges_spot[ex_name].fetch_tickers()
                swap_tickers = exchanges_swap[ex_name].fetch_tickers()
                
                arb_list = []
                for spot_sym, spot_data in spot_tickers.items():
                    if not spot_sym.endswith('/USDT'): continue
                    
                    base_coin = spot_sym.split('/')[0]
                    swap_sym = f"{base_coin}/USDT:USDT" # Формат фьючерса
                    
                    if swap_sym in swap_tickers:
                        spot_price = spot_data.get('last')
                        swap_price = swap_tickers[swap_sym].get('last')
                        
                        if spot_price and swap_price and spot_price > 0:
                            spread = ((swap_price - spot_price) / spot_price) * 100
                            
                            # Ищем разрыв больше 1%
                            if abs(spread) >= 1.0:
                                action = "🔴 ПРОДАТЬ ФЬЮЧ + КУПИТЬ СПОТ" if spread > 0 else "🟢 КУПИТЬ ФЬЮЧ + ПРОДАТЬ СПОТ"
                                
                                # Запрашиваем стакан СПОТА только для этой монеты
                                imbalance = "-"
                                try:
                                    ob = exchanges_spot[ex_name].fetch_order_book(spot_sym, limit=20)
                                    bids, asks = ob['bids'], ob['asks']
                                    if bids and asks:
                                        tb = sum(p*a for p, a in bids)
                                        ta = sum(p*a for p, a in asks)
                                        imbalance = int((tb / (tb+ta)) * 100) if (tb+ta) > 0 else 50
                                    time.sleep(0.1) # Защита от бана
                                except: pass
                                
                                arb_list.append({
                                    "ticker": base_coin,
                                    "spot_price": spot_price,
                                    "swap_price": swap_price,
                                    "spread": f"{spread:.2f}%",
                                    "action": action,
                                    "raw_spread": abs(spread),
                                    "imbalance": imbalance
                                })
                
                if arb_list:
                    latest_data[ex_name]['arbitrage'] = sorted(arb_list, key=lambda x: x['raw_spread'], reverse=True)
                else:
                    latest_data[ex_name]['arbitrage'] = [{"ticker": "РАЗРЫВОВ НЕТ", "spot_price": "-", "swap_price": "-", "spread": "-", "action": "-", "imbalance": "-"}]
                    
            except Exception as e:
                print(f"[ARB ERROR {ex_name}]: {e}")
        time.sleep(10) # Обновляем арбитраж каждые 10 секунд

def start_scanner():
    global scanner_started
    with lock:
        if not scanner_started:
            threading.Thread(target=scan_spot, args=('bingx',), daemon=True).start()
            threading.Thread(target=scan_spot, args=('bitget',), daemon=True).start()
            threading.Thread(target=scan_spot, args=('mexc',), daemon=True).start()
            threading.Thread(target=scan_arbitrage, daemon=True).start()
            scanner_started = True

@app.route('/')
def home(): return "[SYSTEM_ONLINE] Multi-Scanner API"

@app.route('/api/ping-pong')
def get_ping_pong_data():
    start_scanner(); ex = request.args.get('exchange', 'bingx')
    return jsonify(latest_data.get(ex, latest_data['bingx'])['ping_pong'] or [{"ticker": "ИНИЦИАЛИЗАЦИЯ..."}])

@app.route('/api/densities')
def get_densities_data():
    start_scanner(); ex = request.args.get('exchange', 'bingx')
    return jsonify(latest_data.get(ex, latest_data['bingx'])['densities'] or [{"ticker": "ИНИЦИАЛИЗАЦИЯ..."}])

@app.route('/api/arbitrage')
def get_arbitrage_data():
    start_scanner(); ex = request.args.get('exchange', 'bingx')
    return jsonify(latest_data.get(ex, latest_data['bingx'])['arbitrage'] or [{"ticker": "ИНИЦИАЛИЗАЦИЯ..."}])

@app.route('/api/search')
def search_ticker():
    ticker = request.args.get('ticker')
    ex_name = request.args.get('exchange', 'bingx')
    if not ticker: return jsonify({"error": "Введите тикер"}), 400
    ticker = ticker.upper().strip()
    if not ticker.endswith('USDT'): ticker += '/USDT'
    elif not ticker.endswith('/USDT') and ticker.endswith('USDT'): ticker = ticker.replace('USDT', '/USDT')
    try:
        orderbook = exchanges_spot[ex_name].fetch_order_book(ticker, limit=50)
        bids, asks = orderbook['bids'], orderbook['asks']
        if not bids or not asks: return jsonify({"error": "Стакан пуст"}), 404
        cp = (bids[0][0] + asks[0][0]) / 2
        spr = ((asks[0][0] - bids[0][0]) / bids[0][0]) * 100
        nb = next(((p, p*a) for p, a in bids if p * a >= 1000), None)
        na = next(((p, p*a) for p, a in asks if p * a >= 1000), None)
        return jsonify({"ticker": ticker, "price": cp, "spread": f"{spr:.2f}%", "nearest_bid": {"price": nb[0], "vol": int(nb[1])} if nb else None, "nearest_ask": {"price": na[0], "vol": int(na[1])} if na else None})
    except: return jsonify({"error": "Монета не найдена"}), 404

if __name__ == '__main__': app.run(host='0.0.0.0', port=10000)
