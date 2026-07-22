"""Implémentation Redis du port SearchQuotaPort — fenêtre glissante par minute.

Mesure de conformité (protection anti-surveillance de masse, §12), pas
seulement de performance : un acteur qui dépasse son quota reçoit 429.
"""

from __future__ import annotations

import redis

from facereco.domain.ports.quota import SearchQuotaPort

_WINDOW_SECONDS = 60


class RedisSearchQuota(SearchQuotaPort):
    def __init__(self, client: redis.Redis, max_per_minute: int) -> None:
        self._redis = client
        self._max_per_minute = max_per_minute

    def check_and_consume(self, actor_id: str) -> bool:
        key = f"facereco:quota:search:{actor_id}"
        count = self._redis.incr(key)
        if count == 1:
            self._redis.expire(key, _WINDOW_SECONDS)
        return count <= self._max_per_minute
