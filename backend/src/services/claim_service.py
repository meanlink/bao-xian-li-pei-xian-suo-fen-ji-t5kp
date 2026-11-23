import json
from datetime import date
from src.services.logistic_model import score_claim, confusion_matrix, choose_threshold
from src.services.clue_review_service import unresolved_review_count
from src.services.document_triage_service import INTAKE_STATES, complete_followup, missing_documents
from src.utils.audit import record, record_in_transaction
from src.utils.db import get_conn
from src.utils.redis_client import publish_event
from src.config import MAX_FALSE_POSITIVE_RATE

def row_claim(row):
    if not row: return None
    item = dict(row)
    for key in ("required_documents", "received_documents", "missing_documents"):
        if isinstance(item.get(key), str): item[key] = json.loads(item[key])
    if item.get("loss_amount") is not None: item["loss_amount"] = float(item["loss_amount"])
    if item.get("model_score") is not None: item["model_score"] = float(item["model_score"])
    if item.get("model_threshold") is not None: item["model_threshold"] = float(item["model_threshold"])
    return item

def list_claims():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM claims ORDER BY created_at DESC").fetchall()
    return [row_claim(row) for row in rows]

def get_claim(claim_id):
    with get_conn() as conn:
        return row_claim(conn.execute("SELECT * FROM claims WHERE id=%s", (claim_id,)).fetchone())

def get_clues(claim_id=None):
    with get_conn() as conn:
        if claim_id:
            rows = conn.execute("SELECT r.*, c.claim_no FROM risk_clues r JOIN claims c ON c.id=r.claim_id WHERE claim_id=%s ORDER BY r.created_at DESC", (claim_id,)).fetchall()
        else:
            rows = conn.execute("SELECT r.*, c.claim_no FROM risk_clues r JOIN claims c ON c.id=r.claim_id ORDER BY r.created_at DESC").fetchall()
    return [dict(row) for row in rows]

def get_tasks():
    with get_conn() as conn:
        rows = conn.execute("SELECT t.*, c.claim_no, c.customer_name, c.risk_level FROM investigation_tasks t JOIN claims c ON c.id=t.claim_id ORDER BY t.due_date ASC, t.id DESC").fetchall()
    return [dict(row) for row in rows]

def verify_documents(claim_id, received, user_id):
    with get_conn() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE id=%s FOR UPDATE", (claim_id,)).fetchone()
        if not claim:
            raise ValueError("案件不存在")
        missing = missing_documents(claim, received)
        if missing and claim["status"] not in INTAKE_STATES:
            raise PermissionError("案件已进入风险分级或后续阶段，不能将资料改回缺项")
        status = "missing" if missing else "complete"
        next_status = "initial_review" if not missing and claim["status"] == "intake" else claim["status"]
        row = conn.execute(
            """UPDATE claims SET received_documents=%s, missing_documents=%s,
                   documents_status=%s, status=%s, updated_at=now() WHERE id=%s RETURNING *""",
            (json.dumps(received, ensure_ascii=False), json.dumps(missing, ensure_ascii=False), status, next_status, claim_id),
        ).fetchone()
        record_in_transaction(conn, user_id, "document_verified", claim_id, {"missing": missing, "documents_status": status})
        if not missing:
            complete_followup(conn, claim_id, user_id)
    return row_claim(row)


def model_claim(claim_id, user_id):
    with get_conn() as conn:
        claim = row_claim(conn.execute("SELECT * FROM claims WHERE id=%s FOR UPDATE", (claim_id,)).fetchone())
        if not claim:
            raise ValueError("案件不存在")
        if claim["documents_status"] != "complete" or missing_documents(claim):
            raise PermissionError("资料缺项，不能进入模型分级")
        clues = conn.execute("SELECT * FROM risk_clues WHERE claim_id=%s", (claim_id,)).fetchall()
        score, features = score_claim(claim, clues)
        threshold = float(conn.execute("SELECT value FROM settings WHERE key='model_threshold'").fetchone()["value"])
        risk = "high" if score >= threshold else "medium" if score >= threshold - 0.16 else "low"
        row = conn.execute("UPDATE claims SET model_score=%s, model_threshold=%s, risk_level=%s, status='modeled', updated_at=now() WHERE id=%s RETURNING *", (score, threshold, risk, claim_id)).fetchone()
        record_in_transaction(conn, user_id, "model_scored", claim_id, {"score": round(score, 4), "threshold": threshold, "features": features})
    publish_event("model_scored", str(claim_id))
    return row_claim(row)


