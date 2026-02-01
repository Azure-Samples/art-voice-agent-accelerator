"""
FastAPI backend for Card Decline Code Lookup API.
Provides REST endpoints for querying decline codes and their descriptions.

Configuration:
    - Loads from Azure App Configuration when deployed
    - Falls back to local JSON file for development
    - AZURE_COSMOS_CONNECTION_STRING: From App Config → azure/cosmos/connection-string
    - AZURE_COSMOS_DATABASE_NAME: Database name (default: cardapi)
    - AZURE_COSMOS_COLLECTION_NAME: Collection name (default: declinecodes)
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

# Add workspace root to path (/app is the root in container, main.py is at /app/backend/main.py)
workspace_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(workspace_root))

print(f"[Bootstrap] Workspace root: {workspace_root}", flush=True)
print("[Bootstrap] Starting App Configuration load...", flush=True)

# Bootstrap Azure App Configuration to load secrets from Key Vault
def _bootstrap_appconfig():
    """Load configuration from Azure App Configuration at startup."""
    print("[Bootstrap] _bootstrap_appconfig() called", flush=True)
    try:
        from azure.appconfiguration import AzureAppConfigurationClient, SecretReferenceConfigurationSetting
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        
        endpoint = os.getenv("AZURE_APPCONFIG_ENDPOINT")
        label = os.getenv("AZURE_APPCONFIG_LABEL", "")
        
        print(f"[Bootstrap] AZURE_APPCONFIG_ENDPOINT={endpoint}", flush=True)
        print(f"[Bootstrap] AZURE_APPCONFIG_LABEL={label}", flush=True)
        
        if not endpoint:
            print("[Bootstrap] AZURE_APPCONFIG_ENDPOINT not set; skipping App Configuration load", flush=True)
            return  # App Config not configured, use direct env vars
        
        print("[Bootstrap] Creating AzureAppConfigurationClient...", flush=True)
        credential = DefaultAzureCredential()
        client = AzureAppConfigurationClient(endpoint, credential)
        print("[Bootstrap] Client created successfully", flush=True)
        
        # Load Cosmos connection string from App Config
        # Key format: azure/cosmos/connection-string
        try:
            print("[Bootstrap] Fetching 'azure/cosmos/connection-string' from App Config...", flush=True)
            kv = client.get_configuration_setting(key="azure/cosmos/connection-string", label=label)
            if kv:
                print(f"[Bootstrap] Setting type: {type(kv).__name__}", flush=True)
                
                # Check if it's a Key Vault reference
                if isinstance(kv, SecretReferenceConfigurationSetting):
                    print(f"[Bootstrap] Detected Key Vault reference: {kv.secret_id}", flush=True)
                    # Parse the Key Vault URL to get vault URI
                    secret_id = kv.secret_id
                    # Format: https://{vault-name}.vault.azure.net/secrets/{secret-name}/{version}
                    vault_url = secret_id.split('/secrets/')[0]
                    secret_name = secret_id.split('/secrets/')[1].split('/')[0]
                    
                    print(f"[Bootstrap] Fetching secret from Key Vault: {vault_url}", flush=True)
                    kv_client = SecretClient(vault_url=vault_url, credential=credential)
                    secret = kv_client.get_secret(secret_name)
                    connection_string = secret.value
                    print(f"[Bootstrap] ✓ Resolved Key Vault reference (length: {len(connection_string)})", flush=True)
                else:
                    # Direct value
                    connection_string = kv.value
                    print(f"[Bootstrap] ✓ Loaded direct value (length: {len(connection_string)})", flush=True)
                
                os.environ["AZURE_COSMOS_CONNECTION_STRING"] = connection_string
                print(f"[Bootstrap] AZURE_COSMOS_CONNECTION_STRING set, starts with: {connection_string[:20]}...", flush=True)
            else:
                print("[Bootstrap] Key returned None from App Configuration", flush=True)
        except Exception as e:
            print(f"[Bootstrap] WARNING: Could not load 'azure/cosmos/connection-string': {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()
            pass  # Key not found, use env var if set
        
        print("[Bootstrap] App Configuration bootstrap complete", flush=True)
            
    except Exception as e:
        # Graceful degradation if app config loading fails
        print(f"[Bootstrap] ERROR: Could not load App Configuration: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()

_bootstrap_appconfig()
print("[Bootstrap] Finished calling _bootstrap_appconfig()", flush=True)


from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from utils.ml_logging import get_logger

logger = get_logger(__name__)


app = FastAPI(
    title="Card Decline Code Lookup API",
    description="REST API for querying debit card and ATM card decline reason codes",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EscalationConfig(BaseModel):
    """Escalation configuration for a decline code."""
    required: bool = Field(..., description="Whether escalation is required")
    target: Optional[str] = Field(None, description="Escalation target (e.g., FRAUD_SERVICING, LOAN_LOC_SERVICE_CENTER)")


class Script(BaseModel):
    """Resolved script content."""
    ref: str = Field(..., description="Script reference identifier")
    title: str = Field(..., description="Script title")
    channels: Optional[List[str]] = Field(None, description="Applicable channels (chat, voice, sms)")
    text: str = Field(..., description="Script text content")
    notes: Optional[str] = Field(None, description="Additional notes or context")


class ContextualRule(BaseModel):
    """Contextual rule for conditional actions."""
    if_condition: dict = Field(..., alias="if", description="Condition to check")
    add_script_refs: Optional[List[str]] = Field(None, description="Additional script references to add")
    add_scripts: Optional[List[Script]] = Field(None, description="Resolved scripts for add_script_refs")
    escalation: Optional[EscalationConfig] = Field(None, description="Override escalation configuration")
    orchestrator_actions: Optional[List[str]] = Field(None, description="Override orchestrator actions")
    
    class Config:
        populate_by_name = True


class DeclineCodePolicy(BaseModel):
    """Model for decline code information with policy pack details."""
    code: str = Field(..., description="The decline code (numeric or alphanumeric)")
    description: str = Field(..., description="Brief description of the decline reason")
    information: str = Field(..., description="Detailed information about the decline")
    actions: List[str] = Field(..., description="Recommended actions to resolve the decline")
    code_type: str = Field(..., description="Type of code: 'numeric' (Base24) or 'alphanumeric' (FAST)")
    script_refs: Optional[List[str]] = Field(None, description="References to customer service scripts")
    scripts: Optional[List[Script]] = Field(None, description="Resolved script content for script_refs")
    orchestrator_actions: Optional[List[str]] = Field(None, description="Actions for voice agent orchestrator")
    contextual_rules: Optional[List[ContextualRule]] = Field(None, description="Conditional rules based on context")
    escalation: Optional[EscalationConfig] = Field(None, description="Escalation requirements")

    class Config:
        populate_by_name = True  # Allow both 'if' and 'if_condition'


class DeclineCodesResponse(BaseModel):
    """Response model for decline codes list."""
    codes: List[DeclineCodePolicy]
    total: int = Field(..., description="Total number of codes returned")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    message: str


# In-memory cache of decline codes loaded from Cosmos DB or local file
decline_codes_data: dict = {}

# Path to local JSON file (for development fallback)
LOCAL_DATA_FILE = Path(__file__).parent.parent / "database" / "decline_codes_policy_pack.json"


def _load_from_local_file() -> dict:
    """Load decline codes from local JSON file (development fallback)."""
    logger.info(f"Loading decline codes from local file: {LOCAL_DATA_FILE}")
    
    with open(LOCAL_DATA_FILE) as f:
        data = json.load(f)
    
    # Add code_type field to each code based on which array it came from
    numeric_codes = data.get("numeric_codes", [])
    for code in numeric_codes:
        code["code_type"] = "numeric"
    
    alphanumeric_codes = data.get("alphanumeric_codes", [])
    for code in alphanumeric_codes:
        code["code_type"] = "alphanumeric"
    
    return {
        "metadata": data.get("metadata", {"source": "local_file"}),
        "numeric_codes": numeric_codes,
        "alphanumeric_codes": alphanumeric_codes,
        "scripts": data.get("scripts", {}),
        "global_rules": data.get("global_rules", []),
    }


def _load_from_cosmos() -> dict:
    """Load decline codes from Cosmos DB using the shared library."""
    from src.cosmosdb.manager import CosmosDBMongoCoreManager
    
    database_name = os.getenv("AZURE_COSMOS_DATABASE_NAME") or "cardapi"
    collection_name = os.getenv("AZURE_COSMOS_COLLECTION_NAME") or "declinecodes"
    
    logger.info(f"Connecting to Cosmos DB: database={database_name}, collection={collection_name}")
    
    manager = CosmosDBMongoCoreManager(
        database_name=database_name,
        collection_name=collection_name,
    )
    
    # Query all documents
    documents = manager.query_documents({}, projection={"_id": 0})
    
    numeric: list = []
    alpha: list = []
    scripts_dict: dict = {}
    global_rules: list = []
    metadata: dict = {}
    
    for doc in documents:
        code_type = (doc.get("code_type") or "").lower()
        if code_type == "numeric":
            numeric.append(doc)
        elif code_type == "alphanumeric":
            alpha.append(doc)
        elif "scripts" in doc:
            scripts_dict = doc.get("scripts", {})
        elif "rules" in doc:
            global_rules = doc.get("rules", [])
        elif doc.get("title") or doc.get("description"):
            metadata = doc
        else:
            logger.warning("Skipping document with unknown structure: %s", doc)
    
    manager.close_connection()
    
    return {
        "metadata": metadata or {
            "source": "azure_cosmosdb",
            "database": database_name,
            "collection": collection_name,
        },
        "numeric_codes": numeric,
        "alphanumeric_codes": alpha,
        "scripts": scripts_dict,
        "global_rules": global_rules,
    }


async def load_decline_codes() -> None:
    """Load decline codes from Cosmos DB or local file fallback."""
    global decline_codes_data

    connection_string = os.getenv("AZURE_COSMOS_CONNECTION_STRING")

    # Use local file if no Cosmos connection string is set
    if not connection_string:
        logger.info("No AZURE_COSMOS_CONNECTION_STRING set; using local file fallback")
        if LOCAL_DATA_FILE.exists():
            decline_codes_data = _load_from_local_file()
            logger.info(
                "Loaded %s numeric, %s alphanumeric decline codes from local file",
                len(decline_codes_data.get("numeric_codes", [])),
                len(decline_codes_data.get("alphanumeric_codes", [])),
            )
        else:
            logger.warning(f"Local data file not found: {LOCAL_DATA_FILE}")
            decline_codes_data = {
                "metadata": {"source": "disabled"},
                "numeric_codes": [],
                "alphanumeric_codes": [],
            }
        return

    # Load from Cosmos DB
    try:
        decline_codes_data = await asyncio.to_thread(_load_from_cosmos)
        logger.info(
            "Loaded %s numeric, %s alphanumeric decline codes, %s scripts from Cosmos DB",
            len(decline_codes_data.get("numeric_codes", [])),
            len(decline_codes_data.get("alphanumeric_codes", [])),
            len(decline_codes_data.get("scripts", {})),
        )
    except Exception as e:
        logger.error(f"Failed to load from Cosmos DB: {e}")
        # Fall back to local file
        if LOCAL_DATA_FILE.exists():
            logger.info("Falling back to local file after Cosmos DB failure")
            decline_codes_data = _load_from_local_file()
        else:
            decline_codes_data = {
                "metadata": {"source": "error"},
                "numeric_codes": [],
                "alphanumeric_codes": [],
            }


def _get_scripts_dict() -> dict:
    """Get scripts dictionary from loaded data."""
    return decline_codes_data.get("scripts", {})


def _resolve_script_refs(script_refs: Optional[List[str]]) -> Optional[List[Script]]:
    """Resolve script references to actual script objects."""
    if not script_refs:
        return None
    
    scripts_dict = _get_scripts_dict()
    resolved_scripts = []
    
    for ref in script_refs:
        if ref in scripts_dict:
            script_data = scripts_dict[ref]
            resolved_scripts.append(Script(
                ref=ref,
                title=script_data.get("title", ""),
                channels=script_data.get("channels"),
                text=script_data.get("text", ""),
                notes=script_data.get("notes")
            ))
        else:
            logger.warning(f"Script reference '{ref}' not found in scripts dictionary")
    
    return resolved_scripts if resolved_scripts else None


def _enrich_code_data(code_data: dict) -> dict:
    """Enrich decline code data with resolved scripts."""
    enriched = code_data.copy()
    
    # Resolve main script references
    if enriched.get("script_refs"):
        enriched["scripts"] = _resolve_script_refs(enriched.get("script_refs"))
    
    # Resolve contextual rule scripts
    if enriched.get("contextual_rules"):
        contextual_rules = enriched.get("contextual_rules", [])
        for rule in contextual_rules:
            if rule.get("add_script_refs"):
                rule["add_scripts"] = _resolve_script_refs(rule.get("add_script_refs"))
    
    return enriched


@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup."""
    try:
        logger.info("Starting Card Decline API...")
        await load_decline_codes()
        logger.info("✓ Card Decline API started successfully")
    except Exception as e:
        logger.error(
            "Failed to load decline codes from Cosmos DB on startup: %s. "
            "API will start with empty data. Error type: %s",
            str(e),
            type(e).__name__,
            exc_info=True
        )


