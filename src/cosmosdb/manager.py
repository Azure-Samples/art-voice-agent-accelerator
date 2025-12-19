import logging
import os
import re
import time
import warnings
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, TypeVar

import pymongo
from bson.son import SON
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from pymongo.auth_oidc import OIDCCallback, OIDCCallbackContext, OIDCCallbackResult
from pymongo.errors import DuplicateKeyError, NetworkTimeout, PyMongoError
from utils.azure_auth import get_credential

# Initialize logging
logger = logging.getLogger(__name__)

# OpenTelemetry tracer for Cosmos DB operations
_tracer = trace.get_tracer(__name__)

# Type variable for decorator
F = TypeVar("F", bound=Callable[..., Any])

# Suppress CosmosDB compatibility warnings from PyMongo - these are expected when using Azure CosmosDB with MongoDB API
warnings.filterwarnings("ignore", message=".*CosmosDB cluster.*", category=UserWarning)


def _trace_cosmosdb(operation: str) -> Callable[[F], F]:
    """
    Simple decorator for tracing Cosmos DB operations with CLIENT spans.

    Args:
        operation: Database operation name (e.g., "find_one", "insert_one")

    Creates spans visible in App Insights Dependencies view with latency tracking.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(self, *args, **kwargs) -> Any:
            # Get cluster host for server.address attribute
            server_address = getattr(self, "cluster_host", None) or "cosmosdb"
            collection_name = getattr(getattr(self, "collection", None), "name", "unknown")

            with _tracer.start_as_current_span(
                f"cosmosdb.{operation}",
                kind=SpanKind.CLIENT,
                attributes={
                    "peer.service": "cosmosdb",
                    "db.system": "cosmosdb",
                    "db.operation": operation,
                    "db.name": collection_name,
                    "server.address": server_address,
                },
            ) as span:
                start_time = time.perf_counter()
                try:
                    result = func(self, *args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    span.set_attribute("db.operation.duration_ms", duration_ms)

        return wrapper  # type: ignore

    return decorator


def _extract_cluster_host(connection_string: str | None) -> str | None:
    if not connection_string:
        return None
    host_match = re.search(r"@([^/?]+)", connection_string)
    if not host_match:
        host_match = re.search(r"mongodb\+srv://([^/?]+)", connection_string)
    if not host_match:
        return None
    host = host_match.group(1)
    host = host.split(",")[0]
    if ":" in host:
        host = host.split(":")[0]
    return host


class AzureIdentityTokenCallback(OIDCCallback):
    def __init__(self, credential):
        self.credential = credential

    def fetch(self, context: OIDCCallbackContext) -> OIDCCallbackResult:
        token = self.credential.get_token(
            "https://ossrdbms-aad.database.windows.net/.default"
        ).token
        return OIDCCallbackResult(access_token=token)


class CosmosDBMongoCoreManager:
    def __init__(
        self,
        connection_string: str | None = None,
        database_name: str | None = None,
        collection_name: str | None = None,
    ):
        """
        Initialize the CosmosDBMongoCoreManager for connecting to Cosmos DB using MongoDB API.
        """
        load_dotenv()
        connection_string = connection_string or os.getenv("AZURE_COSMOS_CONNECTION_STRING")

        self.cluster_host = _extract_cluster_host(connection_string)

        database_name = database_name or os.getenv("AZURE_COSMOS_DATABASE_NAME")
        collection_name = collection_name or os.getenv("AZURE_COSMOS_COLLECTION_NAME")
        try:
            # Check if connection string contains mongodb-oidc for Azure Entra ID authentication
            if connection_string and "mongodb-oidc" in connection_string.lower():
                # Extract cluster name from connection string or environment
                cluster_name = os.getenv("AZURE_COSMOS_CLUSTER_NAME")
                if not cluster_name:
                    # Try to extract from connection string if not in env
                    # Assuming format like mongodb+srv://clustername.global.mongocluster.cosmos.azure.com/
                    match = re.search(r"mongodb\+srv://([^.]+)\.", connection_string)
                    if match:
                        cluster_name = match.group(1)
                    else:
                        raise ValueError("Could not determine cluster name for OIDC authentication")

                # Setup Azure Identity credential for OIDC
                credential = get_credential()
                auth_callback = AzureIdentityTokenCallback(credential)
                auth_properties = {"OIDC_CALLBACK": auth_callback}

                # Build connection string for OIDC with required parameters
                connection_string = (
                    f"mongodb+srv://{cluster_name}.global.mongocluster.cosmos.azure.com/"
                    "?tls=true&authMechanism=MONGODB-OIDC&retrywrites=false&maxIdleTimeMS=120000"
                )
                self.cluster_host = f"{cluster_name}.global.mongocluster.cosmos.azure.com"

                logger.info(f"Using OIDC authentication for cluster: {cluster_name}")
                logger.debug(f"OIDC connection string: {connection_string}")

                self.client = pymongo.MongoClient(
                    connection_string,
                    connectTimeoutMS=120000,
                    tls=True,
                    retryWrites=False,  # Cosmos DB MongoDB vCore doesn't support retryWrites
                    maxIdleTimeMS=120000,
                    authMechanism="MONGODB-OIDC",
                    authMechanismProperties=auth_properties,
                )
            else:
                auth_properties = None
                logger.info("Using standard connection string authentication")

                # Initialize the MongoClient with the connection string
                self.client = pymongo.MongoClient(connection_string)
                if not self.cluster_host:
                    self.cluster_host = _extract_cluster_host(connection_string)
            self.database = self.client[database_name]
            self.collection = self.database[collection_name]
            logger.info(
                f"Connected to Cosmos DB database: '{database_name}', collection: '{collection_name}'"
            )
        except PyMongoError as e:
            logger.error(f"Failed to connect to Cosmos DB: {e}")
            raise

    @_trace_cosmosdb("insert_one")
    def insert_document(self, document: dict[str, Any]) -> Any | None:
        """
        Insert a document into the collection. If the document with the same _id already exists, it will raise a DuplicateKeyError.
        :param document: The document data to insert.
        :return: The inserted document's ID or None if an error occurred.
        """
        try:
            result = self.collection.insert_one(document)
            logger.info(f"Inserted document with _id: {result.inserted_id}")
            return result.inserted_id
        except DuplicateKeyError as e:
            logger.error(f"Duplicate key error while inserting document: {e}")
            return None
        except PyMongoError as e:
            logger.error(f"Failed to insert document: {e}")
            return None

    @_trace_cosmosdb("upsert")
    def upsert_document(self, document: dict[str, Any], query: dict[str, Any]) -> Any | None:
        """
        Upsert (insert or update) a document into the collection. If a document matching the query exists, it will update the document, otherwise it inserts a new one.
        :param document: The document data to upsert.
        :param query: The query to find an existing document to update.
        :return: The upserted document's ID if a new document is inserted, None otherwise.
        """
        try:
            # Try updating the document; insert if it doesn't exist
            result = self.collection.update_one(query, {"$set": document}, upsert=True)
            if result.upserted_id:
                logger.info(f"Upserted document with _id: {result.upserted_id}")
                return result.upserted_id
            else:
                logger.info(f"Updated document matching query: {query}")
                return None
        except NetworkTimeout as e:
            logger.warning(f"Network timeout during upsert for query {query}: {e}")
            raise
        except PyMongoError as e:
            logger.error(f"Failed to upsert document for query {query}: {e}")
            raise

    @_trace_cosmosdb("find_one")
    def read_document(self, query: dict[str, Any]) -> dict[str, Any] | None:
        """
        Read a document from the collection based on a query.
        :param query: The query to match the document.
        :return: The matched document or None if not found.
        """
        try:
            document = self.collection.find_one(query)
            if document:
                logger.info(f"Found document: {document}")
            else:
                logger.warning("No document found for the given query.")
            return document
        except PyMongoError as e:
            logger.error(f"Failed to read document: {e}")
            return None

    @_trace_cosmosdb("find")
    def query_documents(
        self,
        query: dict[str, Any],
        projection: dict[str, Any] | None = None,
        sort: Sequence[tuple[str, int]] | None = None,
        skip: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query multiple documents from the collection based on a query.

        Args:
            query: Filter used to match documents.
            projection: Optional field projection to apply.
            sort: Optional sort specification passed to Mongo cursor.
            skip: Optional number of documents to skip.
            limit: Optional maximum number of documents to return.

        Returns:
            A list of matching documents.
        """
        try:
            cursor = self.collection.find(query, projection=projection)

            if sort:
                cursor = cursor.sort(list(sort))

            if skip is not None and skip > 0:
                cursor = cursor.skip(skip)

            if limit is not None and limit > 0:
                cursor = cursor.limit(limit)

            documents = list(cursor)
            logger.info(
                "Found %d documents matching the query (limit=%s, skip=%s).",
                len(documents),
                limit if limit is not None else "none",
                skip if skip is not None else 0,
            )
            return documents
        except PyMongoError as e:
            logger.error(f"Failed to query documents: {e}")
            return []

    @_trace_cosmosdb("count")
    def document_exists(self, query: dict[str, Any]) -> bool:
        """
        Check if a document exists in the collection based on a query.
        :param query: The query to match the document.
        :return: True if the document exists, False otherwise.
        """
        try:
            exists = self.collection.count_documents(query) > 0
            if exists:
                logger.info(f"Document matching query {query} exists.")
            else:
                logger.info(f"Document matching query {query} does not exist.")
            return exists
        except PyMongoError as e:
            logger.error(f"Failed to check document existence: {e}")
            return False

    @_trace_cosmosdb("delete_one")
    def delete_document(self, query: dict[str, Any]) -> bool:
        """
        Delete a document from the collection based on a query.
        :param query: The query to match the document to delete.
        :return: True if a document was deleted, False otherwise.
        """
        try:
            result = self.collection.delete_one(query)
            if result.deleted_count > 0:
                logger.info(f"Deleted document matching query: {query}")
                return True
            else:
                logger.warning(f"No document found to delete for query: {query}")
                return False
        except PyMongoError as e:
            logger.error(f"Failed to delete document: {e}")
            return False

    @staticmethod
    def _normalize_ttl_seconds(raw_seconds: Any) -> int:
        """Validate and clamp TTL seconds to Cosmos DB supported range."""
        try:
            seconds = int(raw_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("TTL seconds must be an integer value") from exc

        if seconds < 0:
            raise ValueError("TTL seconds must be non-negative")

        # Cosmos DB (Mongo API) relies on signed 32-bit range for ttl values
        max_supported = 2_147_483_647
        return min(seconds, max_supported)

    @_trace_cosmosdb("create_index")
    def ensure_ttl_index(self, field_name: str = "ttl", expire_seconds: int = 0) -> bool:
        """
        Create TTL index on collection for automatic document expiration.

        Args:
            field_name: Field name to create TTL index on (default: 'ttl')
            expire_seconds: Collection-level expiration (0 = use document-level TTL)

        Returns:
            True if index was created successfully, False otherwise
        """
        try:
            normalized_expire = self._normalize_ttl_seconds(expire_seconds)

            # Detect existing TTL index for the same field
            try:
                existing_indexes = list(self.collection.list_indexes())
            except Exception:  # pragma: no cover - defensive fallback
                existing_indexes = []

            for index in existing_indexes:
                key_spec = index.get("key")
                if isinstance(key_spec, (dict, SON)):
                    key_items = list(key_spec.items())
                else:
                    key_items = list(key_spec or [])

                if key_items == [(field_name, 1)]:
                    current_expire = index.get("expireAfterSeconds")
                    if current_expire == normalized_expire:
                        logger.info("TTL index already configured for '%s'", field_name)
                        return True
                    # Drop stale index so we can recreate with desired settings
                    self.collection.drop_index(index["name"])
                    logger.info("Dropped stale TTL index '%s'", index["name"])
                    break

            index_def = [(field_name, pymongo.ASCENDING)]
            result = self.collection.create_index(
                index_def,
                expireAfterSeconds=normalized_expire,
            )
            logger.info("TTL index created on '%s' field: %s", field_name, result)
            return True

        except ValueError as exc:
            logger.error("Invalid TTL configuration: %s", exc)
            return False
        except Exception as exc:  # pragma: no cover - real backend safeguard
            logger.error("Failed to create TTL index: %s", exc)
            return False

    def upsert_document_with_ttl(
        self, document: dict[str, Any], query: dict[str, Any], ttl_seconds: int
    ) -> Any | None:
        """
        Upsert document with TTL for automatic expiration.

        Args:
            document: Document data to upsert
            query: Query to find existing document
            ttl_seconds: TTL in seconds (e.g., 300 for 5 minutes)

        Returns:
            The upserted document's ID if a new document is inserted, None otherwise
        """
        try:
            # Calculate expiration time as Date object (required for TTL with expireAfterSeconds=0)
            ttl_value = self._normalize_ttl_seconds(ttl_seconds)
            expiration_time = datetime.utcnow() + timedelta(seconds=ttl_value)

            document_with_ttl = document.copy()
            # Store Date object for TTL index (this is what MongoDB TTL requires)
            document_with_ttl["ttl"] = expiration_time
            # Keep string version for human readability/debugging
            document_with_ttl["expires_at"] = expiration_time.isoformat() + "Z"

            # Use the existing upsert method
            result = self.upsert_document(document_with_ttl, query)

            if result:
                logger.info(f"Document upserted with TTL ({ttl_seconds}s): {result}")
            else:
                logger.info(f"Document updated with TTL ({ttl_seconds}s)")

            return result

        except Exception as e:
            logger.error(f"Failed to upsert document with TTL: {e}")
            raise

    def insert_document_with_ttl(self, document: dict[str, Any], ttl_seconds: int) -> Any | None:
        """
        Insert document with TTL for automatic expiration.

        Args:
            document: Document data to insert
            ttl_seconds: TTL in seconds (e.g., 300 for 5 minutes)

        Returns:
            The inserted document's ID or None if an error occurred
        """
        try:
            # Calculate expiration time as Date object (required for TTL with expireAfterSeconds=0)
            ttl_value = self._normalize_ttl_seconds(ttl_seconds)
            expiration_time = datetime.utcnow() + timedelta(seconds=ttl_value)

            document_with_ttl = document.copy()
            # Store Date object for TTL index (this is what MongoDB TTL requires)
            document_with_ttl["ttl"] = expiration_time
            # Keep string version for human readability/debugging
            document_with_ttl["expires_at"] = expiration_time.isoformat() + "Z"

            # Use the existing insert method
            result = self.insert_document(document_with_ttl)

            logger.info(f"Document inserted with TTL ({ttl_seconds}s): {result}")
            return result

        except Exception as e:
            logger.error(f"Failed to insert document with TTL: {e}")
            raise

    def query_active_documents(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Query documents that are still active (not expired).
        This method doesn't rely on TTL cleanup and manually filters expired docs as backup.

        Args:
            query: The query to match documents

        Returns:
            A list of active (non-expired) documents
        """
        try:
            # Get all matching documents
            documents = self.query_documents(query)

            # Filter out manually expired documents (backup for TTL)
            active_documents = []
            current_time = datetime.utcnow()

            for doc in documents:
                expires_at_str = doc.get("expires_at")
                if expires_at_str:
                    try:
                        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                        if expires_at > current_time:
                            active_documents.append(doc)
                    except ValueError:
                        # If parsing fails, include the document (safer approach)
                        active_documents.append(doc)
                else:
                    # No expiration time, include the document
                    active_documents.append(doc)

            logger.info(f"Found {len(active_documents)}/{len(documents)} active documents")
            return active_documents

        except PyMongoError as e:
            logger.error(f"Failed to query active documents: {e}")
            return []

    def close_connection(self):
        """Close the connection to Cosmos DB."""
        self.client.close()
        logger.info("Closed the connection to Cosmos DB.")
