import redis
from app.core.config import settings

class EventBus:
    def __init__(self):
        self.redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    def publish(self, channel, event):
        self.redis.publish(channel, event)

    def subscribe(self, channel):
        pubsub = self.redis.pubsub()
        pubsub.subscribe(channel)
        return pubsub

event_bus = EventBus()
