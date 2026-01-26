---
applyTo: "**/*.py"
---

# Python Code Standards

## Imports & Setup
```python
from __future__ import annotations
from utils.ml_logging import get_logger

logger = get_logger(__name__)
```

## Type Hints
- Full type hints on all functions and methods
- Use `X | None` instead of `Optional[X]`
- Use `TypeVar` for generic classes

## Async Patterns
- All I/O operations must be `async`
- Use explicit timeouts: `await asyncio.wait_for(coro, timeout=5.0)`
- Background tasks: `asyncio.create_task()` with proper lifecycle management
- Never use blocking `requests` — use `aiohttp` or `httpx`

## Error Handling
- Use `HTTPException` for API errors with appropriate status codes
- Always log errors before raising: `logger.error(f"...: {e}")`
- Use `tenacity` for retries (already in deps), not custom retry logic

## Functions Over Classes
```python
# ✅ Prefer
async def process_item(item: Item) -> Result:
    return Result(data=item.transform())

# ❌ Avoid unnecessary abstraction
class ItemProcessor:
    async def process(self, item: Item) -> Result:
        return Result(data=item.transform())
```

## Docstrings
- Include for public functions
- Describe inputs, outputs, and any latency concerns
- Keep concise — one-liner if behavior is obvious
