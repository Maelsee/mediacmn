import os
import sys
import logging
import redis
import uuid

# Set up path
sys.path.append(os.path.join(os.getcwd(), "media-server"))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from services.task.broker import get_broker
from services.task.consumers import scan_worker

def test_enqueue():
    broker = get_broker()
    scan_worker.broker = broker
    
    task_id = uuid.uuid4().hex
    payload = {"test": "data"}
    
    logger.info(f"Broker: {broker}")
    logger.info(f"Actor Broker: {scan_worker.broker}")
    
    # Generate message manually to check
    msg = scan_worker.message(task_id, payload)
    logger.info(f"Generated Message object: {msg}")
    logger.info(f"Message dict: {msg.asdict()}")
    
    # Send
    logger.info("Calling send()...")
    scan_worker.send(task_id, payload)
    logger.info("Send called.")
    
    # Check Redis immediately
    from core.config import get_settings
    s = get_settings()
    r = redis.from_url(s.REDIS_URL)
    
    # Dramatiq RedisBroker uses "dramatiq:default" unless specified.
    # scan_worker has queue_name="scan". So it should be "dramatiq:scan".
    queue_name = "dramatiq:scan"
    
    last_item = r.lindex(queue_name, 0)
    print(f"\n--- Redis Inspection ---")
    print(f"Queue '{queue_name}' item at index 0: {last_item}")
    
    if last_item:
        try:
            print(f"Decoded: {last_item.decode('utf-8')}")
        except:
            print("Decode failed")

if __name__ == "__main__":
    test_enqueue()
