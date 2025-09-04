import json


def _json(ok: bool, msg: str, **data):
    return json.dumps(
        {"ok": ok, "message": msg, "data": data or None}, ensure_ascii=False
    )
