import time
import requests
from datetime import datetime, timedelta
from multiprocessing import Queue
import threading
import json
import os

class TokenSaleDecision:
    def __init__(self, bought_price, initial_price):
        self.bought_price = bought_price
        self.current_price = initial_price
        self.buy_time = datetime.now()
        self.max_price_seen = bought_price
        self.missing_count = 0
        
    def update_price(self, new_price):
        self.current_price = new_price
        if new_price > self.max_price_seen:
            self.max_price_seen = new_price
        self.missing_count = 0
        
    def should_sell(self):
        current_profit = ((self.current_price - self.bought_price) / self.bought_price) * 100
        time_held = datetime.now() - self.buy_time
        
        if current_profit <= -45:
            return True, "STOP LOSS (-45%)"
            
        if time_held >= timedelta(minutes=8):
            return current_profit >= 5, "5% Target (8m+)"
        elif time_held >= timedelta(minutes=7):
            return current_profit >= 10, "10% Target (7m+)"
        elif time_held >= timedelta(minutes=5):
            return current_profit >= 15, "15% Target (5m+)"
        else:
            return current_profit >= 20, "20% Target"

class TokenMonitor:
    def __init__(self, queue):
        self.queue = queue
        self.token_decisions = {}
        self.running = True
        self.last_update = 0
        self.update_interval = 2.0  # Strict 2-second interval
        self.api_call_lock = threading.Lock()
        self.last_api_call = 0
        self.min_api_delay = 2.0  # 2 seconds between API calls (30/minute max)
        
    def rate_limited_api_call(self):
        """Ensure we don't exceed 30 API calls/minute"""
        with self.api_call_lock:
            current_time = time.time()
            elapsed = current_time - self.last_api_call
            if elapsed < self.min_api_delay:
                time.sleep(self.min_api_delay - elapsed)
            self.last_api_call = time.time()
    
    def get_token_prices(self, token_ids):
        """Fetch prices with strict rate limiting"""
        if not token_ids: return {}
        
        self.rate_limited_api_call()
        
        try:
            response = requests.get(
                'https://lite-api.jup.ag/price/v2',
                params={'ids': ','.join(token_ids)},
                timeout=15,
                headers={'User-Agent': 'JupiterSaleMonitor/2.0'}
            )
            response.raise_for_status()
            data = response.json().get('data', {})
            
            return {
                token_id: float(token_data['price'])
                for token_id, token_data in data.items()
                if 'price' in token_data and token_data['price'] != '0'
            }
        except Exception as e:
            print(f"⚠ API Error: {str(e)}")
            return None
            
    def get_prices_from_file(self):
        """Read prices from jupPrice.py's output with freshness check"""
        try:
            if not os.path.exists('token_prices.json'):
                return None
                
            # Only use file if updated in last 3 seconds
            if time.time() - os.path.getmtime('token_prices.json') > 3:
                return None
                
            with open('token_prices.json', 'r') as f:
                data = json.load(f)
                return {
                    item['ID']: float(item['Price'])
                    for item in data
                    if 'ID' in item and 'Price' in item
                }
        except Exception as e:
            print(f"⚠ File read error: {str(e)}")
            return None
    
    def process_queue(self):
        """Process buy signals with rate limiting"""
        while self.running:
            if not self.queue.empty():
                try:
                    message = self.queue.get()
                    if message.get('type') == 'buy':
                        token_id = message['token_id']
                        bought_price = message['price']
                        
                        # Try file first
                        prices = self.get_prices_from_file()
                        
                        # Fallback to API if needed (rate limited)
                        if not prices or token_id not in prices:
                            prices = self.get_token_prices([token_id])
                        
                        if prices and token_id in prices:
                            self.token_decisions[token_id] = TokenSaleDecision(bought_price, prices[token_id])
                            print(f"✔ Monitoring {token_id[:6]}... | Buy: {bought_price:.6f} | Current: {prices[token_id]:.6f}")
                        else:
                            print(f"⏳ Price not available for {token_id[:6]}..., will retry")
                            self.queue.put(message)  # Requeue
                            time.sleep(1)
                            
                except Exception as e:
                    print(f"⚠ Queue error: {str(e)}")
                    time.sleep(1)
                    
            time.sleep(0.1)
            
    def monitor_tokens(self):
        """Monitor tokens with strict 2-second intervals"""
        while self.running:
            current_time = time.time()
            
            # Maintain exact 2-second interval
            if current_time - self.last_update < self.update_interval:
                time.sleep(0.05)
                continue
                
            self.last_update = current_time
            
            # Get prices (file first, then API)
            prices = self.get_prices_from_file()
            missing_tokens = []
            
            if not prices:
                prices = {}
            
            # Check which tokens need API lookup
            for token_id in list(self.token_decisions.keys()):
                if token_id not in prices:
                    missing_tokens.append(token_id)
            
            # Fetch missing prices in one batch if needed
            if missing_tokens:
                api_prices = self.get_token_prices(missing_tokens)
                if api_prices:
                    prices.update(api_prices)
            
            # Process decisions
            for token_id, decision in list(self.token_decisions.items()):
                if token_id in prices:
                    decision.update_price(prices[token_id])
                    sell, reason = decision.should_sell()
                    
                    if sell:
                        profit = ((prices[token_id] - decision.bought_price) / decision.bought_price) * 100
                        print(f"🚀 SELL {token_id[:6]}... at {prices[token_id]:.6f} ({profit:.2f}% profit) - {reason}")
                        del self.token_decisions[token_id]
                    else:
                        profit = ((prices[token_id] - decision.bought_price) / decision.bought_price) * 100
                        print(f"⏳ HOLD {token_id[:6]}... | Price: {prices[token_id]:.6f} | Profit: {profit:.2f}%")
                
            
            time.sleep(0.05)
            
    def start(self):
        self.process_thread = threading.Thread(target=self.process_queue)
        self.monitor_thread = threading.Thread(target=self.monitor_tokens)
        self.process_thread.start()
        self.monitor_thread.start()
        
    def stop(self):
        self.running = False
        self.process_thread.join()
        self.monitor_thread.join()

if __name__ == "__main__":
    print("🔍 Starting Token Sale Monitor (Strict Rate Limited)")
    
    # Test connection
    test_monitor = TokenMonitor(Queue())
    sol_token = "So11111111111111111111111111111111111111112"
    
    print("Testing API connection...")
    sol_prices = test_monitor.get_token_prices([sol_token])
    
    if not sol_prices or sol_token not in sol_prices:
        print("❌ API test failed. Please check:")
        print("1. Internet connection")
        print(f"2. API status: https://lite-api.jup.ag/price/v2?ids={sol_token}")
        exit()
    
    print(f"✓ API working | SOL price: {sol_prices[sol_token]}")
    
    # Main monitor
    input_queue = Queue()
    monitor = TokenMonitor(input_queue)
    monitor.start()

    try:
        # Example token monitoring
        your_token = "HQNJmMYYzrd4vRFK7e89JuzD4UNb1vAHi7a9q4Wcpump"  # Replace with your token
        prices = monitor.get_token_prices([your_token])
        
        if prices and your_token in prices:
            print(f"✓ Token found | Price: {prices[your_token]}")
            input_queue.put({
                'type': 'buy',
                'token_id': your_token,
                'price': prices[your_token]
            })
        else:
            print(f"❌ Token not found. Verify:")
            print(f"1. Token exists: https://solscan.io/token/{your_token}")
            print(f"2. Is tradeable: https://jup.ag/swap/{your_token}-USDC")
        
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitor...")
    finally:
        monitor.stop()