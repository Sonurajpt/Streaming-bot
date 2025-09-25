# proxy.py
# Requirements: flask, requests
# This is a streaming proxy endpoint. It includes basic SSRF protection.

import os
import logging
import socket
from urllib.parse import urlparse, unquote_plus
from flask import Flask, request, Response, stream_with_context, jsonify
import requests

# --- config ---
PORT = int(os.environ.get("PORT", 5000))
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
REQUEST_TIMEOUT = 20  # seconds
MAX_CONTENT_LENGTH = 1024 * 1024 * 1024  # 1GB safety cap (adjust as needed)

# --- logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("terabox-proxy")

app = Flask(__name__)

# --- Basic SSRF protection: disallow requests to private IP ranges and loopback ---
def is_private_ip(hostname: str) -> bool:
    try:
        ip = socket.gethostbyname(hostname)
    except Exception:
        # could not resolve: be conservative and treat as not private
        return False
    # IPv4 local ranges
    private_prefixes = ("10.", "127.", "169.254.", "172.", "192.168.")
    if ip.startswith(("127.", "10.", "169.254.", "192.168.")):
        return True
    # 172.16.0.0 — 172.31.255.255
    if ip.startswith("172."):
        try:
            second_octet = int(ip.split(".")[1])
            if 16 <= second_octet <= 31:
                return True
        except Exception:
            pass
    # IPv6 loopback (simple check)
    if ip == "::1":
        return True
    return False

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/proxy")
def proxy():
    raw_url = request.args.get("url")
    if not raw_url:
        return "Missing url parameter", 400

    # allow encoded urls
    try:
        url = unquote_plus(raw_url)
    except Exception:
        url = raw_url

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "Only http/https URLs are allowed", 400

    # SSRF check: disallow private IPs
    hostname = parsed.hostname or ""
    if is_private_ip(hostname):
        logger.warning("Blocked request to private IP/hostname: %s -> %s", hostname, url)
        return "Blocked access to private/internal addresses", 403

    headers = {
        "User-Agent": USER_AGENT,
        # optionally forward certain incoming headers if useful
    }

    try:
        # stream the remote content
        r = requests.get(url, headers=headers, stream=True, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logger.warning("Error fetching url %s: %s", url, e)
        return f"Error fetching url: {e}", 502

    # protect huge downloads (safety)
    content_length = r.headers.get("content-length")
    if content_length:
        try:
            cl = int(content_length)
            if cl > MAX_CONTENT_LENGTH:
                r.close()
                return "File too large to proxy", 413
        except Exception:
            pass

    # build streaming response
    def generate():
        try:
            for chunk in r.iter_content(chunk_size=1024 * 16):
                if chunk:
                    yield chunk
        finally:
            r.close()

    # attempt to forward content-type, content-length and range support
    headers_out = {}
    if "content-type" in r.headers:
        headers_out["Content-Type"] = r.headers["content-type"]
    if "content-length" in r.headers:
        headers_out["Content-Length"] = r.headers["content-length"]
    # Pass-through Accept-Ranges and status code 200
    return Response(stream_with_context(generate()), headers=headers_out)

if __name__ == "__main__":
    logger.info("Starting proxy on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT)
