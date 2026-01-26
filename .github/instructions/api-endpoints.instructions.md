---
applyTo: "**/api/**/*.py,**/endpoints/**/*.py,**/handlers/**/*.py"
---

# API Endpoint Standards

## Router Setup
```python
from fastapi import APIRouter, Request, HTTPException, Depends
from utils.ml_logging import get_logger

router = APIRouter()
logger = get_logger(__name__)
```

## Endpoint Pattern
```python
@router.get("/path", response_model=ResponseSchema, tags=["Category"])
async def endpoint_name(request: Request) -> ResponseSchema:
    """Brief description of what this endpoint does."""
    # Access shared resources via request.app.state
    # Return Pydantic model, not dict
```

## Request/Response
- Use Pydantic schemas from `api/v1/schemas/` for all request/response models
- Extend `BaseModel` from `api/v1/models/base.py` for new models
- Never return raw dicts — always use response_model

## Dependency Injection
- Use `Depends()` for auth, sessions, clients
- Access app state: `request.app.state.redis_client`
- WebSocket: use `container_from_ws(ws)`, not direct state access

## Error Responses
```python
# Standard error format
raise HTTPException(status_code=404, detail="Resource not found")

# With logging
logger.error(f"Failed to fetch resource {id}: {e}")
raise HTTPException(status_code=500, detail=str(e))
```

## Tags for OpenAPI
- `Health` — health/readiness endpoints
- `Calls` — call management
- `Agents` — agent operations
- `Voice` — voice/speech operations
