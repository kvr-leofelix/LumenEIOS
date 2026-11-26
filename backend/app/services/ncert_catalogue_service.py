"""Read projections and append-only editorial decisions; no curriculum ingestion."""
from datetime import timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from backend.app.models.ncert_catalogue import (
    CatalogueRelease as Release, CatalogueNode as Node, CatalogueText as Text,
    CatalogueEvidence as Evidence, CatalogueSource as Source, CatalogueNodeEvidence as NodeEvidence,
    CatalogueRelationship as Relationship, CatalogueRelationshipEvidence as RelationshipEvidence,
)
from backend.app.models.ncert_review import CatalogueMappingDecision as Review
from backend.app.models.entities import utc_now


def fail(code, message, status=409):
    raise HTTPException(status_code=status, detail={'code': code, 'message': message})


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def release_out(row):
    return {key: utc(getattr(row, key)) if key.endswith('_at') else getattr(row, key)
            for key in ('id', 'release_key', 'edition', 'academic_year', 'status', 'created_at', 'published_at')}


def review_out(row):
    return {key: utc(getattr(row, key)) if key == 'reviewed_at' else getattr(row, key)
            for key in ('id', 'relationship_id', 'revision', 'decision', 'rationale', 'reviewer_id', 'reviewed_at')}


async def release(db, id, user):
    row = await db.get(Release, id)
    if not row:
        fail('NOT_FOUND', 'Release not found', 404)
    if row.status == 'WITHDRAWN':
        fail('RELEASE_UNAVAILABLE', 'Release is withdrawn')
    if row.status == 'DRAFT' and user.role != 'admin':
        fail('FORBIDDEN', 'Only global administrators may inspect drafts', 403)
    return row


async def node(db, id, user):
    row = await db.get(Node, id)
    if not row:
        fail('NOT_FOUND', 'Node not found', 404)
    await release(db, row.release_id, user)
    return row


async def page(db, query, limit, offset, render):
    rows = (await db.scalars(query.offset(offset).limit(limit + 1))).all()
    return {'items': [await render(row) for row in rows[:limit]],
            'next_offset': offset + limit if len(rows) > limit else None}


async def citation(db, evidence_id):
    e = await db.get(Evidence, evidence_id)
    s = await db.get(Source, e.source_id) if e else None
    if not s:
        fail('INVALID_MAPPING', 'Broken source evidence reference')
    visible = s.rights_status in ('METADATA_APPROVED', 'CONTENT_APPROVED') and bool(s.rights_decision and s.rights_decision.strip())
    return dict(evidence_id=e.id, source_id=s.id, document_type=s.document_type,
                source_verification=s.access_status, rights_status=s.rights_status, metadata_visible=visible,
                title=s.title if visible else None, official_url=s.official_url if visible else None,
                edition=s.edition if visible else None, language=s.language if visible else None,
                locator=e.locator if visible else None, notes=e.supported_claim if visible else None)


async def node_out(db, row, language, children=False):
    links = (await db.scalars(select(NodeEvidence).where(NodeEvidence.node_id == row.id).order_by(NodeEvidence.evidence_id))).all()
    citations = [await citation(db, link.evidence_id) for link in links]
    text = await db.scalar(select(Text).where(Text.node_id == row.id, Text.language == language))
    visible = text is not None and text.evidence_id is not None and (await citation(db, text.evidence_id))['metadata_visible']
    result = {key: getattr(row, key) for key in ('id', 'identity_id', 'release_id', 'parent_id', 'kind', 'sequence', 'grade_number', 'verification', 'completeness')}
    result.update(title=text.title if visible else None, requested_language=language,
                  resolved_language=language if visible else None, translation_origin=text.origin if visible else None,
                  citations=citations, children=[])
    if children:
        rows = (await db.scalars(select(Node).where(Node.parent_id == row.id, Node.release_id == row.release_id).order_by(Node.sequence, Node.id))).all()
        result['children'] = [await node_out(db, child, language) for child in rows]
    return result


def descendants(root):
    tree = select(Node.id).where(Node.id == root.id, Node.release_id == root.release_id).cte(recursive=True)
    return tree.union(select(Node.id).join(tree, Node.parent_id == tree.c.id).where(Node.release_id == root.release_id))


async def latest_review(db, id):
    return await db.scalar(select(Review).where(Review.relationship_id == id).order_by(Review.revision.desc()).limit(1))


