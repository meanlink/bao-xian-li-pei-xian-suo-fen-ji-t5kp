import json
import time
from pathlib import Path
import redis
from src.config import REDIS_URL

heartbeat = Path('/app/runtime/worker-heartbeat.txt')
client = redis.from_url(REDIS_URL, decode_responses=True)

while True:
    heartbeat.write_text(str(time.time()), encoding='utf-8')
    event = client.rpop('claim-events')
    if event:
        Path('/app/runtime/worker-events.log').open('a', encoding='utf-8').write(event + '\n')
    time.sleep(3)