@app.get("/ready")
async def readiness():
    """Readiness probe - returns 200 if data is loaded, 503 if not."""
    if not decline_codes_data.get("numeric_codes") and not decline_codes_data.get("alphanumeric_codes"):
        return {"status": "not_ready", "message": "No decline codes loaded"}, 503
    return {"status": "ready"}


@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint returning API information."""
    return HealthResponse(
        status="healthy",
        message="Card Decline Code Lookup API is running"
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        message="Service is operational"
    )


@app.get("/api/v1/codes", response_model=DeclineCodesResponse)
async def get_all_codes(
    code_type: Optional[str] = Query(None, description="Filter by code type: 'numeric' or 'alphanumeric'")
):
    """
    Get all decline codes, optionally filtered by type.
    
    - **code_type**: Optional filter for 'numeric' or 'alphanumeric' codes
    
    Returns complete policy pack data for each code including resolved script content.
    """
    try:
        if not decline_codes_data.get("numeric_codes") and not decline_codes_data.get("alphanumeric_codes"):
            raise HTTPException(
                status_code=503,
                detail="Decline codes database not initialized. Try again later."
            )
        
        codes = []
        
        if code_type is None or code_type.lower() == "numeric":
            for code_data in decline_codes_data.get("numeric_codes", []):
                enriched = _enrich_code_data(code_data)
                codes.append(DeclineCodePolicy(**enriched))
        
        if code_type is None or code_type.lower() == "alphanumeric":
            for code_data in decline_codes_data.get("alphanumeric_codes", []):
                enriched = _enrich_code_data(code_data)
                codes.append(DeclineCodePolicy(**enriched))
        
        return DeclineCodesResponse(codes=codes, total=len(codes))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving all codes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/api/v1/codes/{code}", response_model=DeclineCodePolicy)
async def get_code(code: str):
    """
    Get information for a specific decline code, including policy pack data.
    
    - **code**: The decline code to lookup (e.g., '02', '51', 'C1', 'RT')
    
    Returns all available data for the code including script_refs, orchestrator_actions, 
    contextual_rules, escalation information, and resolved script content.
    """
    try:
        if not decline_codes_data.get("numeric_codes") and not decline_codes_data.get("alphanumeric_codes"):
            raise HTTPException(
                status_code=503,
                detail="Decline codes database not initialized. Try again later."
            )
        
        code_upper = code.upper()
        
        # Search in numeric codes
        for code_data in decline_codes_data.get("numeric_codes", []):
            if code_data["code"] == code_upper:
                enriched = _enrich_code_data(code_data)
                return DeclineCodePolicy(**enriched)
        
        # Search in alphanumeric codes
        for code_data in decline_codes_data.get("alphanumeric_codes", []):
            if code_data["code"] == code_upper:
                enriched = _enrich_code_data(code_data)
                return DeclineCodePolicy(**enriched)
        
        logger.warning(f"Decline code not found: {code}")
        raise HTTPException(status_code=404, detail=f"Decline code '{code}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving code {code}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/api/v1/search", response_model=DeclineCodesResponse)
async def search_codes(
    q: str = Query(..., description="Search query for description or information"),
    code_type: Optional[str] = Query(None, description="Filter by code type: 'numeric' or 'alphanumeric'")
):
    """
    Search decline codes by description or information text.
    
    - **q**: Search query string
    - **code_type**: Optional filter for 'numeric' or 'alphanumeric' codes
    
    Returns complete policy pack data for matching codes including resolved script content.
    """
    try:
        if not decline_codes_data.get("numeric_codes") and not decline_codes_data.get("alphanumeric_codes"):
            raise HTTPException(
                status_code=503,
                detail="Decline codes database not initialized. Try again later."
            )
        
        query_lower = q.lower()
        matching_codes = []
        
        def matches_query(code_data):
            """Check if code data matches the search query."""
            return (
                query_lower in code_data["description"].lower() or
                query_lower in code_data["information"].lower() or
                any(query_lower in action.lower() for action in code_data["actions"])
            )
        
        if code_type is None or code_type.lower() == "numeric":
            for code_data in decline_codes_data.get("numeric_codes", []):
                if matches_query(code_data):
                    enriched = _enrich_code_data(code_data)
                    matching_codes.append(DeclineCodePolicy(**enriched))
        
        if code_type is None or code_type.lower() == "alphanumeric":
            for code_data in decline_codes_data.get("alphanumeric_codes", []):
                if matches_query(code_data):
                    enriched = _enrich_code_data(code_data)
                    matching_codes.append(DeclineCodePolicy(**enriched))
        
        logger.info(f"Search for '{q}' found {len(matching_codes)} codes")
        return DeclineCodesResponse(codes=matching_codes, total=len(matching_codes))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching codes with query '{q}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/api/v1/metadata")
async def get_metadata():
    """
    Get metadata about the decline codes database.
    """
    try:
        return {
            "metadata": decline_codes_data.get("metadata", {}),
            "numeric_codes_count": len(decline_codes_data.get("numeric_codes", [])),
            "alphanumeric_codes_count": len(decline_codes_data.get("alphanumeric_codes", [])),
            "ready": bool(decline_codes_data.get("numeric_codes") or decline_codes_data.get("alphanumeric_codes"))
        }
    except Exception as e:
        logger.error(f"Error retrieving metadata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
