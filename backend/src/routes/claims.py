from fastapi import APIRouter, Depends, HTTPException
from src.schemas.claims import ClaimCreate, DocumentVerify, InvestigationCreate, InvestigationComplete
from src.services.claim_service import list_claims, get_claim, verify_documents, model_claim, assign_task, complete_task, adjudicate, get_clues, get_tasks
from src.services.clue_review_service import unresolved_review_count
from src.services.document_triage_service import TRIAGE_ROLES, latest_followup
from src.utils.auth import current_user, require_roles
from src.utils.db import get_conn
from src.utils.audit import record
import json

router = APIRouter(tags=["claims"])

def fail(exc):
    if isinstance(exc, PermissionError): raise HTTPException(status_code=409, detail=str(exc))
    raise HTTPException(status_code=400, detail=str(exc))

@router.get("/claims")
def claims(user=Depends(current_user)):
    return {"items": list_claims()}

@router.post("/claims")
def create_claim(payload: ClaimCreate, user=Depends(require_roles("intake_agent", "risk_manager"))):
    with get_conn() as conn:
        duplicate = conn.execute("SELECT id FROM claims WHERE policy_no=%s AND incident_date=%s", (payload.policy_no, payload.incident_date)).fetchone()
        if duplicate: raise HTTPException(status_code=409, detail="同一保单同一事故日期已存在案件")
        claim_no = f"CLM-{payload.incident_date.strftime('%y%m%d')}-{conn.execute('SELECT COALESCE(max(id),0)+1 AS next_id FROM claims').fetchone()['next_id']:04d}"
        row = conn.execute("INSERT INTO claims(claim_no, policy_no, customer_name, incident_type, incident_date, loss_amount, region, claimant_phone, required_documents, verified_fraud) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *", (claim_no, payload.policy_no, payload.customer_name, payload.incident_type, payload.incident_date, payload.loss_amount, payload.region, payload.claimant_phone, json.dumps(payload.required_documents, ensure_ascii=False), payload.verified_fraud)).fetchone()
    record(user["id"], "claim_created", row["id"], {"claim_no": claim_no})
    return row

@router.get("/claims/{claim_id}")
def claim_detail(claim_id: int, user=Depends(current_user)):
    item = get_claim(claim_id)
    if not item: raise HTTPException(status_code=404, detail="案件不存在")
    with get_conn() as conn:
        unresolved_reviews = unresolved_review_count(conn, claim_id)
        followup = latest_followup(conn, claim_id) if user["role"] in TRIAGE_ROLES else None
    return {"claim": item, "clues": get_clues(claim_id), "tasks": [task for task in get_tasks() if task["claim_id"] == claim_id], "unresolved_clue_reviews": unresolved_reviews, "document_followup": followup}

@router.post("/claims/{claim_id}/verify-documents")
def verify(claim_id: int, payload: DocumentVerify, user=Depends(require_roles("intake_agent", "risk_manager"))):
    try: return verify_documents(claim_id, payload.received_documents, user["id"])
    except Exception as exc: fail(exc)

@router.post("/claims/{claim_id}/model")
def model(claim_id: int, user=Depends(require_roles("risk_manager"))):
    try: return model_claim(claim_id, user["id"])
    except Exception as exc: fail(exc)

@router.post("/claims/{claim_id}/investigation")
def investigate(claim_id: int, payload: InvestigationCreate, user=Depends(require_roles("risk_manager"))):
    try: return assign_task(claim_id, payload, user["id"])
    except Exception as exc: fail(exc)

@router.post("/tasks/{task_id}/complete")
def complete(task_id: int, payload: InvestigationComplete, user=Depends(require_roles("investigator", "risk_manager"))):
    try: return complete_task(task_id, payload, user["id"])
    except Exception as exc: fail(exc)

@router.post("/claims/{claim_id}/adjudicate")
def close_claim(claim_id: int, user=Depends(require_roles("risk_manager"))):
    try: return adjudicate(claim_id, user["id"])
    except Exception as exc: fail(exc)

@router.get("/risk-clues")
def clues(user=Depends(current_user)):
    return {"items": get_clues()}

@router.post("/risk-clues")
def add_clue(payload: dict, user=Depends(require_roles("investigator", "risk_manager"))):
    required = {"claim_id", "clue_type", "severity", "description", "evidence"}
    if not required.issubset(payload): raise HTTPException(status_code=422, detail="线索字段不完整")
    with get_conn() as conn:
        row = conn.execute("INSERT INTO risk_clues(claim_id, clue_type, severity, description, evidence, created_by) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *", (payload["claim_id"], payload["clue_type"], payload["severity"], payload["description"], payload["evidence"], user["id"])).fetchone()
    record(user["id"], "risk_clue_added", payload["claim_id"], {"clue_type": payload["clue_type"]})
    return dict(row)

@router.get("/investigations")
def investigations(user=Depends(current_user)):
    return {"items": get_tasks()}
