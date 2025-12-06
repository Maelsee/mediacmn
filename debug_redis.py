
import os
import sys
from pathlib import Path

# Add media-server to sys.path
base_dir = Path(__file__).resolve().parent / "media-server"
sys.path.append(str(base_dir))

from core.config import get_settings
from services.task.broker import get_broker
import redis

def check_redis():
    settings = get_settings()
    print(f"Settings REDIS_URL: {settings.REDIS_URL}")
    
    try:
        r = redis.from_url(settings.REDIS_URL)
        print("Connected to Redis successfully.")
        
        keys = r.keys("*")
        print(f"Found {len(keys)} keys in Redis:")
        for k in keys:
            try:
                print(f" - {k.decode('utf-8')} ({r.type(k).decode('utf-8')})")
                if r.type(k).decode('utf-8') == 'list':
                     print(f"   Length: {r.llen(k)}")
            except:
                print(f" - {k}")
                
    except Exception as e:
        print(f"Failed to connect to Redis: {e}")

if __name__ == "__main__":
    check_redis()
