import pytest

from facereco.infrastructure.quota.redis_quota import RedisSearchQuota

pytestmark = pytest.mark.integration


def test_allows_requests_under_quota(redis_client) -> None:
    quota = RedisSearchQuota(client=redis_client, max_per_minute=3)

    assert quota.check_and_consume("alice") is True
    assert quota.check_and_consume("alice") is True
    assert quota.check_and_consume("alice") is True


def test_denies_requests_over_quota(redis_client) -> None:
    quota = RedisSearchQuota(client=redis_client, max_per_minute=2)

    assert quota.check_and_consume("bob") is True
    assert quota.check_and_consume("bob") is True
    assert quota.check_and_consume("bob") is False


def test_quota_is_isolated_per_actor(redis_client) -> None:
    quota = RedisSearchQuota(client=redis_client, max_per_minute=1)

    assert quota.check_and_consume("alice") is True
    assert quota.check_and_consume("bob") is True
