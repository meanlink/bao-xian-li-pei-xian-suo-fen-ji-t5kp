from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from src.schemas.claims import SettlementRecordCreate
from src.services.monthly_report_service import (
    backfill_settlement_record,
    freeze_monthly_report,
    get_monthly_report,
    list_monthly_reports,
)
from src.utils.auth import current_user, require_roles

router = APIRouter(tags=["monthly reports"])


def checked_month(month: date) -> date:
    if month.day != 1:
        raise HTTPException(status_code=400, detail="月份参数需为当月第一天")
    return month


@router.get("/monthly-reports")
def reports(user=Depends(current_user)):
    return list_monthly_reports()


@router.get("/monthly-reports/{month}")
def report_detail(month: date, user=Depends(current_user)):
    return get_monthly_report(checked_month(month))


@router.post("/monthly-reports/{month}/freeze")
def freeze(month: date, user=Depends(require_roles("risk_manager"))):
    try:
        return freeze_monthly_report(checked_month(month), user["id"])
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/claims/{claim_id}/settlement-record")
def backfill(claim_id: int, payload: SettlementRecordCreate, user=Depends(require_roles("risk_manager"))):
    try:
        return backfill_settlement_record(claim_id, payload.settled_on, user["id"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
