from playwright.sync_api import sync_playwright
from multiprocessing.managers import BaseManager
import time
import signal
import sys

class QueueManager(BaseManager):
    pass

def connect_to_manager():
    QueueManager.register('get_queue')
    QueueManager.register('get_stop_event')
    manager = QueueManager(address=('localhost', 50000), authkey=b'abc123')
    try:
        manager.connect()
        return manager.get_queue(), manager.get_stop_event()
    except ConnectionRefusedError:
        print("❌ Error: Could not connect to queue manager")
        print("   Make sure queue_manager.py is running first")
        sys.exit(1)

def scrape_pump_fun():
    data_queue, stop_event = connect_to_manager()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1600, "height": 1400},
            device_scale_factor=1.5
        )
        page = context.new_page()

        try:
            print("🚀 Navigating to pump.fun...")
            page.goto("https://pump.fun/advanced?include-nsfw=true", timeout=120000)
            
            # Handle popups
            print("🔄 Handling popups...")
            for _ in range(3):
                try:
                    page.click('button[data-test-id="how-it-works-button"]', timeout=8000)
                    time.sleep(2)
                    page.evaluate('''() => {
                        const closeImg = document.querySelector('img[alt="close"][src*="close_icon"]');
                        if (closeImg) closeImg.closest('button').click();
                    }''')
                    time.sleep(3)
                    break
                except:
                    continue
            
            while not stop_event.is_set():
                try:
                    # Wait for coin list
                    print("🔍 Locating newest coins at top of list...")
                    page.wait_for_selector('div[data-testid="virtuoso-item-list"]', timeout=60000)
                    
                    # Get visible coins
                    print("📦 Processing newest coins...")
                    coins = page.evaluate('''() => {
                        const mainList = document.querySelector('div[data-testid="virtuoso-item-list"]');
                        if (!mainList) return [];
                        
                        const coins = [];
                        const items = mainList.querySelectorAll('div[data-index]');
                        
                        for (let i = 0; i < items.length; i++) {
                            const item = items[i];
                            const coinDiv = item.querySelector('div[data-coin-mint]');
                            if (!coinDiv) continue;
                            
                            const rect = item.getBoundingClientRect();
                            const isVisible = (
                                rect.top >= 0 &&
                                rect.left >= 0 &&
                                rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                                rect.right <= (window.innerWidth || document.documentElement.clientWidth)
                            );
                            
                            if (isVisible) {
                                const nameElement = item.querySelector('div.truncate.font-semibold.text-gray-300') || 
                                                    item.querySelector('div.font-semibold.text-gray-300');
                                const symbolElement = item.querySelector('div.mr-2.truncate.font-bold.text-white') || 
                                                     item.querySelector('div.font-bold.text-white');
                                
                                coins.push({
                                    mint: coinDiv.getAttribute('data-coin-mint'),
                                    name: nameElement?.innerText,
                                    symbol: symbolElement?.innerText,
                                    img: item.querySelector('img[alt="coin"]')?.src,
                                    timestamp: new Date().toISOString()
                                });
                            }
                        }
                        return coins;
                    }''')
                    
                    # Put valid coins into queue
                    for coin in coins:
                        if all(coin.values()):
                            data_queue.put(dict(coin))  # Convert to regular dict
                            print(f"📤 Sent to queue: {coin['symbol']}")
                    
                    # Wait before next scrape (interruptible)
                    print("🔄 Waiting 10 seconds before next scrape...")
                    for _ in range(10):
                        if stop_event.is_set():
                            break
                        time.sleep(1)
                            
                except Exception as e:
                    print(f"⚠️ Scraping error: {str(e)}")
                    if stop_event.is_set():
                        break
                    time.sleep(5)
                    continue
                    
        except Exception as e:
            print(f"\n❌ Main error: {str(e)}")
            page.screenshot(path="error.png")
            print("Saved error screenshot to error.png")
        finally:
            browser.close()
            print("✅ Scraper shutdown complete")

def main():
    def shutdown(signum, frame):
        print("\n🛑 Shutdown signal received")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("🔄 Starting scraper - connecting to queue manager...")
    scrape_pump_fun()

if __name__ == "__main__":
    main()