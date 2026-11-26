"""Editorial decisions are independent of catalogue verification snapshots."""
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from backend.app.db.session import Base


class CatalogueMappingDecision(Base):
    __tablename__ = 'ncert_mapping_decisions'
    id = Column(String(36), primary_key=True)
    relationship_id = Column(String(36), ForeignKey('ncert_relationships.id', ondelete='RESTRICT'), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    decision = Column(String(40), nullable=False)
    rationale = Column(Text, nullable=False)
    reviewer_id = Column(String(64), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint('relationship_id', 'revision'),
        CheckConstraint('revision >= 1'),
        CheckConstraint("decision IN ('APPROVED','REJECTED','REVISION_REQUESTED')"),
        CheckConstraint('length(trim(rationale)) BETWEEN 10 AND 4000'),
    )
