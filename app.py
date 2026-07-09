import time
import requests
import re
from flask import Flask, render_template_string, request, Response, stream_with_context

app = Flask(__name__)

# Chess.com requires a descriptive User-Agent header
HEADERS = {"User-Agent": "FreeBrilliantWebTool/1.0 (contact: your_email@example.com)"}

# Single-file HTML interface design
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Chess.com Brilliant Move Scanner</title>
    <style>
        body { font-family: monospace; background: #121212; color: #00ff00; padding: 40px; }
        .container { max-width: 600px; margin: 0 auto; border: 1px solid #00ff00; padding: 20px; }
        input, button { background: #000; color: #00ff00; border: 1px solid #00ff00; padding: 8px; font-family: monospace; }
        button { cursor: pointer; }
        #output { margin-top: 20px; white-space: pre-wrap; background: #000; pading: 10px; border: 1px dashed #00ff00; height: 300px; overflow-y: scroll; padding: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Brilliant Move Counter</h2>
        <p>Enter your username to fetch archives and estimate run time.</p>
        
        <input type="text" id="username" placeholder="Chess.com Username">
        <button onclick="checkEstimation()">Check Estimated Time</button>
        <button onclick="startScan()">Start Scan</button>
        
        <div id="estimation" style="margin-top: 15px; color: #ffff00;"></div>
        <div id="output">Console output will appear here...</div>
    </div>

    <script>
        // Check estimated time before running the scan
        async function checkEstimation() {
            const user = document.getElementById('username').value;
            if (!user) return alert('Enter a username first');
            
            const response = await fetch(`/estimate?username=${user}`);
            const data = await response.json();
            
            if (data.error) {
                document.getElementById('estimation').innerText = "Error: Player not found.";
            } else {
                document.getElementById('estimation').innerText = 
                    `Found ${data.months} months of game history. Estimated Scan Time: ~${data.estimated_seconds} seconds.`;
            }
        }

        // Connect to the streaming backend to display live console output
        function startScan() {
            const user = document.getElementById('username').value;
            if (!user) return alert('Enter a username first');
            
            const outputDiv = document.getElementById('output');
            outputDiv.innerText = "Connecting to API...\\n";
            
            const eventSource = new EventSource(`/scan?username=${user}`);
            
            eventSource.onmessage = function(event) {
                outputDiv.innerText += event.data + "\\n";
                outputDiv.scrollTop = outputDiv.scrollHeight; // Auto-scroll
                
                if (event.data.includes("--- Scan Complete ---")) {
                    eventSource.close();
                }
            };

            eventSource.onerror = function() {
                outputDiv.innerText += "\\nAn error occurred or connection closed.";
                eventSource.close();
            };
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/estimate')
def estimate():
    username = request.args.get('username', '').strip()
    url = f"https://chess.com{username}/games/archives"
    res = requests.get(url, headers=HEADERS)
    
    if res.status_code != 200:
        return {"error": "User not found"}, 400
        
    archives = res.json().get("archives", [])
    num_months = len(archives)
    
    # Estimate roughly 0.5 seconds per month calculation (downloading + processing time)
    estimated_seconds = round(num_months * 0.5)
    
    return {"months": num_months, "estimated_seconds": max(estimated_seconds, 1)}

@app.route('/scan')
def scan():
    username = request.args.get('username', '').strip()
    
    def generate_scan_progress():
        url = f"https://chess.com{username}/games/archives"
        res = requests.get(url, headers=HEADERS)
        if res.status_code != 200:
            yield "data: Error connecting to Chess.com API.\n\n"
            return
            
        archives = res.json().get("archives", [])
        total_brilliant = 0
        total_games_scanned = 0
        
        yield f"data: Starting scan across {len(archives)} history logs...\n\n"
        
        for idx, archive_url in enumerate(archives):
            time.sleep(0.15) # Safe gap to prevent Chess.com from blocking requests
            month_res = requests.get(archive_url, headers=HEADERS)
            if month_res.status_code != 200:
                continue
                
            games = month_res.json().get("games", [])
            total_games_scanned += len(games)
            
            month_brilliants = 0
            for game in games:
                if "pgn" in game:
                    # Look for standard Chess.com brilliant tags (!! or PGN $3 code)
                    brilliants = len(re.findall(r'(\!\!|\$3)', game["pgn"]))
                    month_brilliants += brilliants
                    total_brilliant += brilliants
            
            # Send live text chunks to the browser log window
            month_name = archive_url.split('/')[-2] + "-" + archive_url.split('/')[-1]
            yield f"data: [{idx+1}/{len(archives)}] Processed {month_name} (+{month_brilliants} brilliant moves found)\n\n"

        yield "data: \n\n"
        yield "data: --- Scan Complete ---\n\n"
        yield f"data: Total Games Scanned: {total_games_scanned}\n\n"
        yield f"data: Total Brilliant Moves: {total_brilliant}\n\n"

    return Response(stream_with_context(generate_scan_progress()), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
