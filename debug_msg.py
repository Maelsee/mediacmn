
import redis
import json
import pickle
from core.config import get_settings

def inspect_queue():
    s = get_settings()
    r = redis.from_url(s.REDIS_URL)
    
    queue_name = "dramatiq:scan"
    print(f"Inspecting {queue_name}...")
    
    # Peek at the last item (LINDEX -1) - Queue is FIFO, so new tasks are at the end? No, LPUSH/RPOP usually?
    # Dramatiq uses LPUSH to enqueue, so RPOP to dequeue.
    # So the OLDEST item is at index -1, and the NEWEST item is at index 0.
    # Wait, Dramatiq standard: broker.enqueue -> rpush ? Or lpush?
    # RedisBroker uses LPUSH by default. So consumers RPOP.
    # So index 0 is the LAST pushed item (newest), index -1 is the FIRST pushed item (oldest).
    
    msg_data = r.lindex(queue_name, 0)
    if not msg_data:
        print("Queue is empty.")
        return

    print(f"Raw data (first 100 bytes): {msg_data[:100]}")
    
    try:
        # 尝试作为字符串打印，看看是不是被双重编码了
        print(f"Decoded utf-8: {msg_data.decode('utf-8')}")
    except:
        pass

    try:
        # Dramatiq messages are JSON by default in recent versions, but let's check.
        # Wait, Dramatiq uses a custom encoder/decoder. 
        # Standard Dramatiq protocol is JSON.
        msg = json.loads(msg_data)
        print("Parsed JSON Message:")
        print(json.dumps(msg, indent=2))
        
        print(f"Target Queue: {msg.get('queue_name')}")
        print(f"Target Actor: {msg.get('actor_name')}")
        
    except json.JSONDecodeError:
        print("Not JSON. Trying pickle...")
        try:
            msg = pickle.loads(msg_data)
            print("Parsed Pickle Message:")
            print(msg)
        except:
            print("Could not parse message.")

if __name__ == "__main__":
    inspect_queue()
