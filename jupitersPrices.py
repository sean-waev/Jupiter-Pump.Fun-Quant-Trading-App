import random
import requests
import time
import threading
import queue
import warnings
import json
import math
import socket
import sys
import concurrent.futures
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from multiprocessing.managers import BaseManager
from datetime import datetime, timedelta
from collections import defaultdict, deque
from bisect import bisect_left
from urllib.parse import quote

# Disable warnings
warnings.filterwarnings("ignore")

# Configuration
UPDATE_INTERVAL = 3.0  # Target cycle time
TOKEN_CHUNK_SIZE = 99   # Max tokens per API call
MAX_TOKENS = 1500      # Support 20,000 tokens
MAX_RETRIES = 2         # Reduced retries for speed
MAX_HISTORY_HOURS = 24  # 24 hours price history
MIN_HISTORY_FOR_CHANGES = 2
JSON_OUTPUT_FILE = 'token_prices.json'
API_CALL_DELAY = 0.04   # 40ms between API calls
API_TIMEOUT = 10        # Reduced timeout
MAX_WORKERS = 50        # Thread pool size for parallel processing

# SOCKS5 Proxy Configuration
PROXY_USERNAME = "72dbb58e5f3bc021aebe"
PROXY_PASSWORD = "af48baf3f0c8ef0b"
PROXY_HOST = "gw.dataimpulse.com"
PROXY_PORT = 824

# Time intervals for price changes
TIME_INTERVALS = {
    '2s': 2, '5s': 5, '10s': 10, '30s': 30,
    '1m': 60, '2m': 120, '5m': 300, '10m': 600
}

# Jupiter API
JUPITER_API_URL = 'https://lite-api.jup.ag/price/v2'

class QueueManager(BaseManager): pass

# Global variables
price_data = {}
price_history = defaultdict(deque)
token_queue = queue.Queue()
data_lock = threading.Lock()
active_tokens = set()
stop_event = threading.Event()
last_api_call_time = 0
api_call_lock = threading.Lock()
pending_tokens = set()
token_retry_counts = defaultdict(int)

class ProxyManager:
    """Handles SOCKS5 proxy configuration for API calls"""
    def __init__(self):
        self.proxy_configured = False
        self.setup_proxy()

    def setup_proxy(self):
        """Configure SOCKS5 proxy for API calls"""
        try:
            try:
                import socks
                self.socks_module = socks
            except ImportError:
                try:
                    import PySocks as socks
                    self.socks_module = socks
                except ImportError:
                    import pysocks as socks
                    self.socks_module = socks
            self.proxy_configured = True
        except Exception as e:
            print(f"⚠ Proxy configuration warning: {str(e)}")

    def get_session(self):
        """Return a requests session with proxy configuration"""
        session = requests.Session()
        if self.proxy_configured:
            encoded_username = quote(PROXY_USERNAME)
            encoded_password = quote(PROXY_PASSWORD)
            proxy_url = f"socks5://{encoded_username}:{encoded_password}@{PROXY_HOST}:{PROXY_PORT}"
            session.proxies = {'http': proxy_url, 'https': proxy_url}
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=0.5,  # Reduced backoff for speed
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            respect_retry_after_header=False  # Disabled for speed
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=100,
            pool_maxsize=100,
            pool_block=False  # Non-blocking pool
        )
        session.mount("https://", adapter)
        return session

# Initialize proxy manager and thread pool
proxy_manager = ProxyManager()
executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)

def connect_to_manager():
    """Connect to multiprocessing manager without proxy"""
    original_socket = socket.socket
    if 'socks' in sys.modules:
        socket.socket = original_socket
    
    try:
        QueueManager.register('get_queue')
        QueueManager.register('get_json_queue')
        QueueManager.register('get_stop_event')
        manager = QueueManager(address=('localhost', 50000), authkey=b'abc123')
        manager.connect()
        return manager.get_queue(), manager.get_json_queue(), manager.get_stop_event()
    except Exception as e:
        print(f"❌ Queue manager error: {str(e)}")
        return None, None, None
    finally:
        socket.socket = original_socket

def interpolate_price(history, target_time):
    """Optimized price interpolation"""
    if not history:
        return None
        
    history_list = list(history)
    timestamps = [point[0] for point in history_list]
    pos = bisect_left(timestamps, target_time)
    
    if pos == 0:
        return history_list[0][1]
    if pos == len(timestamps):
        return history_list[-1][1]
    
    t_prev, p_prev = history_list[pos-1]
    t_next, p_next = history_list[pos]
    
    if t_next == t_prev:
        return p_prev
    
    factor = (target_time - t_prev).total_seconds() / (t_next - t_prev).total_seconds()
    return p_prev + factor * (p_next - p_prev)

