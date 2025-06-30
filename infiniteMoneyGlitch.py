from multiprocessing.managers import BaseManager
import time
import signal
import sys
import json
from datetime import datetime
import math
import requests
from collections import deque

class QueueManager(BaseManager):
    pass

# Configuration
SOLANA_MINT = "So11111111111111111111111111111111111111112"
BASE_URL = "http://localhost:3000/swap/quote-and-execute"
AUTO_SELL_URL = "http://localhost:3000/auto-sell/start"
RPC_URL = "https://api.mainnet-beta.solana.com"
DEFAULT_SLIPPAGE_BPS = 7000
WALLET_ADDRESS = "YOUR_WALLET_ADDRESS_HERE"

bought_tokens = {}  # Stores {token_id: purchase_timestamp}
purchase_queue = deque()
processing_tokens = set()

def clean_expired_tokens():
    """Remove tokens that have been in bought_tokens for more than 13 minutes"""
    current_time = time.time()
    expired_tokens = [
        token_id for token_id, purchase_time in bought_tokens.items()
        if current_time - purchase_time > 16 * 60  # 13 minutes in seconds
    ]
    for token_id in expired_tokens:
        bought_tokens.pop(token_id, None)
        print(f"♻️ Removed expired token from tracking: {token_id}")

def safe_convert(value):
    try:
        if isinstance(value, str):
            value = value.replace('%', '').strip()
            if value.lower() in ('', 'nan', 'none', 'null', 'n/a'):
                return float('nan')
        return float(value)
    except:
        return float('nan')

