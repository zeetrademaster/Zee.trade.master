import os
from flask import Flask, jsonify, send_from_directory

app = Flask(__name__, static_folder=".")

@app.route("/health")
def health():
    return jsonify({"ok": True, "app": "ZEE TRADE MASTER", "source": "TradingView Live Widgets"})

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(".", path)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"ZEE TRADE MASTER (TradingView Live) running at http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port)
