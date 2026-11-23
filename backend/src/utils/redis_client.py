import redis
from src.config import REDIS_URL

client = redis.from_url(REDIS_URL, decode_responses=True)

def publish_event(kind: str, payload: str):
    try:
        client.lpush("claim-events", f"{kind}|{payload}")
    except redis.RedisError:
        pass
