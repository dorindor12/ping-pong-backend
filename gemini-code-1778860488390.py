<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Crypto Scanner | Ping-Pong</title>
    <style>
        body { background-color: #121212; color: #ffffff; font-family: monospace; padding: 20px; }
        .header { border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; display: flex; justify-content: space-between; }
        .tab.active { background-color: #00ffcc; color: #000; padding: 10px 20px; border-radius: 5px; font-weight: bold; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #333; padding: 12px; text-align: left; }
        th { background-color: #1a1a1a; color: #888; }
        .status-online { color: #00ffcc; font-size: 0.8em; font-weight: bold; }
    </style>
</head>
<body>
    <div class="header">
        <div class="tab active">Ping-Pong (BingX)</div>
        <div id="api-status" class="status-online">CONNECTING TO API...</div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Тикер</th><th>Спред (%)</th><th>Покупка (Низ)</th><th>Продажа (Верх)</th><th>Касаний</th><th>Объем ($)</th>
            </tr>
        </thead>
        <tbody id="data-table"></tbody>
    </table>

    <script>
        // https://ping-pong-backend-yhro.onrender.com /api/ping-pong !!!
        const API_URL = "https://https://ping-pong-backend-yhro.onrender.com
        async function updateData() {
            try {
                const response = await fetch(API_URL);
                const data = await response.json();
                const tableBody = document.getElementById('data-table');
                
                tableBody.innerHTML = '';
                data.forEach(row => {
                    tableBody.innerHTML += `<tr><td>${row.ticker}</td><td>${row.spread}</td><td>${row.low}</td><td>${row.high}</td><td>${row.hits}</td><td>${row.vol}</td></tr>`;
                });
                document.getElementById('api-status').innerText = "STATUS: [SYSTEM_ONLINE]";
                document.getElementById('api-status').style.color = "#00ffcc";
            } catch (error) {
                document.getElementById('api-status').innerText = "STATUS: [CONNECTION_ERROR]";
                document.getElementById('api-status').style.color = "red";
            }
        }
        updateData();
        setInterval(updateData, 5000);
    </script>
</body>
</html>