def assign_task(claim_id, payload, user_id):
    claim = get_claim(claim_id)
    if not claim: raise ValueError("案件不存在")
    if claim["status"] != "modeled": raise PermissionError("只有完成模型分级的案件才能派调查任务")
    with get_conn() as conn:
        task = conn.execute("INSERT INTO investigation_tasks(claim_id, assignee, priority, status, due_date, scope) VALUES (%s,%s,%s,'assigned',%s,%s) RETURNING *", (claim_id, payload.assignee, payload.priority, payload.due_date, payload.scope)).fetchone()
        conn.execute("UPDATE claims SET status='investigating', updated_at=now() WHERE id=%s", (claim_id,))
    record(user_id, "investigation_assigned", claim_id, {"task_id": task["id"], "assignee": payload.assignee})
    publish_event("investigation_assigned", str(task["id"]))
    return dict(task)

def complete_task(task_id, payload, user_id):
    with get_conn() as conn:
        task = conn.execute("SELECT * FROM investigation_tasks WHERE id=%s", (task_id,)).fetchone()
        if not task: raise ValueError("调查任务不存在")
        if task["status"] == "completed": raise PermissionError("调查任务已完成")
        row = conn.execute("UPDATE investigation_tasks SET status='completed', findings=%s, completed_at=now() WHERE id=%s RETURNING *", (payload.findings, task_id)).fetchone()
        conn.execute("UPDATE claims SET status='adjudicating', updated_at=now() WHERE id=%s", (task["claim_id"],))
    record(user_id, "investigation_completed", task["claim_id"], {"task_id": task_id})
    return dict(row)

def adjudicate(claim_id, user_id):
    with get_conn() as conn:
        claim = conn.execute("SELECT status FROM claims WHERE id=%s FOR UPDATE", (claim_id,)).fetchone()
        if not claim:
            raise ValueError("案件不存在")
        if claim["status"] != "adjudicating":
            raise PermissionError("调查未完成，不能核赔结案")
        pending = conn.execute("SELECT count(*) AS count FROM investigation_tasks WHERE claim_id=%s AND status != 'completed'", (claim_id,)).fetchone()["count"]
        if pending:
            raise PermissionError("仍有未完成的调查任务")
        if unresolved_review_count(conn, claim_id):
            raise PermissionError("仍有待复核或待补正的线索证据，不能核赔结案")
        row = conn.execute("UPDATE claims SET status='closed', updated_at=now() WHERE id=%s RETURNING *", (claim_id,)).fetchone()
        record_in_transaction(conn, user_id, "claim_adjudicated", claim_id, {"result": "closed"})
    return row_claim(row)

def threshold_check(new_threshold, user_id):
    with get_conn() as conn:
        last_good = float(conn.execute("SELECT value FROM settings WHERE key='last_good_threshold'").fetchone()["value"])
        claims = conn.execute("SELECT model_score, verified_fraud FROM claims WHERE model_score IS NOT NULL AND verified_fraud IS NOT NULL").fetchall()
    records = [(float(row["model_score"]), bool(row["verified_fraud"])) for row in claims]
    metrics = confusion_matrix(records, new_threshold) if records else {"tp": 0, "tn": 0, "fp": 0, "fn": 0, "false_positive_rate": 0.0, "recall": 0.0, "precision": 0.0}
    rolled_back = metrics["false_positive_rate"] > MAX_FALSE_POSITIVE_RATE
    effective = last_good if rolled_back else new_threshold
    with get_conn() as conn:
        if not rolled_back:
            conn.execute("UPDATE settings SET value=%s, updated_at=now() WHERE key='model_threshold'", (str(new_threshold),))
            conn.execute("UPDATE settings SET value=%s, updated_at=now() WHERE key='last_good_threshold'", (str(new_threshold),))
        else:
            conn.execute("UPDATE settings SET value=%s, updated_at=now() WHERE key='model_threshold'", (str(last_good),))
    record(user_id, "threshold_rollback" if rolled_back else "threshold_updated", None, {"requested": new_threshold, "effective": effective, "metrics": metrics})
    return {"requested_threshold": new_threshold, "effective_threshold": effective, "rolled_back": rolled_back, "max_false_positive_rate": MAX_FALSE_POSITIVE_RATE, "metrics": metrics}
