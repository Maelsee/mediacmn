import os
import sys
import logging
import redis
import uuid
import json
import pickle

# Set up path
sys.path.append(os.path.join(os.getcwd(), "media-server"))

from services.task.broker import get_broker
from services.task.consumers import scan_worker
from core.config import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_enqueue_full():
    # 1. Setup
    s = get_settings()
    r = redis.from_url(s.REDIS_URL)
    
    # 2. Flush
    r.flushall()
    print("--- Redis Flushed ---")
    
    # 3. Configure Actor
    broker = get_broker()
    scan_worker.broker = broker
    
    task_id = uuid.uuid4().hex
    payload = {"test_key": "test_value_123"}
    
    print(f"--- Sending Task {task_id} ---")
    # 4. Send
    msg = scan_worker.send(task_id, payload)
    print(f"Message returned by send: {msg}")
    # Note: actor.send returns the message object or message ID depending on version/config.
    # In Dramatiq, .send() usually returns the Message object.
    
    # 5. Inspect Redis
    print("\n--- Inspecting Redis Keys ---")
    keys = r.keys("*")
    print(f"Keys found: {keys}")
    
    queue_name = "dramatiq:scan"
    if r.exists(queue_name):
        q_len = r.llen(queue_name)
        print(f"Queue '{queue_name}' length: {q_len}")
        
        # Read all items
        items = r.lrange(queue_name, 0, -1)
        for i, item in enumerate(items):
            print(f"\nItem [{i}]:")
            print(f"  Raw: {item}")
            try:
                decoded = item.decode('utf-8')
                print(f"  UTF-8: {decoded}")
                # Try JSON
                try:
                    json_obj = json.loads(decoded)
                    print(f"  JSON: {json.dumps(json_obj, indent=2)}")
                except:
                    print("  Not valid JSON")
            except:
                print("  Not valid UTF-8")
                # Try Pickle
                try:
                    p_obj = pickle.loads(item)
                    print(f"  Pickle: {p_obj}")
                except:
                    print("  Not valid Pickle")
    else:
        print(f"Queue '{queue_name}' does not exist!")

if __name__ == "__main__":
    test_enqueue_full()
