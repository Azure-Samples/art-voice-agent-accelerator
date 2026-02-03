#!/usr/bin/env python3
"""
Provision decline codes data to Azure DocumentDB (MongoDB Cluster).
This script loads the decline codes from JSON and inserts them into the
cardapi database with minimal interference to existing data.

Authentication: 
- If COSMOS_ADMIN_PASSWORD is set: Uses admin credentials (for provisioning)
- Otherwise: Uses Azure Managed Identity with OIDC (ENVIRONMENT="azure")
"""

import json
import os
import sys
import warnings
from pathlib import Path
from urllib.parse import quote_plus

# Suppress PyMongo CosmosDB compatibility warnings
warnings.filterwarnings("ignore", message=".*CosmosDB.*")

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError


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
            # Use admin credentials for Cosmos DB MongoDB cluster
            # Note: Cosmos DB requires TLS and doesn't use authSource like traditional MongoDB
            print(f"[DEBUG] Connecting to {hostname} as {admin_username}...", file=sys.stderr)
            print(f"[DEBUG] Password length: {len(admin_password)} chars", file=sys.stderr)
            
            # For Cosmos DB MongoDB vCore, use SCRAM-SHA-256 authentication
            # Don't specify authSource (Cosmos handles this internally)
            encoded_username = quote_plus(admin_username)
            encoded_password = quote_plus(admin_password)
            
            # Build connection string with all required Cosmos DB parameters
            connection_string = (
                f"mongodb+srv://{encoded_username}:{encoded_password}@{hostname}/"
                f"?tls=true&retryWrites=false&authMechanism=SCRAM-SHA-256"
            )
            
            try:
                client = MongoClient(connection_string, serverSelectionTimeoutMS=15000, connectTimeoutMS=15000)
                client.admin.command("ping")
                print(f"✓ Connected to Cosmos DB with admin credentials (SCRAM-SHA-256)")
            except Exception as conn_error:
                print(f"[DEBUG] SCRAM-SHA-256 method failed: {conn_error}", file=sys.stderr)
                
                # Fallback: try without explicit authMechanism (let Cosmos negotiate)
                connection_string_simple = (
                    f"mongodb+srv://{encoded_username}:{encoded_password}@{hostname}/"
                    f"?tls=true&retryWrites=false"
                )
                
                try:
                    client = MongoClient(connection_string_simple, serverSelectionTimeoutMS=15000, connectTimeoutMS=15000)
                    client.admin.command("ping")
                    print(f"✓ Connected to Cosmos DB with admin credentials (auto-negotiated)")
                except Exception as fallback_error:
                    print(f"[DEBUG] Auto-negotiated method also failed: {fallback_error}", file=sys.stderr)
                    raise conn_error  # Raise original error for better diagnostics
        else:
            # Use OIDC authentication with Azure CLI credentials (works locally and in CI/CD)
            import re
            from azure.identity import DefaultAzureCredential
            
            connection_string = os.getenv("AZURE_COSMOS_CONNECTION_STRING")
            
            # Extract cluster name from connection string, stripping any <user>:<password>@ prefix
            match = re.search(r"mongodb\+srv://(?:<[^>]+>:<[^>]+>@)?([^./?]+)", connection_string)
            if match:
                cluster_name = match.group(1)
            else:
                raise ValueError(f"Could not determine cluster name from connection string: {connection_string[:50]}...")
            
            # Use DefaultAzureCredential which tries: Environment > CLI > Managed Identity
            credential = DefaultAzureCredential()
            
            # Define OIDC callback that uses Azure Identity SDK
            def oidc_callback(context):
                token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
                return {"access_token": token.token, "expires_in_seconds": 3600}
            
            # Build OIDC connection string
            oidc_connection_string = f"mongodb+srv://{cluster_name}.mongocluster.cosmos.azure.com/"
            
            client = MongoClient(
                oidc_connection_string,
                connectTimeoutMS=120000,
                tls=True,
                retryWrites=False,
                authMechanism="MONGODB-OIDC",
                authMechanismProperties={"OIDC_CALLBACK": oidc_callback},
            )
            client.admin.command("ping")
            print(f"✓ Connected to Cosmos DB cluster: {cluster_name}")
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
