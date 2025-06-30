
# queue_manager.py
from multiprocessing.managers import BaseManager
from multiprocessing import Queue, Event
import sys

class QueueManager(BaseManager):
    pass

def run_manager():
    # Create the shared objects
    task_queue = Queue()
    json_queue = Queue()
    buy_signal_queue = Queue()
    stop_event = Event()
    
    # Register them with the manager
    QueueManager.register('get_queue', callable=lambda: task_queue)
    QueueManager.register('get_json_queue', callable=lambda: json_queue)
    QueueManager.register('get_buy_signal_queue', callable=lambda: buy_signal_queue)
    QueueManager.register('get_stop_event', callable=lambda: stop_event)
    
    # Start the manager server
    manager = QueueManager(address=('localhost', 50000), authkey=b'abc123')
    server = manager.get_server()
    
    print("🚀 Queue manager server running - ready for connections")
    print("   Press Ctrl+C to stop the manager")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down queue manager...")
        # Set stop event when shutting down
        stop_event.set()
        sys.exit(0)

if __name__ == '__main__':
    run_manager()