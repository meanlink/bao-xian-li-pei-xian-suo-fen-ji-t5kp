from fastapi import APIRouter, Depends, HTTPException

from src.schemas.clue_reviews import ClueReviewDecision, ClueReviewSubmission
from src.services.clue_review_service import MissingClue, decide_review, list_clue_reviews, submit_review
from src.utils.auth import current_user, require_roles

router = APIRouter(tags=["clue-reviews"])


@router.get("/clue-reviews")
def reviews(claim_id: int | None = None, user=Depends(current_user)):
    return {"items": list_clue_reviews(claim_id)}


@router.post("/risk-clues/{clue_id}/review/submission")
def submit(clue_id: int, payload: ClueReviewSubmission, user=Depends(require_roles("investigator"))):
    try:
        return submit_review(clue_id, payload, user["id"])
    except MissingClue as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/risk-clues/{clue_id}/review/decision")
def decide(clue_id: int, payload: ClueReviewDecision, user=Depends(require_roles("risk_manager"))):
    try:
        return decide_review(clue_id, payload, user["id"])
    except MissingClue as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
