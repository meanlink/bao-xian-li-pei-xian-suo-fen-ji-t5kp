from fastapi import APIRouter, Depends, HTTPException

from src.schemas.claims import DocumentFollowupContact
from src.services.document_triage_service import TRIAGE_ROLES, list_document_triage, log_followup
from src.utils.auth import require_roles

router = APIRouter(tags=["document triage"])
triage_staff = require_roles(*TRIAGE_ROLES)


@router.get("/document-triage")
def queue(user=Depends(triage_staff)):
    return list_document_triage()


@router.post("/claims/{claim_id}/document-followup")
def record_contact(claim_id: int, payload: DocumentFollowupContact, user=Depends(triage_staff)):
    try:
        return log_followup(claim_id, payload, user["id"])
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
