from fastapi import APIRouter, Depends
from src.schemas.claims import ThresholdUpdate
from src.services.claim_service import threshold_check
from src.utils.auth import require_roles
from src.utils.db import get_conn
from src.services.logistic_model import choose_threshold, confusion_matrix, score_claim

router = APIRouter(prefix="/model", tags=["model"])

@router.post("/threshold")
def update_threshold(payload: ThresholdUpdate, user=Depends(require_roles("risk_manager"))):
    return threshold_check(payload.threshold, user["id"])

@router.get("/metrics")
def metrics(user=Depends(require_roles("risk_manager"))):
    with get_conn() as conn:
        rows = conn.execute("SELECT model_score, verified_fraud FROM claims WHERE model_score IS NOT NULL AND verified_fraud IS NOT NULL").fetchall()
        threshold = float(conn.execute("SELECT value FROM settings WHERE key='model_threshold'").fetchone()["value"])
    records = [(float(row["model_score"]), bool(row["verified_fraud"])) for row in rows]
    selected, selected_metrics = choose_threshold(records, 0.25) if records else (threshold, confusion_matrix([], threshold))
    return {"current_threshold": threshold, "selected_threshold": selected, "metrics": selected_metrics, "sample_size": len(records)}
