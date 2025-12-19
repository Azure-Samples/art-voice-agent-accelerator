import pytest
from redis.exceptions import MovedError, RedisClusterException
from src.redis import manager as redis_manager
from src.redis.manager import AzureRedisManager


class _FakeRedis:
    def __init__(self) -> None:
        self.hgetall_calls = 0

    def hgetall(self, key: str) -> dict[str, str]:
        self.hgetall_calls += 1
        raise MovedError("1234 127.0.0.1:7001")


class _FakeClusterRedis:
    def __init__(self) -> None:
        self.hgetall_calls = 0

    def hgetall(self, key: str) -> dict[str, str]:
        self.hgetall_calls += 1
        return {"foo": "bar"}


def test_get_session_data_switches_to_cluster(monkeypatch):
    single_node_client = _FakeRedis()
    cluster_client = _FakeClusterRedis()

    # Stub the redis client constructors used inside the manager
    monkeypatch.setattr(
        redis_manager.redis,
        "Redis",
        lambda *args, **kwargs: single_node_client,
    )
    monkeypatch.setattr(
        redis_manager,
        "RedisCluster",
        lambda *args, **kwargs: cluster_client,
    )

    mgr = AzureRedisManager(
        host="example.redis.local",
        port=6380,
        access_key="dummy",
        ssl=False,
        credential=object(),
    )

    data = mgr.get_session_data("session-123")

    assert data == {"foo": "bar"}
    assert single_node_client.hgetall_calls == 1
    assert cluster_client.hgetall_calls == 1
    assert mgr.use_cluster is True


def test_get_session_data_raises_without_cluster_support(monkeypatch):
    single_node_client = _FakeRedis()

    monkeypatch.setattr(
        redis_manager.redis,
        "Redis",
        lambda *args, **kwargs: single_node_client,
    )
    monkeypatch.setattr(
        redis_manager,
        "RedisCluster",
        lambda *args, **kwargs: (_ for _ in ()).throw(RedisClusterException("cluster unavailable")),
    )

    mgr = AzureRedisManager(
        host="example.redis.local",
        port=6380,
        access_key="dummy",
        ssl=False,
        credential=object(),
    )

    with pytest.raises(MovedError):
        mgr.get_session_data("session-123")


def test_cluster_initialization_falls_back_to_standalone(monkeypatch):
    standalone_client = _FakeClusterRedis()
    monkeypatch.setattr(
        redis_manager.redis,
        "Redis",
        lambda *args, **kwargs: standalone_client,
    )
    monkeypatch.setattr(
        redis_manager,
        "RedisCluster",
        lambda *args, **kwargs: (_ for _ in ()).throw(RedisClusterException("cluster unavailable")),
    )

    mgr = AzureRedisManager(
        host="example.redis.local",
        port=6380,
        access_key="dummy",
        ssl=False,
        credential=object(),
        use_cluster=True,
    )

    assert mgr.redis_client is standalone_client
    assert mgr.use_cluster is False
