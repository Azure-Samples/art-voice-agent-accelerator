import asyncio
import datetime

from src.cosmosdb.manager import CosmosDBMongoCoreManager
from src.stateful.state_managment import MemoManager
from utils.ml_logging import get_logger
from pymongo.errors import NetworkTimeout

logger = get_logger("postcall_analytics")


def _connectivity_hint(cosmos: CosmosDBMongoCoreManager) -> str:
    host = getattr(cosmos, "cluster_host", None)
    if not host:
        return "nc -vz <cluster>.global.mongocluster.cosmos.azure.com 10260"
    primary_host = host.split(",")[0]
    return f"nc -vz {primary_host} 10260"


async def build_and_flush(cm: MemoManager, cosmos: CosmosDBMongoCoreManager):
    """
    Build analytics document from conversation manager and asynchronously upsert into
    Cosmos DB (MongoDB API, _id = session_id). Executes the write on a worker thread to
    avoid blocking the event loop and adds guidance when connectivity fails.
    """
    session_id = cm.session_id
    histories = cm.histories
    context = cm.context.copy()
    raw_lat = context.pop("latency_roundtrip", {})

    summary = {}
    for stage, entries in raw_lat.items():
        durations = [e.get("dur", 0.0) for e in entries if "dur" in e]
        count = len(durations)
        summary[stage] = {
            "count": count,
            "avg": sum(durations) / count if count else 0.0,
            "min": min(durations) if count else 0.0,
            "max": max(durations) if count else 0.0,
        }

    doc = {
        "_id": session_id,
        "session_id": session_id,
        "timestamp": datetime.datetime.utcnow().replace(microsecond=0).isoformat()
        + "Z",
        "histories": histories,
        "context": context,
        "latency_summary": summary,
        "agents": list(histories.keys()),
    }

    try:
        await asyncio.to_thread(
            cosmos.upsert_document, document=doc, query={"_id": session_id}
        )
        logger.info(f"Analytics document upserted for session {session_id}")
    except NetworkTimeout as err:
        hint = _connectivity_hint(cosmos)
        logger.warning(
            "Cosmos analytics upsert timed out for session %s. Verify network access to the Cosmos Mongo cluster. Test connectivity with `%s`. Details: %s",
            session_id,
            hint,
            err,
        )
    except Exception as e:
        logger.error(
            f"Failed to upsert analytics document for session {session_id}: {e}",
            exc_info=True,
        )
