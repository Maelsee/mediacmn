import os
import sys
import redis
import logging
from services.task.broker import get_broker
from core.config import get_settings

# Set up path
sys.path.append(os.path.join(os.getcwd(), "media-server"))

def inspect_msgs():
    s = get_settings()
    r = redis.from_url(s.REDIS_URL)
    
    print("--- Inspecting dramatiq:scan.msgs ---")
    msgs_key = "dramatiq:scan.msgs"
    if r.exists(msgs_key):
        # It's likely a Hash
        type_ = r.type(msgs_key)
        print(f"Type: {type_}")
        
        if type_ == b'hash':
            keys = r.hkeys(msgs_key)
            print(f"Message IDs in hash: {keys}")
            
            # Get the first one
            if keys:
                val = r.hget(msgs_key, keys[0])
                print(f"First message body (raw): {val}")
                try:
                    import pickle
                    decoded = pickle.loads(val)
                    print(f"Decoded (pickle): {decoded}")
                except:
                    print("Not pickle")
    else:
        print("dramatiq:scan.msgs does not exist")

if __name__ == "__main__":
    inspect_msgs()
