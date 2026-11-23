import json

from src.utils.db import get_conn


def record_in_transaction(conn, user_id, action, claim_id=None, detail=None):
    conn.execute(
        "INSERT INTO audit_logs(user_id, action, claim_id, detail) VALUES (%s,%s,%s,%s)",
        (user_id, action, claim_id, json.dumps(detail or {}, ensure_ascii=False)),
    )


def record(user_id, action, claim_id=None, detail=None):
    with get_conn() as conn:
        record_in_transaction(conn, user_id, action, claim_id, detail)
