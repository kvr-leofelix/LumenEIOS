from datetime import datetime
from typing import Literal, Generic, TypeVar
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

Language = Literal['en', 'hi', 'ur']
Decision = Literal['APPROVED', 'REJECTED', 'REVISION_REQUESTED']


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Decision
    rationale: str = Field(min_length=10, max_length=4000)
    expected_revision: int = Field(ge=0, strict=True)

    @field_validator('rationale', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    relationship_id: str
    revision: int
    decision: Decision
    rationale: str
    reviewer_id: str
    reviewed_at: datetime


class ReleaseOut(BaseModel):
    id: str
    release_key: str
    edition: str
    academic_year: str | None
    status: str
    created_at: datetime
    published_at: datetime | None


class CitationOut(BaseModel):
    evidence_id: str
    source_id: str
    document_type: str
    source_verification: str
    rights_status: str
    metadata_visible: bool
    title: str | None
    official_url: str | None
    edition: str | None
    language: str | None
    locator: str | None
    notes: str | None


class NodeOut(BaseModel):
    id: str
    identity_id: str
    release_id: str
    parent_id: str | None
    kind: str
    sequence: int
    grade_number: int | None
    title: str | None
    requested_language: Language
    resolved_language: str | None
    translation_origin: str | None
    verification: str
    completeness: str
    citations: list[CitationOut]
    children: list['NodeOut']


class ResourceOut(BaseModel):
    source_id: str
    document_type: str
    language: str | None
    rights_status: str
    source_verification: str
    citations: list[CitationOut]


class AvailabilityOut(BaseModel):
    grade: int
    requested_language: Language
    release: ReleaseOut | None
    subject: NodeOut | None
    status: str
    resources: list[ResourceOut]
    missing_resource_types: list[str]
    permissions_status: str
    applicability: Literal['UNVERIFIED'] = 'UNVERIFIED'


class MappingEvidenceOut(BaseModel):
    role: str
    citation: CitationOut


class MappingOut(BaseModel):
    id: str
    release_id: str
    relationship_type: str
    directionality: str
    source: NodeOut
    destination: NodeOut
    verification: str
    creation_method: str
    curriculum_applicability: Literal['UNVERIFIED']
    publication_status: str
    permissions_status: str
    evidence: list[MappingEvidenceOut]
    rationale: str | None
    overlapping_outcomes: str | None
    uncovered_outcomes: str | None
    coverage_assessment: str | None
    human_review_state: str
    revision: int
    latest_review: ReviewOut | None
    recovery_eligible: Literal[False]


T = TypeVar('T')
class Page(BaseModel, Generic[T]):
    items: list[T]
    next_offset: int | None