async def mapping(db, id, user):
    row = await db.get(Relationship, id)
    if not row:
        fail('NOT_FOUND', 'Mapping not found', 404)
    rel = await release(db, row.release_id, user)
    source = await db.get(Node, row.source_node_id)
    dest = await db.get(Node, row.destination_node_id)
    if not source or not dest or source.release_id != row.release_id or dest.release_id != row.release_id or source.kind not in ('TOPIC', 'SUBTOPIC') or dest.kind != 'LEARNING_OUTCOME':
        fail('INVALID_MAPPING', 'Not a same-release topic-to-outcome mapping')
    return row, rel, source, dest


async def mapping_out(db, row, user, language):
    row, rel, source, dest = await mapping(db, row.id, user)
    links = (await db.scalars(select(RelationshipEvidence).where(RelationshipEvidence.relationship_id == row.id).order_by(RelationshipEvidence.role, RelationshipEvidence.evidence_id))).all()
    evidence = [dict(role=link.role, citation=await citation(db, link.evidence_id)) for link in links]
    source_out = await node_out(db, source, language)
    dest_out = await node_out(db, dest, language)
    all_citations = [e['citation'] for e in evidence] + source_out['citations'] + dest_out['citations']
    visible = bool(evidence) and bool(source_out['citations']) and bool(dest_out['citations']) and all(c['metadata_visible'] for c in all_citations)
    review = await latest_review(db, row.id)
    result = {key: getattr(row, key) for key in ('id', 'release_id', 'relationship_type', 'directionality', 'verification', 'creation_method')}
    result.update(source=source_out, destination=dest_out,
                  curriculum_applicability='UNVERIFIED', publication_status=rel.status,
                  permissions_status='CLEARED_FOR_METADATA' if visible else 'PENDING', evidence=evidence,
                  rationale=row.explanation if visible else None,
                  overlapping_outcomes=row.overlapping_outcomes if visible else None,
                  uncovered_outcomes=row.uncovered_outcomes if visible else None,
                  coverage_assessment=row.coverage_assessment if visible else None,
                  human_review_state=review.decision if review else 'AWAITING_REVIEW',
                  revision=review.revision if review else 0, latest_review=review_out(review) if review else None,
                  recovery_eligible=False)
    return result


async def decide(db, id, request, user):
    row, rel, source, dest = await mapping(db, id, user)
    if rel.status != 'DRAFT':
        fail('READ_ONLY_RELEASE', 'Published releases are immutable; review a new draft')
    previous = await latest_review(db, id)
    if request.expected_revision != (previous.revision if previous else 0):
        fail('STALE_REVISION', 'Reload mapping before submitting a decision')
    if previous and previous.decision == request.decision:
        fail('INVALID_TRANSITION', 'A repeated decision is not a state transition')
    if request.decision == 'APPROVED':
        projection = await mapping_out(db, row, user, 'en')
        roles = {e['role'] for e in projection['evidence']}
        if roles != {'SOURCE_ENDPOINT', 'DESTINATION_ENDPOINT', 'RELATIONSHIP'} or not projection['source']['citations'] or not projection['destination']['citations']:
            fail('EVIDENCE_INCOMPLETE', 'Both endpoints and all three relationship evidence roles are required')
        for role, endpoint in (('SOURCE_ENDPOINT', 'source'), ('DESTINATION_ENDPOINT', 'destination')):
            endpoint_ids = {c['evidence_id'] for c in projection[endpoint]['citations']}
            role_ids = {e['citation']['evidence_id'] for e in projection['evidence'] if e['role'] == role}
            if not endpoint_ids.intersection(role_ids):
                fail('EVIDENCE_INCOMPLETE', 'Relationship endpoint evidence must also cite the actual endpoint node')
        all_citations = [e['citation'] for e in projection['evidence']] + projection['source']['citations'] + projection['destination']['citations']
        if not all(c['metadata_visible'] for c in all_citations):
            fail('RIGHTS_BLOCKED', 'Scoped metadata permission is required for approval')
    result = Review(id=str(uuid4()), relationship_id=id, revision=request.expected_revision + 1,
                    decision=request.decision, rationale=request.rationale, reviewer_id=user.id, reviewed_at=utc_now())
    db.add(result)
    try:
        await db.flush()
        # Persist before HTTP201, independent of FastAPI yield cleanup timing.
        await db.commit()
    except IntegrityError:
        await db.rollback()
        fail('STALE_REVISION', 'Another reviewer changed this mapping; reload')
    return review_out(result)
