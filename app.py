#!/usr/bin/env python3
"""
ZEE TRADE MASTER — Cloud (Render.com) & Local Wi-Fi Live PSX Server
Zero external dependencies (100% Python 3 standard library).
- On Render.com: automatically reads PORT env var and binds to 0.0.0.0
- On PC / Mac: runs on http://127.0.0.1:8765 and also accessible on local Wi-Fi!
"""

import http.server
import json
import os
import re
import socket
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8765"))
IS_CLOUD = bool(os.environ.get("RENDER") or os.environ.get("PORT"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(BASE_DIR, "index.html")
MANIFEST_FILE = os.path.join(BASE_DIR, "manifest.json")
ICON_FILE = os.path.join(BASE_DIR, "icon.svg")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}

_CACHE = {"ts": 0.0, "data": None}
_CACHE_LOCK = threading.Lock()
CACHE_TTL = 20.0


def _clean_num(val):
    if val is None:
        return None
    s = re.sub(r"[^\d.\-]", "", str(val).replace(",", ""))
    if not s or s in ("-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fetch_url(url, timeout=14):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_psx_live_snapshot():
    now = time.time()
    with _CACHE_LOCK:
        if _CACHE["data"] is not None and (now - _CACHE["ts"]) < CACHE_TTL:
            return _CACHE["data"]

    stocks = {}
    indices = []

    try:
        html = _fetch_url("https://dps.psx.com.pk/market-watch", timeout=15)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S | re.I)
        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)
            if len(cells) < 10:
                continue
            clean_cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in cells]
            sym_m = re.match(r"^([A-Z0-9]{2,14})\b", clean_cells[0].upper())
            if not sym_m:
                continue
            sym = sym_m.group(1)
            ldcp = _clean_num(clean_cells[3])
            op = _clean_num(clean_cells[4])
            hi = _clean_num(clean_cells[5])
            lo = _clean_num(clean_cells[6])
            cur = _clean_num(clean_cells[7])
            chg = _clean_num(clean_cells[8])
            pct = _clean_num(clean_cells[9])
            vol = _clean_num(clean_cells[10]) if len(clean_cells) > 10 else 0
            if cur is not None and cur > 0:
                stocks[sym] = {
                    "ldcp": ldcp if ldcp is not None else cur,
                    "open": op if op is not None else cur,
                    "high": hi if hi is not None else cur,
                    "low": lo if lo is not None else cur,
                    "close": cur,
                    "change": chg if chg is not None else 0.0,
                    "pct": pct if pct is not None else 0.0,
                    "vol": int(vol) if vol is not None else 0,
                }
    except Exception as e:
        print(f"[WARN] PSX Market Watch fetch: {e}")

    try:
        idx_html = _fetch_url("https://dps.psx.com.pk/indices", timeout=12)
        idx_rows = re.findall(r"<tr[^>]*>(.*?)</tr>", idx_html, flags=re.S | re.I)
        for row in idx_rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)
            if len(cells) < 5:
                continue
            clean_cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in cells]
            name = clean_cells[0].upper().replace(" ", "")
            val = _clean_num(clean_cells[3]) if len(clean_cells) > 3 else None
            chg = _clean_num(clean_cells[4]) if len(clean_cells) > 4 else 0.0
            pct = _clean_num(clean_cells[5]) if len(clean_cells) > 5 else 0.0
            if name and val and val > 100:
                indices.append({"name": name, "value": val, "change": chg or 0.0, "pct": pct or 0.0})
    except Exception as e:
        print(f"[WARN] PSX Indices fetch: {e}")

    # Pakistan Standard Time (UTC+5)
    pkt_ts = time.time() + 5 * 3600
    pkt_str = datetime.utcfromtimestamp(pkt_ts).strftime("%H:%M:%S PKT")

    payload = {
        "ok": True,
        "count": len(stocks),
        "time": pkt_str,
        "stocks": stocks,
        "indices": indices,
    }
    with _CACHE_LOCK:
        _CACHE["ts"] = now
        _CACHE["data"] = payload
    return payload


class ZeeTradeMasterHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200, cache_ctrl: str = "no-store"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_ctrl)
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html", "/PSX_All_570_Companies_6Chart_Scanner.html"):
            if os.path.exists(HTML_FILE):
                with open(HTML_FILE, "rb") as f:
                    self._send_bytes(f.read(), "text/html; charset=utf-8")
            else:
                self._send_bytes(b"index.html not found.", "text/plain", 404)
            return

        if path == "/manifest.json" and os.path.exists(MANIFEST_FILE):
            with open(MANIFEST_FILE, "rb") as f:
                self._send_bytes(f.read(), "application/manifest+json; charset=utf-8", cache_ctrl="public, max-age=3600")
            return

        if path == "/icon.svg" and os.path.exists(ICON_FILE):
            with open(ICON_FILE, "rb") as f:
                self._send_bytes(f.read(), "image/svg+xml", cache_ctrl="public, max-age=3600")
            return

        if path == "/health":
            self._send_bytes(b'{"status":"ok","app":"ZEE TRADE MASTER"}', "application/json")
            return

        if path == "/api/psx-live":
            data = fetch_psx_live_snapshot()
            self._send_bytes(json.dumps(data).encode("utf-8"), "application/json; charset=utf-8")
            return

        if path.startswith("/api/psx-eod/"):
            sym = re.sub(r"[^A-Z0-9]", "", path.split("/")[-1].upper())
            try:
                raw = _fetch_url(f"https://dps.psx.com.pk/timeseries/eod/{sym}", timeout=12)
                self._send_bytes(raw.encode("utf-8"), "application/json; charset=utf-8")
            except Exception as e:
                self._send_bytes(json.dumps({"error": str(e), "data": []}).encode("utf-8"), "application/json", 502)
            return

        self._send_bytes(b"Not Found", "text/plain", 404)


def _get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    httpd = http.server.ThreadingHTTPServer((HOST, PORT), ZeeTradeMasterHandler)
    print("=" * 62)
    print("   ZEE TRADE MASTER — LIVE PSX SERVER (PC + MOBILE)")
    print("=" * 62)
    if IS_CLOUD:
        print(f"   Running in Cloud Mode on 0.0.0.0:{PORT}")
    else:
        lan_ip = _get_lan_ip()
        print(f"   PC URL     : http://127.0.0.1:{PORT}/")
        print(f"   Mobile URL : http://{lan_ip}:{PORT}/  (Same Wi-Fi)")
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}/")).start()
    print("=" * 62)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nZEE TRADE MASTER server stopped cleanly.")


if __name__ == "__main__":
    main()
