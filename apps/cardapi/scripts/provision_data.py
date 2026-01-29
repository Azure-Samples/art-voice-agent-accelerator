#!/usr/bin/env python3
"""
Provision decline codes data to Azure DocumentDB (MongoDB Cluster).
This script loads the decline codes from JSON and inserts them into the
cardapi database with minimal interference to existing data.

Authentication: 
- If COSMOS_ADMIN_PASSWORD is set: Uses admin credentials (for provisioning)
- Otherwise: Uses Azure Managed Identity with OIDC
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

from pymongo import MongoClient
from pymongo.auth_oidc import OIDCCallback, OIDCCallbackContext, OIDCCallbackResult
from pymongo.errors import DuplicateKeyError
from azure.identity import DefaultAzureCredential


class AzureIdentityOIDCCallback(OIDCCallback):
    """OIDC callback using Azure Managed Identity."""

    def __init__(self):
        self.credential = DefaultAzureCredential()

    def fetch(self, context: OIDCCallbackContext) -> OIDCCallbackResult:
        """Fetch Azure access token for Cosmos DB."""
        token = self.credential.get_token("https://ossrdbms-aad.database.windows.net/.default").token
        return OIDCCallbackResult(access_token=token)


def main():
    """Load decline codes into DocumentDB using admin credentials or OIDC authentication."""
    # Get connection details from environment
    admin_username = os.getenv("COSMOS_ADMIN_USERNAME")
    admin_password = os.getenv("COSMOS_ADMIN_PASSWORD")
    hostname = os.getenv("COSMOS_HOSTNAME")
    database_name = os.getenv("AZURE_COSMOS_DATABASE_NAME", "cardapi")
    collection_name = os.getenv("AZURE_COSMOS_COLLECTION_NAME", "declinecodes")

    # Determine authentication method
    use_admin_auth = all([admin_username, admin_password, hostname])
    use_oidc_auth = os.getenv("AZURE_COSMOS_CONNECTION_STRING")
    
    if not use_admin_auth and not use_oidc_auth:
        print("ERROR: Must provide either admin credentials (COSMOS_ADMIN_USERNAME, COSMOS_ADMIN_PASSWORD, COSMOS_HOSTNAME) or OIDC connection string (AZURE_COSMOS_CONNECTION_STRING)")
        sys.exit(1)

    # Load decline codes from JSON
    script_dir = Path(__file__).parent.parent
    data_file = script_dir / "database" / "decline_codes_policy_pack.json"

    if not data_file.exists():
        print(f"ERROR: Data file not found: {data_file}")
        sys.exit(1)

    with open(data_file) as f:
        data = json.load(f)

    # Connect to DocumentDB
    try:
        if use_admin_auth:
            # Use admin credentials with PyMongo's built-in parameter handling
            # PyMongo automatically handles URL encoding of credentials
            print(f"[DEBUG] Connecting to {hostname} as {admin_username}...", file=sys.stderr)
            
            try:
                # First try: connection string with embedded credentials
                encoded_username = quote_plus(admin_username)
                encoded_password = quote_plus(admin_password)
                connection_string = f"mongodb+srv://{encoded_username}:{encoded_password}@{hostname}/?retryWrites=false"
                client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
                client.admin.command("ping")
                print(f"✓ Connected to DocumentDB with admin credentials")
            except Exception as conn_error:
                # If connection string parsing fails, try with auth parameters separately
                print(f"[DEBUG] Connection string method failed, trying with separate auth parameters...", file=sys.stderr)
                
                # Second try: use separate authentication parameters (PyMongo handles encoding)
                client = MongoClient(
                    f"mongodb+srv://{hostname}/?retryWrites=false",
                    username=admin_username,
                    password=admin_password,
                    authSource="admin",
                    serverSelectionTimeoutMS=5000
                )
                client.admin.command("ping")
                print(f"✓ Connected to DocumentDB with admin credentials (using auth parameters)")
        else:
            # Use OIDC authentication
            connection_string = os.getenv("AZURE_COSMOS_CONNECTION_STRING")
            callback = AzureIdentityOIDCCallback()
            
            client = MongoClient(
                connection_string,
                authMechanism="MONGODB-OIDC",
                authMechanismProperties={
                    "OIDC_CALLBACK": callback,
                    "ALLOWED_HOSTS": ["*.mongocluster.cosmos.azure.com"],
                },
            )
            client.admin.command("ping")
            print(f"✓ Connected to DocumentDB with OIDC authentication")
    except Exception as e:
        print(f"ERROR: Failed to connect to DocumentDB: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        db = client[database_name]
        collection = db[collection_name]

        # Clear existing data to ensure clean state (optional - remove if you want incremental updates)
        existing_count = collection.count_documents({})
        if existing_count > 0:
            print(f"Clearing {existing_count} existing documents from {collection_name}")
            collection.delete_many({})

        # Insert metadata
        metadata = {
            "_id": "metadata",
            **data["metadata"]
        }
        try:
            collection.insert_one(metadata)
            print(f"✓ Inserted metadata")
        except DuplicateKeyError:
            print(f"✓ Metadata already exists, skipping")

        # Insert numeric codes
        numeric_codes = data.get("numeric_codes", [])
        for code_data in numeric_codes:
            code_data["code_type"] = "numeric"
            try:
                collection.insert_one(code_data)
            except DuplicateKeyError:
                # Update if exists
                collection.replace_one({"code": code_data["code"]}, code_data, upsert=True)

        print(f"✓ Inserted {len(numeric_codes)} numeric codes")

        # Insert alphanumeric codes
        alpha_codes = data.get("alphanumeric_codes", [])
        for code_data in alpha_codes:
            code_data["code_type"] = "alphanumeric"
            try:
                collection.insert_one(code_data)
            except DuplicateKeyError:
                # Update if exists
                collection.replace_one({"code": code_data["code"]}, code_data, upsert=True)

        print(f"✓ Inserted {len(alpha_codes)} alphanumeric codes")

        # Insert scripts
        scripts = {
            "_id": "scripts",
            "scripts": data.get("scripts", {})
        }
        try:
            collection.insert_one(scripts)
            print(f"✓ Inserted scripts dictionary with {len(data.get('scripts', {}))} scripts")
        except DuplicateKeyError:
            collection.replace_one({"_id": "scripts"}, scripts, upsert=True)
            print(f"✓ Updated scripts dictionary with {len(data.get('scripts', {}))} scripts")

        # Insert global_rules if present
        if data.get("global_rules"):
            global_rules = {
                "_id": "global_rules",
                "rules": data.get("global_rules", [])
            }
            try:
                collection.insert_one(global_rules)
                print(f"✓ Inserted {len(data.get('global_rules', []))} global rules")
            except DuplicateKeyError:
                collection.replace_one({"_id": "global_rules"}, global_rules, upsert=True)
                print(f"✓ Updated {len(data.get('global_rules', []))} global rules")

        # Verify counts
        total = collection.count_documents({})
        numeric_count = collection.count_documents({"code_type": "numeric"})
        alpha_count = collection.count_documents({"code_type": "alphanumeric"})

        print(f"\n✓ Data provisioning complete:")
        print(f"  - Total documents: {total}")
        print(f"  - Numeric codes: {numeric_count}")
        print(f"  - Alphanumeric codes: {alpha_count}")
        print(f"  - Scripts: {len(data.get('scripts', {}))}")
        print(f"  - Global rules: {len(data.get('global_rules', []))}")

    except Exception as e:
        print(f"ERROR: Failed to load data: {e}")
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
