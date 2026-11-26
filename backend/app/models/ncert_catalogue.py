"""School-independent NCERT metadata schema. No curriculum content is seeded.

Cross-row provenance/hierarchy/publication rules belong to the future importer;
this foundation deliberately exposes no publication or content-import API.
"""
from uuid import UUID, uuid5
from sqlalchemy import (Column, String, Text, Integer, Boolean, DateTime, JSON,
                        ForeignKey, CheckConstraint, UniqueConstraint, Index, MetaData)
from backend.app.db.session import Base

NAMESPACE = UUID('97c9f8e0-2c87-4d30-9eb3-408e56820611')
KINDS = ('GRADE', 'SUBJECT', 'CHAPTER', 'TOPIC', 'SUBTOPIC', 'LEARNING_OUTCOME')
VERIFICATION = ('SOURCE_VERIFIED', 'EXPERT_VERIFIED', 'AI_SUGGESTED', 'AWAITING_REVIEW', 'REJECTED')
VERIFIED = ('SOURCE_VERIFIED', 'EXPERT_VERIFIED')
COMPLETENESS = ('VERIFIED', 'PARTIAL', 'UNAVAILABLE', 'AWAITING_RIGHTS_REVIEW')
RIGHTS = ('PERMISSION_REQUIRED', 'RIGHTS_REVIEW_REQUIRED', 'METADATA_APPROVED', 'CONTENT_APPROVED', 'DENIED')
RELATIONSHIPS = ('PREREQUISITE', 'SAME_SUBJECT_DEPENDENCY', 'CROSS_SUBJECT_CORRELATION', 'SHARED_LEARNING_OUTCOME', 'CONCEPTUAL_REINFORCEMENT')


def release_id(release_key):
    if not release_key or release_key != release_key.strip():
        raise ValueError('release_key must be nonempty and trimmed')
    return str(uuid5(NAMESPACE, release_key))


def node_id(release_key, identity_id):
    release_id(release_key)
    return str(uuid5(NAMESPACE, release_key + ':' + str(UUID(identity_id))))


def field(type_, nullable=False, **kwargs):
    return Column(type_, nullable=nullable, **kwargs)


def fk(table, nullable=False, primary_key=False):
    return Column(String(36), ForeignKey('ncert_' + table + '.id', ondelete='RESTRICT'),
                  nullable=nullable, index=True, primary_key=primary_key)


def enum_check(column, values):
    return CheckConstraint(column + ' IN (' + ','.join(repr(v) for v in values) + ')', name='ck_' + column)


def model(name, table, columns, constraints=(), composite=False):
    attrs = {'__tablename__': 'ncert_' + table, '__module__': __name__, **columns,
             '__table_args__': tuple(constraints)}
    if not composite:
        attrs['id'] = field(String(36), primary_key=True)
    return type(name, (Base,), attrs)


CatalogueBatch = model('CatalogueBatch', 'batches', dict(
    manifest_sha256=field(String(64), unique=True), importer_version=field(String(40)),
    started_at=field(DateTime(timezone=True)), finished_at=field(DateTime(timezone=True), True),
    status=field(String(40)), report=field(JSON)),
    [enum_check('status', ('STAGED','VALIDATED','PUBLISHED','FAILED'))])
CatalogueRelease = model('CatalogueRelease', 'releases', dict(
    release_key=field(String(120), unique=True), edition=field(Text), academic_year=field(String(9), True),
    status=field(String(40)), created_at=field(DateTime(timezone=True)),
    published_at=field(DateTime(timezone=True), True), batch_id=fk('batches')),
    [enum_check('status', ('DRAFT','PUBLISHED','WITHDRAWN'))])
CatalogueIdentity = model('CatalogueIdentity', 'identities', dict(
    authority_key=field(String(200), unique=True), kind=field(String(40))), [enum_check('kind', KINDS)])