def get40(wallet_address: str) -> int:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [wallet_address]
    }
    try:
        response = requests.post(RPC_URL, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise Exception(f"RPC Error: {data['error']}")
        return int(data["result"]["value"] * 0.1)
    except Exception as e:
        raise Exception(f"Failed to fetch balance: {str(e)}")

def usd_to_lamports() -> int:
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        sol_price = data['solana']['usd']
        return int((940 / sol_price) * 1_000_000_000)
    except Exception as e:
        raise Exception(f"Error calculating USD to lamports: {str(e)}")

def buy(output_mint: str, amount: int) -> dict:
    """Execute a token buy with retry logic (3 total attempts)"""
    max_attempts = 3
    attempt = 0
    last_exception = None
    
    url = f"{BASE_URL}/{SOLANA_MINT}/{output_mint}/{amount}"
    params = {
        "slippage": DEFAULT_SLIPPAGE_BPS,
        "dynamicSlippage": "true",
        "priorityLevel": "high",
        "maxPriorityFee": 100000,
        "maxRetries": 3,
        "commitment": "confirmed"
    }
    
    while attempt < max_attempts:
        attempt += 1
        try:
            print("attempt:", attempt)
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            last_exception = e
            if attempt < max_attempts:
                time.sleep(attempt)  # Linear backoff (1s, 2s)
    
    # All attempts failed
    error_details = {}
    if hasattr(last_exception, 'response') and last_exception.response:
        try:
            error_details = last_exception.response.json()
        except:
            error_details = {"raw_response": last_exception.response.text}
    
    raise Exception(
        f"Buy API Error after {max_attempts} attempts - "
        f"Details: {error_details}, Error: {str(last_exception)}"
    )

def start_auto_sell(buy_response: dict, output_mint: str):
    """Start auto-sell process using the buy response data"""
    try:
        quote = buy_response['quoteResponse']
        payload = {
            "inputMint": output_mint,
            "inAmount": quote['outAmount'],
            "initialUsdValue": quote['swapUsdValue'],
            "buyTime": datetime.now().isoformat(),
            "slippageBps": 9900,
            "maxRetries": 20
        }
        
        response = requests.post(
            AUTO_SELL_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        response.raise_for_status()
        
        print(f"✅ Auto-sell started for {output_mint}")
        return response.json()
    except Exception as e:
        print(f"⚠️ Failed to start auto-sell: {str(e)}")
        raise

import time
from time import sleep

def process_purchase_queue():
    while purchase_queue:
        signal = purchase_queue[0]
        token_mint = signal['id']
        
        if token_mint in processing_tokens or token_mint in bought_tokens:
            purchase_queue.popleft()
            continue
            
        processing_tokens.add(token_mint)
        print(f"\n🛒 Processing purchase for {token_mint}")
        
        try:
            # Execute purchase
            buy_response = buy(
                output_mint=token_mint,
                amount=min(get40(WALLET_ADDRESS), usd_to_lamports())
            )
            print("✓ Purchase executed successfully")
            
            # Update signal with swap USD value
            swap_value = float(buy_response['quoteResponse']['swapUsdValue'])
            signal['price'] = swap_value  # Now storing just the swap value
            
            # Track purchase time
            bought_tokens[token_mint] = time.time()
            
            # Start auto-sell process with retries
            max_retries = 4
            retry_delay = 1  # seconds
            for attempt in range(max_retries):
                try:
                    start_auto_sell(buy_response, token_mint)
                    break  # Success, exit retry loop
                except Exception as e:
                    if attempt == max_retries - 1:  # Last attempt failed
                        print(f"✗ Failed to start auto-sell after {max_retries} attempts: {str(e)}")
                    else:
                        print(f"⚠️ Auto-sell attempt {attempt + 1} failed, retrying in {retry_delay}s...")
                        sleep(retry_delay)
            
            print(f"⏱️ Total processing time: {time.time() - purchase_time:.1f}s")
                        
        except Exception as e:
            print(f"✗ Purchase failed: {str(e)}")
        finally:
            processing_tokens.discard(token_mint)
            purchase_queue.popleft()

def check_token(token):
    try:
        converted = {
            'token': str(token.get('token', '')),
            'price': safe_convert(token.get('price')),
            't_2s': safe_convert(token.get('t_2s')),
            't_5s': safe_convert(token.get('t_5s')),
            't_10s': safe_convert(token.get('t_10s')),
            't_30s': safe_convert(token.get('t_30s')),
            't_1m': safe_convert(token.get('t_1m')),
            't_2m': safe_convert(token.get('t_2m')),
            't_5m': safe_convert(token.get('t_5m')),
            't_10m': safe_convert(token.get('t_10m')),
            'id': str(token.get('id', token.get('token', ''))),
            'time': str(token.get('time', ''))
        }

        # Calculate retrace counts for different conditions
        retrace_count_c1 = sum(1 for key in ['t_2s', 't_5s', 't_2m'] if converted[key] < -5.0)
        retrace_count_c3 = sum(1 for key in ['t_2s', 't_5s', 't_10s','t_30s', 't_1m','t_2m'] if converted[key] < -20.0)

        # Check required fields for each condition
        required_c1 = ['t_10s', 't_30s', 't_1m', 't_2m', 't_5m']
        isRequired_c1 = not any(math.isnan(converted[field]) for field in required_c1)
        
        isRequired_NA_c2 = all(
            token.get(field) is None 
            for field in ['t_5m', 't_10m']
        )
        

        condition2 = all([
            converted['price'] > 6.5e-05,
            # converted['price'] < 6e-04,
            isRequired_NA_c2
        ])

        # condition3 = all([
        #     (converted['t_10s'] > 300.0 or
        #      converted['t_30s'] > 300.0),
        #     #  converted['t_1m'] > 300.0),
        #     converted['price'] > 3e-05,
        #     # isRequired_NA_c3,
        #     retrace_count_c3 == 0
        # ])

        # Check if any condition is met
        if condition2:
            # or condition3:
            condition_met = "2"
            return {
                **converted,
                'signal': "BUY",
                'analysis_time': datetime.now().strftime("%H:%M:%S.%f"),
                'condition_met': condition_met,
                'retrace_check': f"C1:{retrace_count_c1}/C3:{retrace_count_c3}",
                'conditions': {
                    # 'condition1': condition1,
                    'condition2': condition2,
                    # 'condition3': condition3
                }
            }
        return None
    except Exception as e:
        print(f"Error in check_token: {str(e)}")
        return None

def process_batch(batch):
    clean_expired_tokens()  # Clean expired tokens before processing new batch
    start_time = time.time()
    print(f"\n📊 Processing {len(batch)} tokens @ {datetime.now().strftime('%H:%M:%S.%f')}")
    
    buy_signals = []
    for token in batch:
        if isinstance(token, dict):
            signal = check_token(token)
            if signal and signal['id'] not in processing_tokens:
                buy_signals.append(signal)
                purchase_queue.append(signal)
    
    process_purchase_queue()
    
    print(f"✅ Processed in {(time.time() - start_time)*1000:.2f}ms")
    if buy_signals:
        print("\n🔥 BUY SIGNALS DETECTED 🔥")
        for signal in buy_signals:
            print(json.dumps(signal, indent=2))
    print("=" * 60)

def connect_to_manager():
    QueueManager.register('get_json_queue')
    QueueManager.register('get_stop_event')
    manager = QueueManager(address=('localhost', 50000), authkey=b'abc123')
    try:
        manager.connect()
        return (
            manager.get_json_queue(),
            manager.get_stop_event()
        )
    except ConnectionRefusedError:
        print("❌ Could not connect to queue manager")
        sys.exit(1)

def main():
    def shutdown(signum, frame):
        print("\n🛑 Shutdown signal received")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    if WALLET_ADDRESS == "YOUR_WALLET_ADDRESS_HERE":
        print("❌ Please set your wallet address")
        sys.exit(1)

    json_queue, stop_event = connect_to_manager()
    print("\n🚀 Buy signal producer ready")

    while not stop_event.is_set():
        try:
            batch = json_queue.get(timeout=1)
            if isinstance(batch, list):
                process_batch(batch)
        except Exception:
            if stop_event.is_set():
                break

    print("✅ Shutdown complete")

if __name__ == "__main__":
    main()