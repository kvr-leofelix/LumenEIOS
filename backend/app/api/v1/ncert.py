"""Authenticated global catalogue metadata API. See the integration contract."""
from uuid import UUID
import jwt
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import aliased
from backend.app.api.dependencies import oauth2_scheme
from backend.app.core.security import decode_token
from backend.app.db.session import engine
from backend.app.models.entities import User
from backend.app.models.ncert_catalogue import (
    CatalogueRelease as Release, CatalogueNode as Node, CatalogueSource as Source,
    CatalogueNodeEvidence as NodeEvidence, CatalogueEvidence as Evidence, CatalogueRelationship as Relationship,
)
from backend.app.models.ncert_review import CatalogueMappingDecision as Review
from backend.app.schemas.ncert import (
    Language, ReviewRequest, ReviewOut, ReleaseOut, NodeOut, MappingOut, AvailabilityOut, Page,
)
from backend.app.services import ncert_catalogue_service as service

router = APIRouter(prefix='/ncert', tags=['Curriculum Catalogue'])


async def catalogue_db():
    # Enable FKs on this checked-out connection only; never run legacy seed here.
    async with engine.connect() as connection:
        sqlite = connection.dialect.name == 'sqlite'
        original_fk = None
        try:
            if sqlite:
                original_fk = (await connection.exec_driver_sql('PRAGMA foreign_keys')).scalar()
                await connection.exec_driver_sql('PRAGMA foreign_keys=ON')
                if (await connection.exec_driver_sql('PRAGMA foreign_keys')).scalar() != 1:
                    service.fail('DATABASE_UNAVAILABLE', 'Foreign-key enforcement unavailable', 503)
                await connection.commit()
            async with AsyncSession(bind=connection, expire_on_commit=False, autoflush=False) as db:
                try:
                    yield db
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
        except OperationalError:
            service.fail('DATABASE_UNAVAILABLE', 'Catalogue database unavailable; retry later', 503)
        finally:
            if sqlite and original_fk is not None:
                await connection.rollback()
                await connection.exec_driver_sql('PRAGMA foreign_keys=' + ('ON' if original_fk else 'OFF'))
                await connection.commit()


async def reader(token=Depends(oauth2_scheme), db=Depends(catalogue_db)):
    if not token:
        service.fail('AUTHENTICATION_REQUIRED', 'Bearer token required, including demo mode', 401)
    try:
        payload = decode_token(token)
        user_id = payload.get('sub')
        if not user_id or payload.get('type') != 'access':
            raise ValueError('missing subject')
    except (jwt.PyJWTError, ValueError):
        service.fail('INVALID_TOKEN', 'Invalid authentication token', 401)
    user = await db.get(User, user_id)
    if not user:
        service.fail('INVALID_TOKEN', 'Authenticated user no longer exists', 401)
    if user.role not in ('admin', 'principal', 'teacher'):
        service.fail('FORBIDDEN', 'Role cannot access global catalogue', 403)
    return user


async def editor(user=Depends(reader)):
    if user.role != 'admin':
        service.fail('FORBIDDEN', 'Global catalogue review requires admin role', 403)
    return user


@router.get('/releases', response_model=Page[ReleaseOut])
async def releases(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(catalogue_db), user=Depends(reader)):
    query = select(Release).where(Release.status.in_(('DRAFT', 'PUBLISHED') if user.role == 'admin' else ('PUBLISHED',))).order_by(Release.id)
    async def render(row): return service.release_out(row)
    return await service.page(db, query, limit, offset, render)


@router.get('/subjects', response_model=Page[NodeOut])
async def subjects(release_id: UUID, grade: int = Query(..., ge=6, le=8), language: Language = 'en',
                   limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(catalogue_db), user=Depends(reader)):
    await service.release(db, str(release_id), user)
    parent = aliased(Node)
    query = select(Node).join(parent, Node.parent_id == parent.id).where(Node.release_id == str(release_id),
        Node.kind == 'SUBJECT', parent.kind == 'GRADE', parent.release_id == Node.release_id, parent.grade_number == grade).order_by(Node.id)
    return await service.page(db, query, limit, offset, lambda row: service.node_out(db, row, language))


