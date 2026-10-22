import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.llm.base import ChatMessage

logger = logging.getLogger(__name__)


class RedisSessionStore:
    """
    Stateless sliding-window conversation memory backed by Redis (`chat:session:{userId}:{sessionId}`)
    with 30-minute (1800s) inactivity TTL and automatic in-memory fallback for local/offline testing.
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        ttl_seconds: int | None = None,
        max_window_messages: int = 20,
    ) -> None:
        self._redis = redis_client
        self.ttl_seconds = ttl_seconds or settings.SESSION_TTL_SECONDS
        self.max_window_messages = max_window_messages
        self._fallback_memory: dict[str, list[dict[str, Any]]] = {}

    @staticmethod
    def build_key(user_id: str, session_id: str) -> str:
        return f"chat:session:{user_id}:{session_id}"

    def _get_redis(self) -> Any | None:
        if self._redis is not None:
            return self._redis
        if not settings.REDIS_ENABLED:
            return None
        self._redis = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
        )
        return self._redis

    async def get_history(self, user_id: str, session_id: str) -> list[ChatMessage]:
        key = self.build_key(user_id, session_id)
        client = self._get_redis()
        if client is not None:
            try:
                raw = await client.get(key)
                if raw:
                    await client.expire(key, self.ttl_seconds)
                    items = json.loads(raw)
                    return [ChatMessage.model_validate(item) for item in items]
            except Exception as exc:
                logger.debug("Redis unavailable, reading session %s from fallback store: %s", key, exc)

        raw_list = self._fallback_memory.get(key, [])
        return [ChatMessage.model_validate(item) for item in raw_list]

    async def append_messages(
        self,
        user_id: str,
        session_id: str,
        new_messages: list[ChatMessage],
    ) -> list[ChatMessage]:
        existing = await self.get_history(user_id, session_id)
        combined = (existing + new_messages)[-self.max_window_messages :]
        serialized = [msg.model_dump() for msg in combined]
        key = self.build_key(user_id, session_id)

        self._fallback_memory[key] = serialized
        client = self._get_redis()
        if client is not None:
            try:
                await client.set(key, json.dumps(serialized, ensure_ascii=False), ex=self.ttl_seconds)
            except Exception as exc:
                logger.debug("Redis unavailable, saved session %s to fallback store: %s", key, exc)

        return combined

    async def clear_session(self, user_id: str, session_id: str) -> None:
        key = self.build_key(user_id, session_id)
        self._fallback_memory.pop(key, None)
        client = self._get_redis()
        if client is not None:
            try:
                await client.delete(key)
            except Exception as exc:
                logger.debug("Redis unavailable during clear_session for %s: %s", key, exc)


session_store = RedisSessionStore()