CatalogueNode = model('CatalogueNode', 'nodes', dict(
    release_id=fk('releases'), identity_id=fk('identities'), parent_id=fk('nodes', True),
    kind=field(String(40)), grade_number=field(Integer, True), sequence=field(Integer),
    verification=field(String(40)), completeness=field(String(40)), batch_id=fk('batches')),
    [UniqueConstraint('release_id','identity_id'), UniqueConstraint('release_id','id'),
     UniqueConstraint('release_id','grade_number'), enum_check('kind', KINDS),
     enum_check('verification', VERIFICATION), enum_check('completeness', COMPLETENESS),
     CheckConstraint('sequence >= 0'),
     CheckConstraint("(kind = 'GRADE' AND parent_id IS NULL AND grade_number IS NOT NULL AND grade_number BETWEEN 1 AND 12) OR (kind <> 'GRADE' AND parent_id IS NOT NULL AND grade_number IS NULL)"),
     CheckConstraint('parent_id IS NULL OR parent_id <> id'),
     Index('ix_ncert_nodes_release_kind_parent','release_id','kind','parent_id')])
CatalogueSource = model('CatalogueSource','sources', dict(
    publisher=field(Text), title=field(Text), document_type=field(String(40)), grade_scope=field(Text),
    subject_scope=field(Text), edition=field(Text), publication_year=field(Integer, True),
    language=field(String(35)), official_url=field(Text), retrieved_at=field(DateTime(timezone=True)),
    rights_status=field(String(40)), rights_decision=field(Text, True), access_status=field(String(40))),
    [UniqueConstraint('official_url','language','edition'), enum_check('rights_status',RIGHTS),
     enum_check('access_status',('FULL_REVIEW','DISCOVERY_ONLY','INACCESSIBLE')),
     enum_check('document_type',('TEXTBOOK','SYLLABUS','LEARNING_OUTCOMES','FRAMEWORK','NOTICE','CATALOGUE','GOVERNMENT_REPORT')),
     CheckConstraint("rights_status NOT IN ('METADATA_APPROVED','CONTENT_APPROVED') OR (rights_decision IS NOT NULL AND length(trim(rights_decision)) > 0)")])
CatalogueEvidence = model('CatalogueEvidence','evidence', dict(
    source_id=fk('sources'), locator=field(Text), supported_claim=field(Text), batch_id=fk('batches')),
    [UniqueConstraint('source_id','locator','supported_claim')])
CatalogueText = model('CatalogueText','texts', dict(
    node_id=fk('nodes'), language=field(String(35)), title=field(Text), outcome_text=field(Text,True),
    origin=field(String(40)), source_language=field(String(35)), evidence_id=fk('evidence',True),
    verification=field(String(40)), method=field(Text,True), reviewer=field(Text,True), reviewed_at=field(DateTime(timezone=True),True)),
    [UniqueConstraint('node_id','language'),enum_check('verification',VERIFICATION),
     enum_check('origin',('OFFICIAL_ORIGINAL','OFFICIAL_TRANSLATION','HUMAN_TRANSLATION','MACHINE_TRANSLATION')),
     CheckConstraint("origin NOT IN ('OFFICIAL_ORIGINAL','OFFICIAL_TRANSLATION') OR evidence_id IS NOT NULL"),
     CheckConstraint("origin <> 'MACHINE_TRANSLATION' OR (verification <> 'SOURCE_VERIFIED' AND method IS NOT NULL)")])
CatalogueNodeEvidence = model('CatalogueNodeEvidence','node_evidence',dict(
    node_id=fk('nodes',primary_key=True),evidence_id=fk('evidence',primary_key=True)),composite=True)
