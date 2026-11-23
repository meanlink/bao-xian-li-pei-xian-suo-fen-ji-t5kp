from fastapi import APIRouter, Depends
from src.services.document_triage_service import TRIAGE_ROLES
from src.utils.auth import current_user
from src.utils.db import get_conn

router = APIRouter(tags=["dashboard"])

@router.get("/dashboard")
def dashboard(user=Depends(current_user)):
    with get_conn() as conn:
        claims = conn.execute("SELECT count(*) AS total, count(*) FILTER (WHERE status='intake') AS intake, count(*) FILTER (WHERE status='initial_review') AS initial_review, count(*) FILTER (WHERE status='modeled') AS modeled, count(*) FILTER (WHERE status='investigating') AS investigating, count(*) FILTER (WHERE status='adjudicating') AS adjudicating, count(*) FILTER (WHERE risk_level='high') AS high_risk FROM claims").fetchone()
        tasks = conn.execute("SELECT count(*) FILTER (WHERE status != 'completed') AS pending, count(*) FILTER (WHERE status='completed') AS completed FROM investigation_tasks").fetchone()
        settings = conn.execute("SELECT key,value FROM settings WHERE key IN ('model_threshold','last_good_threshold','max_false_positive_rate')").fetchall()
    return {"claims": dict(claims), "tasks": dict(tasks), "settings": {row["key"]: float(row["value"]) for row in settings}}

@router.get("/audit")
def audit(user=Depends(current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT a.*, u.display_name FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id
               WHERE %s OR a.action NOT IN ('document_followup_recorded', 'document_followup_completed')
               ORDER BY a.created_at DESC, a.id DESC LIMIT 30""",
            (user["role"] in TRIAGE_ROLES,),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}
