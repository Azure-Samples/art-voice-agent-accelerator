import datetime

from src.cosmosdb.manager import CosmosDBMongoCoreManager
from src.stateful.state_managment import MemoManager
from utils.ml_logging import get_logger

logger = get_logger("postcall_analytics")


def build_and_flush(cm: MemoManager, cosmos: CosmosDBMongoCoreManager):
    """
    Build analytics document from conversation manager and upsert into Cosmos DB
    (MongoDB API, _id = session_id).
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
        # Upsert the document using session_id as unique identifier
        cosmos.upsert_document(document=doc, query={"_id": session_id})
        logger.info(f"Analytics document upserted for session {session_id}")
    except Exception as e:
        logger.error(
            f"Failed to upsert analytics document for session {session_id}: {e}",
            exc_info=True,
        )
