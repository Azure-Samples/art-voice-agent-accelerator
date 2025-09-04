"""
services/cosmosdb_services.py
-----------------------------
Re-export thin wrappers around Azure Cosmos DB that your code already
implements in `src.cosmosdb.*`. Keeping them here isolates the rest of
the app from the direct SDK dependency.
"""

from src.cosmosdb.manager import CosmosDBMongoCoreManager

__all__ = [
    "CosmosDBMongoCoreManager",
]
