from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

class ClaimCreate(BaseModel):
    policy_no: str
    customer_name: str
    incident_type: str
    incident_date: date
    loss_amount: Decimal = Field(ge=0)
    region: str
    claimant_phone: str
    required_documents: list[str] = ["身份证明", "事故证明", "损失清单"]
    verified_fraud: bool | None = None

class DocumentVerify(BaseModel):
    received_documents: list[str]

class DocumentFollowupContact(BaseModel):
    channel: Literal["phone", "sms", "email"]
    contacted_on: date
    due_on: date
    contact_note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=500)]
    expected_missing_documents: list[str] = Field(min_length=1)
    followup_id: int | None = Field(default=None, gt=0)
    expected_revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_contact(self):
        if self.due_on < self.contacted_on:
            raise ValueError("补件期限不能早于联系日期")
        if (self.followup_id is None) != (self.expected_revision == 0):
            raise ValueError("再次联系需要补件记录编号和当前版本")
        return self

class InvestigationCreate(BaseModel):
    assignee: str
    priority: str = "high"
    due_date: date
    scope: str

class InvestigationComplete(BaseModel):
    findings: str
    status: str = "completed"

class ThresholdUpdate(BaseModel):
    threshold: float = Field(gt=0, lt=1)
