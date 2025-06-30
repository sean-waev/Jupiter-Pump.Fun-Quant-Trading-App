import requests
import time
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from collections import defaultdict
import math
import numpy as np
import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk

# Configuration
UPDATE_INTERVAL = 3  # Update every 3 seconds
MAX_DATA_POINTS = 1200  # Increased to accommodate all time windows
TOKEN_IDS = [
    'So11111111111111111111111111111111111111112',  # SOL

]

# Data storage
price_history = defaultdict(list)
time_history = []
start_time = None

class TokenTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Crypto Price Tracker")
        
        matplotlib.use('TkAgg')
        
        self.num_tokens = len(TOKEN_IDS)
        self.cols = min(10, math.ceil(math.sqrt(self.num_tokens)))
        self.rows = math.ceil(self.num_tokens / self.cols)
        self.fig, self.axs = plt.subplots(
            self.rows, self.cols, 
            figsize=(self.cols*5, self.rows*3),
            tight_layout=True
        )
        
        if self.num_tokens > 1:
            self.axs = self.axs.flatten()
        else:
            self.axs = [self.axs]
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        
        control_frame = tk.Frame(self.root)
        control_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status = tk.StringVar()
        self.status.set("Initializing...")
        tk.Label(control_frame, textvariable=self.status).pack(side=tk.LEFT)
        
        tk.Button(
            control_frame, text="Exit", command=self.cleanup
        ).pack(side=tk.RIGHT)
        
        self.initialize_plots()
    
    def initialize_plots(self):
        for i, ax in enumerate(self.axs):
            if i < self.num_tokens:
                token_id = TOKEN_IDS[i]
                ax.set_title(f"{token_id[:8]}...")
                ax.set_xlabel("Time (s)")
                ax.set_ylabel("Price")
                ax.grid(True)
            else:
                ax.axis('off')
        
        self.fig.suptitle("Crypto Price Tracker - Loading Data...")
        self.canvas.draw()
    
    def update_plots(self, price_data):
        if not price_data or 'data' not in price_data:
            return
        
        times = [(t - start_time).total_seconds() for t in time_history]
        
        for i, ax in enumerate(self.axs):
            if i >= self.num_tokens:
                continue
            
            token_id = TOKEN_IDS[i]
            ax.clear()
            
            if token_id in price_history and len(price_history[token_id]) > 0:
                prices = price_history[token_id]
                token_info = price_data['data'].get(token_id, {})
                name = token_info.get('name', token_id[:8] + '...')
                
                ax.plot(times, prices, 'b-', linewidth=1.5, label=name)
                ax.set_title(name)
                ax.set_xlabel("Time (s)")
                ax.set_ylabel("Price (USD)")
                ax.grid(True)
                
                if len(prices) > 0:
                    y_min = max(0, min(prices) * 0.95)
                    y_max = max(prices) * 1.05
                    ax.set_ylim(y_min, y_max)
                
                if max(prices) < 1:
                    ax.yaxis.set_major_formatter('{:.6f}'.format)
                else:
                    ax.yaxis.set_major_formatter('{:.2f}'.format)
        
        self.fig.suptitle(
            f"Crypto Price Tracker - Last Update: {datetime.now().strftime('%H:%M:%S')}"
        )
        self.canvas.draw()
    
    def cleanup(self):
        plt.close('all')
        self.root.quit()
        self.root.destroy()

def get_token_prices():
    url = 'https://lite-api.jup.ag/price/v2'
    params = {'ids': ','.join(TOKEN_IDS)}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Price fetch error: {e}")
        return None