def calculate_percentage_changes(token_id, current_price, current_time):
    """Optimized percentage change calculation"""
    changes = {interval: math.nan for interval in TIME_INTERVALS}
    
    try:
        history = price_history.get(token_id, deque())
        if not history:
            return changes
            
        oldest_time = history[0][0]
        
        for interval, seconds in TIME_INTERVALS.items():
            if (current_time - oldest_time).total_seconds() < seconds:
                continue
                
            target_time = current_time - timedelta(seconds=seconds)
            historical_price = interpolate_price(history, target_time)
            
            if historical_price and historical_price > 0:
                changes[interval] = ((current_price - historical_price) / historical_price) * 100
    except Exception:
        pass
    
    return changes

def cleanup_old_history():
    """Optimized history cleanup"""
    cutoff_time = datetime.now() - timedelta(hours=MAX_HISTORY_HOURS)
    with data_lock:
        for token_id in list(price_history.keys()):
            while price_history[token_id] and price_history[token_id][0][0] < cutoff_time:
                price_history[token_id].popleft()
            
            if not price_history[token_id]:
                del price_history[token_id]

def fetch_token_prices_batch(token_ids):
    """Fetch prices for a batch of tokens with minimal overhead"""
    if not token_ids:
        return {}
    
    # Enforce minimum delay between API calls
    global last_api_call_time
    with api_call_lock:
        current_time = time.time()
        elapsed = current_time - last_api_call_time
        if elapsed < API_CALL_DELAY:
            time.sleep(API_CALL_DELAY - elapsed)
        last_api_call_time = time.time()
    
    try:
        session = proxy_manager.get_session()
        params = {'ids': ','.join(token_ids)}
        response = session.get(
            JUPITER_API_URL,
            params=params,
            timeout=API_TIMEOUT,
            headers={'User-Agent': 'JupiterPriceTracker/4.0'}
        )
        
        if response.status_code != 200:
            return None
        
        data = response.json().get('data', {})
        return {
            token_id: {
                'price': token_data['price'],
                'symbol': token_data.get('symbol', token_id[:4] + '...'),
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
            for token_id, token_data in data.items()
            if 'price' in token_data and token_data['price'] != '0'
        }
    except Exception:
        return None

def process_token_chunk(chunk):
    """Process a chunk of tokens in parallel"""
    chunk_data = fetch_token_prices_batch(chunk)
    if not chunk_data:
        return 0
    
    current_time = datetime.now()
    updated_count = 0
    
    with data_lock:
        for token_id, data in chunk_data.items():
            try:
                price = float(data['price'])
                if price <= 0:
                    continue
                    
                price_data[token_id] = data
                price_history[token_id].append((current_time, price))
                updated_count += 1
            except (ValueError, KeyError):
                continue
    
    return updated_count

def update_all_prices():
    """Update all token prices in parallel"""
    with data_lock:
        current_tokens = list(active_tokens)
    
    if not current_tokens:
        return 0
    
    # Split into chunks for parallel processing
    token_chunks = [current_tokens[i:i+TOKEN_CHUNK_SIZE] 
                   for i in range(0, len(current_tokens), TOKEN_CHUNK_SIZE)]
    
    # Process chunks in parallel
    futures = [executor.submit(process_token_chunk, chunk) for chunk in token_chunks]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    return sum(results)

def write_to_json(data):
    """Optimized JSON writing"""
    try:
        with open(JSON_OUTPUT_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def prepare_output_data(current_tokens):
    """Prepare output data efficiently"""
    output_data = []
    current_time = datetime.now()
    
    for token_id in current_tokens:
        data = price_data.get(token_id)
        if not data:
            continue
            
        try:
            current_price = float(data.get('price', 0))
            if current_price <= 0:
                continue
                
            changes = calculate_percentage_changes(token_id, current_price, current_time)
            
            output_data.append({
                "token": token_id[:8],
                "price": current_price,
                "t_2s": None if math.isnan(changes['2s']) else round(changes['2s'], 2),
                "t_5s": None if math.isnan(changes['5s']) else round(changes['5s'], 2),
                "t_10s": None if math.isnan(changes['10s']) else round(changes['10s'], 2),
                "t_30s": None if math.isnan(changes['30s']) else round(changes['30s'], 2),
                "t_1m": None if math.isnan(changes['1m']) else round(changes['1m'], 2),
                "t_2m": None if math.isnan(changes['2m']) else round(changes['2m'], 2),
                "t_5m": None if math.isnan(changes['5m']) else round(changes['5m'], 2),
                "t_10m": None if math.isnan(changes['10m']) else round(changes['10m'], 2),
                "id": token_id,
                "time": data.get('timestamp', '')
            })
        except Exception:
            continue
    
    return output_data

def print_console_output(output_data):
    """Print formatted console output"""
    print("\n" + "="*180)
    header = f"{'Token':<8} {'Price':<15} {'2s':<8} {'5s':<8} {'10s':<8} {'30s':<8} {'1m':<8} {'2m':<8} {'5m':<8} {'10m':<8} {'ID':<50} {'Time':<8}"
    print(header)
    print("-"*180)
    
    for item in output_data:
        # Create formatted strings for each change value first
        t_2s = 'N/A' if item['t_2s'] is None else f"{item['t_2s']:.2f}%"
        t_5s = 'N/A' if item['t_5s'] is None else f"{item['t_5s']:.2f}%"
        t_10s = 'N/A' if item['t_10s'] is None else f"{item['t_10s']:.2f}%"
        t_30s = 'N/A' if item['t_30s'] is None else f"{item['t_30s']:.2f}%"
        t_1m = 'N/A' if item['t_1m'] is None else f"{item['t_1m']:.2f}%"
        t_2m = 'N/A' if item['t_2m'] is None else f"{item['t_2m']:.2f}%"
        t_5m = 'N/A' if item['t_5m'] is None else f"{item['t_5m']:.2f}%"
        t_10m = 'N/A' if item['t_10m'] is None else f"{item['t_10m']:.2f}%"
        
        line = (f"{item['token']:<8} {item['price']:<15.8f} "
               f"{t_2s:<8} {t_5s:<8} {t_10s:<8} {t_30s:<8} "
               f"{t_1m:<8} {t_2m:<8} {t_5m:<8} {t_10m:<8} "
               f"{item['id']:<50} {item['time']:<8}")
        print(line)
    
    print("="*180)

def process_new_tokens():
    """Process new tokens in parallel"""
    while not stop_event.is_set():
        try:
            coin = token_queue.get(timeout=0.1)
            mint = coin['mint'].replace('-latest', '')
            
            with data_lock:
                if mint in active_tokens or mint in pending_tokens:
                    continue
                    
                if len(active_tokens) >= MAX_TOKENS:
                    # Remove oldest token
                    if not active_tokens:
                        continue
                    oldest_token = min(
                        active_tokens,
                        key=lambda x: price_history[x][-1][0] if price_history.get(x) else datetime.min
                    )
                    active_tokens.remove(oldest_token)
                    price_data.pop(oldest_token, None)
                    price_history.pop(oldest_token, None)
                
                pending_tokens.add(mint)
                token_retry_counts[mint] = token_retry_counts.get(mint, 0) + 1
                
                if token_retry_counts[mint] > 6:
                    pending_tokens.discard(mint)
                    token_retry_counts.pop(mint, None)
                    continue
            
            # Process token addition in parallel
            executor.submit(process_single_token, mint)
            
        except queue.Empty:
            continue
        except Exception:
            continue

def process_single_token(mint):
    """Process a single token addition"""
    price_data = fetch_token_prices_batch([mint])
    if not price_data or mint not in price_data:
        with data_lock:
            pending_tokens.discard(mint)
            if token_retry_counts.get(mint, 0) <= 2:
                token_queue.put({'mint': mint + '-latest'})
        return
    
    try:
        price = float(price_data[mint]['price'])
        with data_lock:
            active_tokens.add(mint)
            price_history[mint].append((datetime.now(), price))
            pending_tokens.discard(mint)
            token_retry_counts.pop(mint, None)
    except Exception:
        with data_lock:
            pending_tokens.discard(mint)

def update_price_data(json_queue):
    """Main data processing loop with parallel execution"""
    while not stop_event.is_set():
        start_time = time.time()
        
        # Clean up old history occasionally
        if random.random() < 0.05:
            cleanup_old_history()
        
        # Update all prices in parallel
        updated_count = update_all_prices()
        
        if updated_count > 0:
            with data_lock:
                current_tokens = list(active_tokens)
            
            output_data = prepare_output_data(current_tokens)
            
            # Print to console
            print_console_output(output_data)
            
            # Write to JSON
            write_to_json(output_data)
            
            # Send to queue if available
            if json_queue:
                try:
                    json_queue.put(output_data)
                except Exception:
                    pass
        
        # Adjust sleep time based on actual processing time
        elapsed = time.time() - start_time
        sleep_time = max(0.1, UPDATE_INTERVAL - elapsed)
        time.sleep(sleep_time)

def queue_consumer():
    """Optimized queue consumer"""
    mp_queue, json_queue, mp_stop_event = connect_to_manager()
    if mp_queue is None:
        stop_event.set()
        return
    
    while not stop_event.is_set():
        try:
            coin = mp_queue.get(timeout=0.1)
            token_queue.put(coin)
        except queue.Empty:
            continue
        except Exception:
            if stop_event.is_set():
                break
            time.sleep(0.1)

def main():
    print("🚀 Starting Jupiter Price Tracker (High Performance)")
    
    _, json_queue, _ = connect_to_manager()
    
    threads = [
        threading.Thread(target=queue_consumer, daemon=True),
        threading.Thread(target=process_new_tokens, daemon=True),
        threading.Thread(target=update_price_data, args=(json_queue,), daemon=True)
    ]
    
    for t in threads:
        t.start()
    
    try:
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutdown signal received")
    finally:
        stop_event.set()
        executor.shutdown(wait=False)
        for t in threads:
            t.join(timeout=1)
        print("🧹 Cleanup complete")

if __name__ == "__main__":
    main()