@router.get('/availability', response_model=AvailabilityOut)
async def availability(grade: int = Query(..., ge=6, le=8), release_id: UUID | None = None,
                       subject_identity_id: UUID | None = None, language: Language = 'en', db=Depends(catalogue_db), user=Depends(reader)):
    required = ['FRAMEWORK', 'SYLLABUS', 'LEARNING_OUTCOMES', 'TEXTBOOK']
    result = dict(grade=grade, requested_language=language, release=None, subject=None, status='NO_RELEASE_SELECTED',
                  resources=[], missing_resource_types=required, permissions_status='NOT_EVALUATED', applicability='UNVERIFIED')
    if release_id is None:
        return result
    rel = await service.release(db, str(release_id), user)
    result.update(release=service.release_out(rel), status='SUBJECT_NOT_SELECTED')
    if subject_identity_id is None:
        return result
    parent = aliased(Node)
    subject = await db.scalar(select(Node).join(parent, Node.parent_id == parent.id).where(Node.release_id == rel.id,
        Node.identity_id == str(subject_identity_id), Node.kind == 'SUBJECT', parent.kind == 'GRADE',
        parent.release_id == rel.id, parent.grade_number == grade))
    if subject is None:
        result['status'] = 'SUBJECT_NOT_FOUND'
        return result
    tree = service.descendants(subject)
    links = (await db.scalars(select(NodeEvidence).join(Evidence, Evidence.id == NodeEvidence.evidence_id)
        .join(Source, Source.id == Evidence.source_id).where(NodeEvidence.node_id.in_(select(tree.c.id)),
            Source.language == language).order_by(NodeEvidence.evidence_id))).all()
    resources = {}
    for link in links:
        c = await service.citation(db, link.evidence_id)
        entry = resources.setdefault(c['source_id'], dict(source_id=c['source_id'], document_type=c['document_type'],
            language=c['language'], rights_status=c['rights_status'], source_verification=c['source_verification'], citations=[]))
        if not any(e['evidence_id'] == c['evidence_id'] for e in entry['citations']):
            entry['citations'].append(c)
    missing = [kind for kind in required if not any(r['document_type'] == kind for r in resources.values())]
    visible = bool(resources) and all(c['metadata_visible'] for r in resources.values() for c in r['citations'])
    result.update(subject=await service.node_out(db, subject, language), resources=sorted(resources.values(), key=lambda r: r['source_id']),
                  missing_resource_types=missing, status='AVAILABLE' if not missing and visible else 'PARTIAL',
                  permissions_status='CLEARED_FOR_METADATA' if visible else 'PENDING')
    return result


@router.get('/nodes/{node_id}', response_model=NodeOut)
async def get_node(node_id: UUID, language: Language = 'en', db=Depends(catalogue_db), user=Depends(reader)):
    return await service.node_out(db, await service.node(db, str(node_id), user), language, children=True)


@router.get('/mappings', response_model=Page[MappingOut])
async def mappings(release_id: UUID, subject_node_id: UUID | None = None, language: Language = 'en',
                   limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(catalogue_db), user=Depends(reader)):
    await service.release(db, str(release_id), user)
    src, dest = aliased(Node), aliased(Node)
    query = select(Relationship).join(src, src.id == Relationship.source_node_id).join(dest, dest.id == Relationship.destination_node_id).where(
        Relationship.release_id == str(release_id), src.release_id == Relationship.release_id, dest.release_id == Relationship.release_id,
        src.kind.in_(('TOPIC', 'SUBTOPIC')), dest.kind == 'LEARNING_OUTCOME')
    if subject_node_id:
        subject = await service.node(db, str(subject_node_id), user)
        if subject.release_id != str(release_id) or subject.kind != 'SUBJECT':
            service.fail('INVALID_MAPPING', 'Subject node must belong to the requested release')
        tree = service.descendants(subject)
        query = query.where(Relationship.source_node_id.in_(select(tree.c.id)))
    return await service.page(db, query.order_by(Relationship.id), limit, offset, lambda row: service.mapping_out(db, row, user, language))


@router.get('/mappings/{mapping_id}', response_model=MappingOut)
async def get_mapping(mapping_id: UUID, language: Language = 'en', db=Depends(catalogue_db), user=Depends(reader)):
    row, *_ = await service.mapping(db, str(mapping_id), user)
    return await service.mapping_out(db, row, user, language)


@router.get('/mappings/{mapping_id}/reviews', response_model=Page[ReviewOut])
async def reviews(mapping_id: UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(catalogue_db), user=Depends(reader)):
    await service.mapping(db, str(mapping_id), user)
    async def render(row): return service.review_out(row)
    return await service.page(db, select(Review).where(Review.relationship_id == str(mapping_id)).order_by(Review.revision), limit, offset, render)


@router.post('/mappings/{mapping_id}/reviews', response_model=ReviewOut, status_code=201)
async def review(mapping_id: UUID, request: ReviewRequest, db=Depends(catalogue_db), user=Depends(editor)):
    return await service.decide(db, str(mapping_id), request, user)