def calculate_percentage_changes(token_id, current_price):
    """Calculate percentage changes for all time intervals"""
    intervals = {
        '2s': 2,
        '10s': 10,
        '30s': 30,
        '1m': 60,
        '2m': 120,
        '5m': 300,
        '10m': 600,
        '20m': 1200,
        '30m': 1800,
        '45m': 2700,
    }
    
    changes = {interval: 'N/A' for interval in intervals}
    
    if token_id not in price_history or len(price_history[token_id]) < 2:
        return changes
    
    # Helper function to find price at specified time ago
    def find_previous_price(seconds_ago):
        target_time = datetime.now() - timedelta(seconds=seconds_ago)
        for i in range(len(time_history)-1, -1, -1):
            if time_history[i] <= target_time:
                return price_history[token_id][i]
        return None
    
    # Calculate changes for each interval
    for interval, seconds in intervals.items():
        if interval == '2s' and len(price_history[token_id]) >= 2:
            # Special case for immediate previous price
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
    
    if price_data and 'data' in price_data:
        current_time = datetime.now()
        
        if start_time is None:
            start_time = current_time
        
        time_history.append(current_time)
        
        for token_id in TOKEN_IDS:
            if token_id in price_data['data']:
                try:
                    price = float(price_data['data'][token_id]['price'])
                    price_history[token_id].append(price)
                except (ValueError, KeyError):
                    price_history[token_id].append(
                        price_history[token_id][-1] if price_history.get(token_id) else 0
                    )
            else:
                price_history[token_id].append(
                    price_history[token_id][-1] if price_history.get(token_id) else 0
                )
        
        if len(time_history) > MAX_DATA_POINTS:
            time_history.pop(0)
            for token_id in TOKEN_IDS:
                if len(price_history[token_id]) > MAX_DATA_POINTS:
                    price_history[token_id].pop(0)

def print_prices(price_data):
    if not price_data or 'data' not in price_data:
        return
    
    # Header with all time intervals
    header = (
        f"\n{'Token':<20} {'Price':<12} "
        f"{'2s':<8} {'10s':<8} {'30s':<8} "
        f"{'1m':<8} {'2m':<8} {'5m':<8} {'10m':<8} "
        f"{'20m':<8} {'30m':<8} {'45m':<8} "
        f"{'ID':<20}"
    )
    separator = "-" * 110  # Adjusted for new columns
    print(separator)
    print(header)
    print(separator)
    
    for token_id in TOKEN_IDS:
        if token_id in price_data['data']:
            token_info = price_data['data'][token_id]
            try:
                current_price = float(token_info['price'])
                changes = calculate_percentage_changes(token_id, current_price)
                
                name = token_info.get('name', token_id[:6] + '...')
                row = (
                    f"{name:<20} {current_price:<12.6f} "
                    f"{changes['2s']:<8} {changes['10s']:<8} {changes['30s']:<8} "
                    f"{changes['1m']:<8} {changes['2m']:<8} {changes['5m']:<8} {changes['10m']:<8} "
                    f"{changes['20m']:<8} {changes['30m']:<8} {changes['45m']:<8} "
                    f"{token_id[:44]}"
                )
                print(row)
            except (ValueError, KeyError):
                continue
    
    print(separator)
    print(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def main_loop(tracker):
    try:
        while True:
            start = time.time()
            
            price_data = get_token_prices()
            if price_data:
                update_data(price_data)
                print_prices(price_data)
                tracker.status.set(f"Last update: {datetime.now().strftime('%H:%M:%S')}")
                tracker.root.after(0, lambda: tracker.update_plots(price_data))
            
            elapsed = time.time() - start
            sleep_time = max(0, UPDATE_INTERVAL - elapsed)
            time.sleep(sleep_time)
            
            if not tk.Toplevel.winfo_exists(tracker.root):
                break
                
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        tracker.cleanup()

if __name__ == "__main__":
    root = tk.Tk()
    root.protocol("WM_DELETE_WINDOW", root.quit)
    
    tracker = TokenTracker(root)
    
    import threading
    update_thread = threading.Thread(
        target=main_loop, 
        args=(tracker,),
        daemon=True
    )
    update_thread.start()
    
    try:
        root.mainloop()
    except:
        pass
    
    tracker.cleanup()