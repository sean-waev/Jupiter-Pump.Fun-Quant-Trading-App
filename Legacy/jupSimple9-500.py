import requests
import time
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from collections import defaultdict
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
import threading
import queue
import warnings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
warnings.filterwarnings("ignore")

# Configuration
UPDATE_INTERVAL = 2  # Increased from 5 to 30 seconds to reduce API calls
MAX_DATA_POINTS = 60  # Reduced history to match new interval
TOKEN_CHUNK_SIZE = 100  # Reduced from 100 to stay under rate limits
TOKENS_PER_WINDOW = 100  # Charts per window
MAX_TOKENS = 500  # Reduced from 500 to stay under rate limits (adjust as needed)
TOKEN_IDS = [
'So11111111111111111111111111111111111111112'       , #15:02:26

             ]  # Your 500 token IDs here


# API Rate Limit Configuration
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
MAX_WORKERS = 3  # Reduced concurrent requests

# Data storage
price_history = defaultdict(list)
time_history = []
start_time = None
data_lock = threading.Lock()
plot_queue = queue.Queue()

# Configure requests session with retry strategy
session = requests.Session()
retry_strategy = Retry(
    total=MAX_RETRIES,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)

class TokenTracker:
    def __init__(self, root, token_chunk, window_num):
        self.should_close = False
        self.root = root
        self.token_chunk = token_chunk
        self.window_num = window_num
        
        self.root.title(f"Crypto Tracker - Window {window_num}")
        self.root.protocol("WM_DELETE_WINDOW", self.safe_close)
        
        matplotlib.use('TkAgg', force=True)
        
        self.rows = 10
        self.cols = 10
        self.fig, self.axs = plt.subplots(
            self.rows, self.cols,
            figsize=(24, 16),
            tight_layout=True,
            dpi=80
        )
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        
        self.status = tk.StringVar()
        tk.Label(self.root, textvariable=self.status, font=('Arial', 8)).pack(side=tk.BOTTOM)
        self.update_status("Initializing...")
        
        self.initialize_plots()
        self.root.after(100, self.process_queue)
    
    def process_queue(self):
        try:
            while not plot_queue.empty():
                task = plot_queue.get_nowait()
                if task[0] == self.window_num:
                    self._update_plots(task[1])
        except queue.Empty:
            pass
        if not self.should_close:
            self.root.after(100, self.process_queue)
    
    def safe_close(self):
        self.should_close = True
        self.root.quit()
        self.root.destroy()
    
    def update_status(self, message):
        if not self.should_close:
            self.status.set(f"Window {self.window_num} - {message}")
    
    def initialize_plots(self):
        for i, ax in enumerate(self.axs.flatten()):
            if i < len(self.token_chunk):
                token_id = self.token_chunk[i]
                ax.set_title(f"{token_id[:4]}...", fontsize=6, pad=1)
                ax.tick_params(axis='both', which='major', labelsize=4)
                ax.grid(True, alpha=0.3)
            else:
                ax.axis('off')
        
        self.fig.suptitle(f"Token Group {self.window_num}", fontsize=10, y=0.99)
        self.canvas.draw()
    
    def _update_plots(self, price_data):
        if self.should_close or not price_data:
            return
            
        try:
            times = [(t - start_time).total_seconds() for t in time_history[-60:]]
            
            for i, ax in enumerate(self.axs.flatten()):
                if i >= len(self.token_chunk):
                    continue
                
                token_id = self.token_chunk[i]
                ax.clear()
                
                if token_id in price_history and len(price_history[token_id]) > 0:
                    prices = price_history[token_id][-60:]
                    token_info = price_data.get(token_id) or {}  # Ensures we always get a dictionary
                    name = (token_info.get('symbol') if token_info else token_id[:4] + '...')
                    
                    ax.plot(times, prices, 'b-', linewidth=0.5)
                    ax.set_title(f"{name}", fontsize=6, pad=1)
                    ax.tick_params(axis='both', which='major', labelsize=4)
                    ax.grid(True, alpha=0.3)
                    
                    if len(prices) > 0:
                        valid_prices = [p for p in prices if p > 0]
                        if valid_prices:
                            y_min = max(0, min(valid_prices) * 0.95)
                            y_max = max(valid_prices) * 1.05
                            ax.set_ylim(y_min, y_max)
                
                else:
                    ax.axis('off')
            
            self.fig.suptitle(
                f"Token Group {self.window_num} - {datetime.now().strftime('%H:%M:%S')}",
                fontsize=10, y=0.99
            )
            self.canvas.draw()
            self.update_status(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
            
        except Exception as e:
            print(f"Window {self.window_num} plot error: {str(e)[:100]}")

def fetch_token_chunk(chunk):
    """Fetch prices for a chunk of tokens with rate limit handling"""
    url = 'https://lite-api.jup.ag/price/v2'
    params = {'ids': ','.join(chunk)}
    
    try:
        # Add delay between requests
        time.sleep(0.5)  # 500ms delay between requests
        
        response = session.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json().get('data', {})
    except Exception as e:
        print(f"Error fetching chunk (retrying): {str(e)[:100]}...")
        raise  # Re-raise for retry mechanism

def get_all_token_prices():
    """Fetch prices for all tokens with rate limit control"""
    tokens_to_fetch = TOKEN_IDS[:MAX_TOKENS]  # Only fetch up to MAX_TOKENS
    token_chunks = [tokens_to_fetch[i:i+TOKEN_CHUNK_SIZE] 
                   for i in range(0, len(tokens_to_fetch), TOKEN_CHUNK_SIZE)]
    
    combined_data = {}
    
    # Process chunks sequentially with delays
    for i, chunk in enumerate(token_chunks):
        try:
            # Add delay between batches if needed
            if i > 0:
                time.sleep(1)  # 1 second delay between batches
            
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = [executor.submit(fetch_token_chunk, chunk)]
                for future in futures:
                    try:
                        result = future.result()
                        combined_data.update(result)
                    except Exception as e:
                        print(f"Failed to fetch chunk after retries: {str(e)[:100]}")
                        # Fill with zeros if we can't get data
                        for token_id in chunk:
                            combined_data[token_id] = {'price': '0', 'symbol': token_id[:4]+'...'}
        except Exception as e:
            print(f"Error processing chunk: {str(e)[:100]}")
    
    return combined_data

def calculate_percentage_changes(token_id, current_price):
    intervals = {
        '2s': 2,
        '5s': 5,
        '10s': 10,
        '30s': 30,
        '1m': 60,
        '2m': 120,
        '5m': 300,
        '10m': 600
    }
    
    changes = {interval: 'N/A' for interval in intervals}
    
    if token_id not in price_history or len(price_history[token_id]) < 2:
        return changes
    
    def find_previous_price(seconds_ago):
        target_time = datetime.now() - timedelta(seconds=seconds_ago)
        for i in range(len(time_history)-1, -1, -1):
            if time_history[i] <= target_time:
                return price_history[token_id][i]
        return None
    
    for interval, seconds in intervals.items():
        if interval == '2s' and len(price_history[token_id]) >= 2:
            prev_price = price_history[token_id][-2]
            if prev_price > 0:
                changes[interval] = f"{(current_price - prev_price)/prev_price*100:.2f}%"
        else:
            price = find_previous_price(seconds)
            if price is not None and price > 0:
                changes[interval] = f"{(current_price - price)/price*100:.2f}%"
    
    return changes

def update_data(price_data):
    global start_time
    
    if not price_data:
        return
    
    with data_lock:
        current_time = datetime.now()
        
        if start_time is None:
            start_time = current_time
        
        time_history.append(current_time)
        
        for token_id in TOKEN_IDS[:MAX_TOKENS]:  # Only update tracked tokens
            try:
                # Safely get the price data for this token
                token_data = price_data.get(token_id)
                if token_data is not None and 'price' in token_data:
                    price = float(token_data['price'])
                    price_history[token_id].append(price)
                else:
                    raise ValueError("Missing price data")
            except (ValueError, KeyError, TypeError):
                # Fallback to previous price or 0 if no history exists
                if token_id in price_history and price_history[token_id]:
                    price_history[token_id].append(price_history[token_id][-1])
                else:
                    # Initialize if not exists
                    if token_id not in price_history:
                        price_history[token_id] = []
                    price_history[token_id].append(0)
        
        if len(time_history) > MAX_DATA_POINTS:
            time_history.pop(0)
            for token_id in TOKEN_IDS[:MAX_TOKENS]:
                if len(price_history[token_id]) > MAX_DATA_POINTS:
                    price_history[token_id].pop(0)

def print_prices(price_data):
    if not price_data:
        return
    
    print(f"\n{'='*120}")
    print(f"{'Token':<10} {'Price':<12} {'2s':<8}{'5s':<8} {'10s':<8} {'30s':<8} {'1m':<8} {'2m':<8} {'5m':<8} {'10m':<8} {'ID':<20}")
    print(f"{'-'*120}")
    
    # Print all tracked tokens (up to MAX_TOKENS)
    for token_id in TOKEN_IDS[:MAX_TOKENS]:
        token_info = price_data.get(token_id)
        if token_info is None:  # Skip if token data is missing
            continue
            
        try:
            # Safely get price with fallback handling
            current_price = float(token_info.get('price', 0)) if token_info else 0
            changes = calculate_percentage_changes(token_id, current_price)
            
            # Get token name/symbol with fallback
            name = token_info.get('symbol', token_id[:4] + '...') if token_info else token_id[:4] + '...'
            
            print(f"{name:<10} {current_price:<12.6f} "
                  f"{changes.get('2s', 'N/A'):<8} {changes.get('5s', 'N/A'):<8}{changes.get('10s', 'N/A'):<8} "
                  f"{changes.get('30s', 'N/A'):<8} {changes.get('1m', 'N/A'):<8} "
                  f"{changes.get('2m', 'N/A'):<8} {changes.get('5m', 'N/A'):<8} "
                  f"{changes.get('10m', 'N/A'):<8} {token_id[:44]}")
        except (ValueError, KeyError, TypeError) as e:
            # Print error info for debugging (optional)
            # print(f"Error processing {token_id}: {str(e)}")
            continue
    
    print(f"{'='*120}")
    print(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Tracking {min(len(TOKEN_IDS), MAX_TOKENS)} tokens (reduced for rate limits)")
    print(f"API calls: {MAX_WORKERS} concurrent, {TOKEN_CHUNK_SIZE} tokens per call, every {UPDATE_INTERVAL}s")
def create_tracker_windows():
    windows = []
    tokens_to_display = TOKEN_IDS[:MAX_TOKENS]  # Only display up to MAX_TOKENS
    token_chunks = [tokens_to_display[i:i+TOKENS_PER_WINDOW] 
                   for i in range(0, len(tokens_to_display), TOKENS_PER_WINDOW)]
    
    for i, chunk in enumerate(token_chunks, 1):
        root = tk.Tk()
        root.geometry(f"{root.winfo_screenwidth()-100}x{root.winfo_screenheight()-100}+{((i-1)%3)*300}+{((i-1)//3)*300}")
        tracker = TokenTracker(root, chunk, i)
        windows.append((root, tracker))
    
    return windows

def main_loop(trackers):
    try:
        while True:
            start = time.time()
            
            price_data = get_all_token_prices()
            if not price_data:
                print("Price fetch failed, retrying...")
                time.sleep(2)
                continue
            
            update_data(price_data)
            print_prices(price_data)
            
            for i, (_, tracker) in enumerate(trackers, 1):
                if not tracker.should_close:
                    plot_queue.put((i, price_data))
            
            if any(tracker.should_close for _, tracker in trackers):
                print("Window closed detected, shutting down...")
                break
            
            elapsed = time.time() - start
            sleep_time = max(1, UPDATE_INTERVAL - elapsed)
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        for root, tracker in trackers:
            tracker.should_close = True
            try:
                root.quit()
            except:
                pass

if __name__ == "__main__":
    print("Creating tracker windows (reduced token count for rate limits)...")
    trackers = create_tracker_windows()
    
    update_thread = threading.Thread(
        target=main_loop,
        args=(trackers,),
        daemon=True
    )
    update_thread.start()
    
    try:
        for root, _ in trackers:
            root.mainloop()
    except:
        pass
    
    update_thread.join()
    for root, _ in trackers:
        try:
            root.destroy()
        except:
            pass