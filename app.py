import os
import time
import asyncio
from flask import Flask, request, jsonify
from pyppeteer import launch
import requests

app = Flask(__name__)

# caches
INDEX_CACHE = {}
EQUITY_COOKIE_CACHE = {'cookie': None, 'ts': 0}
EQUITY_CACHE = {}

# TTLs
INDEX_TTL = 30
COOKIE_TTL = 300
EQUITY_TTL = 30

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.nseindia.com/option-chain',
}

API_KEY = os.environ.get('API_KEY', '')  # optional security

def check_key():
    key = request.args.get('key') or request.headers.get('x-api-key')
    if API_KEY and key != API_KEY:
        return False
    return True

@app.route('/nse-index')
def nse_index():
    if not check_key():
        return jsonify({'error':'unauthorized'}), 401
    symbol = (request.args.get('symbol') or 'NIFTY').upper()
    now = time.time()
    if symbol in INDEX_CACHE and now - INDEX_CACHE[symbol]['ts'] < INDEX_TTL:
        return jsonify(INDEX_CACHE[symbol]['data'])
    url = f'https://www.nseindia.com/api/option-chain-indices?symbol={symbol}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        INDEX_CACHE[symbol] = {'data': data, 'ts': now}
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

async def _get_cookies():
    browser = await launch(
        headless=True,
        executablePath="/usr/bin/chromium",
        args=["--no-sandbox","--disable-dev-shm-usage"]
    )
    page = await browser.newPage()
    await page.goto('https://www.nseindia.com', {'waitUntil':'networkidle2'})
    await asyncio.sleep(1)
    cookies = await page.cookies()
    await browser.close()
    return '; '.join([f"{c['name']}={c['value']}" for c in cookies])

def get_cookie_blocking():
    now = time.time()
    if EQUITY_COOKIE_CACHE['cookie'] and now - EQUITY_COOKIE_CACHE['ts'] < COOKIE_TTL:
        return EQUITY_COOKIE_CACHE['cookie']
    cookie = asyncio.get_event_loop().run_until_complete(_get_cookies())
    EQUITY_COOKIE_CACHE['cookie'] = cookie
    EQUITY_COOKIE_CACHE['ts'] = now
    return cookie

def fetch_equity(symbol, cookie):
    url = f'https://www.nseindia.com/api/option-chain-equities?symbol={symbol}'
    headers = dict(HEADERS)
    headers['Cookie'] = cookie
    headers['X-Requested-With'] = 'XMLHttpRequest'
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()

@app.route('/nse-equity')
def nse_equity():
    if not check_key():
        return jsonify({'error':'unauthorized'}), 401
    symbol = (request.args.get('symbol') or 'INFY').upper()
    now = time.time()
    if symbol in EQUITY_CACHE and now - EQUITY_CACHE[symbol]['ts'] < EQUITY_TTL:
        return jsonify(EQUITY_CACHE[symbol]['data'])
    try:
        cookie = get_cookie_blocking()
        data = fetch_equity(symbol, cookie)
        EQUITY_CACHE[symbol] = {'data': data, 'ts': now}
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',8080)))
