import os
import sys
import logging
from dramatiq import Worker

# Set up path
sys.path.append(os.path.join(os.getcwd(), "media-server"))

from services.task.broker import get_broker
from services.task.consumers import scan_worker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_consume():
    print("--- Testing Consume ---")
    broker = get_broker()
    
    # Manually set up a worker for the scan queue
    # We only want to process one message then exit
    worker = Worker(broker, worker_timeout=100)
    
    # We need to make sure the actor is declared on the broker
    broker.declare_actor(scan_worker)
    
    # print(f"Broker URL: {broker.url}")
    print(f"Queues: {broker.queues}")
    print("Starting worker for 5 seconds...")
    
    # This starts the worker in a separate thread usually, but we can just run it for a bit
    worker.start()
    
    import time
    time.sleep(5)
    
    worker.stop()
    print("Worker stopped")

if __name__ == "__main__":
    test_consume()
