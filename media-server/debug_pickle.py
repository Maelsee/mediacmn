import pickle
import redis
import sys

def inspect_msg():
    r = redis.Redis.from_url("redis://:redis123@localhost:9001")
    msg = r.lindex("dramatiq:scan", 0)
    if not msg:
        print("Empty")
        return

    print(f"Raw: {msg}")
    
    try:
        print("Trying pickle...")
        data = pickle.loads(msg)
        print(f"Pickle: {data}")
    except Exception as e:
        print(f"Pickle failed: {e}")

if __name__ == "__main__":
    inspect_msg()
