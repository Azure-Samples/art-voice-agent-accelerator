---
name: add-endpoint
description: Add a new FastAPI endpoint to the API
---

# Add Endpoint Skill

Add endpoints to `apps/artagent/backend/api/v1/endpoints/`.

## Endpoint File Template

```python
"""
Endpoint Module
===============

Brief description of endpoints in this module.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from utils.ml_logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class MyRequest(BaseModel):
    """Request model for the endpoint."""
    field1: str = Field(..., description="Required field")
    field2: int | None = Field(None, description="Optional field")


class MyResponse(BaseModel):
    """Response model for the endpoint."""
    success: bool
    data: str


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/resource", response_model=MyResponse, tags=["Category"])
async def get_resource(request: Request) -> MyResponse:
    """
    Get a resource.

    Returns the resource data.
    """
    return MyResponse(success=True, data="result")


@router.post("/resource", response_model=MyResponse, tags=["Category"])
async def create_resource(request: Request, body: MyRequest) -> MyResponse:
    """
    Create a new resource.

    Args:
        body: The resource data to create.
    """
    logger.info("Creating resource: %s", body.field1)
    return MyResponse(success=True, data=body.field1)
```

## Steps

1. Create file in `api/v1/endpoints/` or edit existing
2. Define Pydantic request/response schemas
3. Create async endpoint functions with type hints
4. Include `tags=["Category"]` for OpenAPI grouping
5. Register router in `api/v1/__init__.py`

## Router Registration

In `apps/artagent/backend/api/v1/__init__.py`:

```python
from apps.artagent.backend.api.v1.endpoints import my_module

api_router.include_router(
    my_module.router,
    prefix="/my-resource",
    tags=["MyResource"],
)
```

## Common Patterns

### Access App State
```python
@router.get("/resource")
async def get_resource(request: Request):
    redis = request.app.state.redis_client
    # Use redis...
```

### Path Parameters
```python
@router.get("/resource/{resource_id}")
async def get_resource(resource_id: str) -> MyResponse:
    ...
```

### Query Parameters
```python
@router.get("/resources")
async def list_resources(
    limit: int = 10,
    offset: int = 0,
) -> list[MyResponse]:
    ...
```

### Error Handling
```python
@router.get("/resource/{id}")
async def get_resource(id: str) -> MyResponse:
    resource = await fetch_resource(id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource
```

## OpenAPI Tags

Use consistent tags:
- `Health` - Health/readiness endpoints
- `Calls` - Call management
- `Agents` - Agent operations
- `Voice` - Voice/speech operations
- `Sessions` - Session management

## Schema Location

For reusable schemas, add to `api/v1/schemas/`:

```python
# api/v1/schemas/my_schemas.py
from pydantic import BaseModel

class SharedSchema(BaseModel):
    field: str
```

For models with timestamps/IDs, extend base:

```python
from apps.artagent.backend.api.v1.models.base import BaseModel

class MyModel(BaseModel):
    field: str
    # Automatically gets id, created_at, updated_at
```
