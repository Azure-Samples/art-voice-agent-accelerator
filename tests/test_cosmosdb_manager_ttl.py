from datetime import UTC, datetime
from unittest.mock import MagicMock

import pymongo
import pytest
from bson.son import SON
from src.cosmosdb.manager import CosmosDBMongoCoreManager


def _make_manager():
    manager = CosmosDBMongoCoreManager.__new__(CosmosDBMongoCoreManager)
    manager.collection = MagicMock()
    return manager


def test_ensure_ttl_index_reuses_existing_configuration():
    manager = _make_manager()
    manager.collection.list_indexes.return_value = [
        {"name": "ttl_idx", "key": SON([("ttl", 1)]), "expireAfterSeconds": 0}
    ]

    assert manager.ensure_ttl_index("ttl", 0) is True
    manager.collection.drop_index.assert_not_called()
    manager.collection.create_index.assert_not_called()


def test_ensure_ttl_index_recreates_when_expire_differs():
    manager = _make_manager()
    manager.collection.list_indexes.return_value = [
        {"name": "ttl_idx", "key": SON([("ttl", 1)]), "expireAfterSeconds": 60}
    ]
    manager.collection.create_index.return_value = "ttl_idx"

    assert manager.ensure_ttl_index("ttl", 0) is True
    manager.collection.drop_index.assert_called_once_with("ttl_idx")
    manager.collection.create_index.assert_called_once()

    args, kwargs = manager.collection.create_index.call_args
    assert args[0] == [("ttl", pymongo.ASCENDING)]
    assert kwargs["expireAfterSeconds"] == 0


def test_upsert_document_with_ttl_adds_ttl_and_expiry():
    manager = _make_manager()
    manager.upsert_document = MagicMock(return_value="doc123")

    base_doc = {"_id": "client-1", "value": "keep"}
    query = {"_id": base_doc["_id"]}

    result = manager.upsert_document_with_ttl(base_doc, query, 120)

    assert result == "doc123"
    manager.upsert_document.assert_called_once()
    updated_doc = manager.upsert_document.call_args[0][0]

    assert updated_doc is not base_doc
    # TTL field should now contain a datetime object, not an integer
    assert "ttl" in updated_doc
    assert isinstance(updated_doc["ttl"], datetime)
    assert updated_doc["ttl"] > datetime.utcnow()
    assert "expires_at" in updated_doc
    expires_at = datetime.fromisoformat(updated_doc["expires_at"].replace("Z", "+00:00"))
    assert expires_at > datetime.now(UTC)
    assert "ttl" not in base_doc


def test_insert_document_with_ttl_adds_ttl_and_expiry():
    manager = _make_manager()
    manager.insert_document = MagicMock(return_value="doc123")

    base_doc = {"_id": "client-2"}

    result = manager.insert_document_with_ttl(base_doc, 90)

    assert result == "doc123"
    manager.insert_document.assert_called_once()
    inserted_doc = manager.insert_document.call_args[0][0]

    assert inserted_doc is not base_doc
    # TTL field should now contain a datetime object, not an integer
    assert isinstance(inserted_doc["ttl"], datetime)
    assert inserted_doc["ttl"] > datetime.utcnow()
    expires_at = datetime.fromisoformat(inserted_doc["expires_at"].replace("Z", "+00:00"))
    assert expires_at > datetime.now(UTC)
    assert "ttl" not in base_doc


@pytest.mark.parametrize(
    "raw, expected",
    [
        (30, 30),
        ("45", 45),
        (1.9, 1),
        (3_000_000_000, 2_147_483_647),
    ],
)
def test_normalize_ttl_seconds_clamps_and_casts(raw, expected):
    manager = _make_manager()
    assert manager._normalize_ttl_seconds(raw) == expected


def test_normalize_ttl_seconds_rejects_negative():
    manager = _make_manager()
    with pytest.raises(ValueError):
        manager._normalize_ttl_seconds(-1)