CatalogueRelationship = model('CatalogueRelationship','relationships',dict(
    release_id=fk('releases'),source_node_id=fk('nodes'),destination_node_id=fk('nodes'),
    relationship_type=field(String(40)),directionality=field(String(40)),explanation=field(Text),
    overlapping_outcomes=field(Text),uncovered_outcomes=field(Text),coverage_assessment=field(Text),
    verification=field(String(40)),creation_method=field(String(40)),reviewer=field(Text,True),
    reviewed_at=field(DateTime(timezone=True),True),recovery_eligible=field(Boolean,default=False,server_default='false'),batch_id=fk('batches')),
    [UniqueConstraint('release_id','source_node_id','destination_node_id','relationship_type','directionality'),
     enum_check('relationship_type',RELATIONSHIPS),enum_check('verification',VERIFICATION),
     enum_check('directionality',('DIRECTED','SYMMETRIC')),
     enum_check('creation_method',('OFFICIAL_SOURCE_DERIVED','EXPERT_REVIEWED','AI_SUGGESTED','MANUALLY_ENTERED')),
     CheckConstraint('source_node_id <> destination_node_id'),
     CheckConstraint("directionality <> 'SYMMETRIC' OR source_node_id < destination_node_id"),
     CheckConstraint("relationship_type NOT IN ('PREREQUISITE','SAME_SUBJECT_DEPENDENCY') OR directionality = 'DIRECTED'"),
     CheckConstraint("relationship_type NOT IN ('SHARED_LEARNING_OUTCOME','CONCEPTUAL_REINFORCEMENT') OR directionality = 'SYMMETRIC'"),
     CheckConstraint("verification NOT IN ('SOURCE_VERIFIED','EXPERT_VERIFIED') OR (reviewer IS NOT NULL AND reviewed_at IS NOT NULL)"),
     CheckConstraint("NOT recovery_eligible OR (verification IN ('SOURCE_VERIFIED','EXPERT_VERIFIED') AND length(trim(coverage_assessment)) > 0)")])
CatalogueRelationshipEvidence = model('CatalogueRelationshipEvidence','relationship_evidence',dict(
    relationship_id=fk('relationships',primary_key=True),evidence_id=fk('evidence',primary_key=True),
    role=field(String(40),primary_key=True)),[enum_check('role',('SOURCE_ENDPOINT','DESTINATION_ENDPOINT','RELATIONSHIP'))],composite=True)
CatalogueRelationshipOutcome = model('CatalogueRelationshipOutcome','relationship_outcomes',dict(
    relationship_id=fk('relationships',primary_key=True),outcome_node_id=fk('nodes',primary_key=True)),composite=True)
CatalogueReview = model('CatalogueReview','reviews',dict(
    node_id=fk('nodes',True),relationship_id=fk('relationships',True),reviewer=field(Text),
    reviewed_at=field(DateTime(timezone=True)),decision=field(String(40)),rationale=field(Text)),
    [enum_check('decision',VERIFICATION),CheckConstraint('(node_id IS NULL AND relationship_id IS NOT NULL) OR (node_id IS NOT NULL AND relationship_id IS NULL)')])
CatalogueLineage = model('CatalogueLineage','lineage',dict(
    old_identity_id=fk('identities',primary_key=True),new_identity_id=fk('identities',primary_key=True),
    release_id=fk('releases',primary_key=True),reason=field(String(40)),evidence_id=fk('evidence')),
    [enum_check('reason',('SPLIT','MERGE','REPLACED')),CheckConstraint('old_identity_id <> new_identity_id')],composite=True)

CATALOGUE_MODELS = (CatalogueBatch,CatalogueRelease,CatalogueIdentity,CatalogueNode,
    CatalogueSource,CatalogueEvidence,CatalogueText,CatalogueNodeEvidence,CatalogueRelationship,
    CatalogueRelationshipEvidence,CatalogueRelationshipOutcome,CatalogueReview,CatalogueLineage)


def catalogue_metadata():
    """Independent metadata ensures migration never creates teammate tables."""
    metadata = MetaData()
    for cls in CATALOGUE_MODELS:
        cls.__table__.to_metadata(metadata)
    return metadata
