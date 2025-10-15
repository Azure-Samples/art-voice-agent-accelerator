import logging
import os
import re
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymongo
import yaml
from utils.azure_auth import get_credential
from dotenv import load_dotenv
from pymongo.auth_oidc import OIDCCallback, OIDCCallbackContext, OIDCCallbackResult
from pymongo.errors import DuplicateKeyError, NetworkTimeout, PyMongoError

# Initialize logging
logger = logging.getLogger(__name__)

# Suppress CosmosDB compatibility warnings from PyMongo - these are expected when using Azure CosmosDB with MongoDB API
warnings.filterwarnings("ignore", message=".*CosmosDB cluster.*", category=UserWarning)


def _extract_cluster_host(connection_string: Optional[str]) -> Optional[str]:
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
        connection_string: Optional[str] = None,
        database_name: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        """
        Initialize the CosmosDBMongoCoreManager for connecting to Cosmos DB using MongoDB API.
        """
        load_dotenv()
        connection_string = connection_string or os.getenv(
            "AZURE_COSMOS_CONNECTION_STRING"
        )

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
                        raise ValueError(
                            "Could not determine cluster name for OIDC authentication"
                        )

                # Setup Azure Identity credential for OIDC
                credential = get_credential()
                auth_callback = AzureIdentityTokenCallback(credential)
                auth_properties = {"OIDC_CALLBACK": auth_callback}

                # Override connection string for OIDC
                connection_string = f"mongodb+srv://{cluster_name}.global.mongocluster.cosmos.azure.com/"
                self.cluster_host = (
                    f"{cluster_name}.global.mongocluster.cosmos.azure.com"
                )

                logger.info(f"Using OIDC authentication for cluster: {cluster_name}")

                self.client = pymongo.MongoClient(
                    connection_string,
                    connectTimeoutMS=120000,
                    tls=True,
                    retryWrites=True,
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

    def insert_document(self, document: Dict[str, Any]) -> Optional[Any]:
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

    def upsert_document(
        self, document: Dict[str, Any], query: Dict[str, Any]
    ) -> Optional[Any]:
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

    def read_document(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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

    def query_documents(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Query multiple documents from the collection based on a query.
        :param query: The query to match documents.
        :return: A list of matching documents.
        """
        try:
            documents = list(self.collection.find(query))
            logger.info(f"Found {len(documents)} documents matching the query.")
            return documents
        except PyMongoError as e:
            logger.error(f"Failed to query documents: {e}")
            return []

    def document_exists(self, query: Dict[str, Any]) -> bool:
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

    def delete_document(self, query: Dict[str, Any]) -> bool:
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

    def close_connection(self):
        """Close the connection to Cosmos DB."""
        self.client.close()
        logger.info("Closed the connection to Cosmos DB.")
