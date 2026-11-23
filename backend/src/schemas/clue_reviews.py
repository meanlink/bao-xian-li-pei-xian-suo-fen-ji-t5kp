from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


class ClueReviewSubmission(BaseModel):
    expected_revision: int = Field(ge=0)
    evidence_source: Literal["official_record", "original_media", "issuer_confirmation"]
    evidence_reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    finding: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=1000)]
    recommendation: Literal["confirmed", "dismissed"]


class ClueReviewDecision(BaseModel):
    expected_revision: int = Field(ge=1)
    action: Literal["accept", "return"]
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=500)]
