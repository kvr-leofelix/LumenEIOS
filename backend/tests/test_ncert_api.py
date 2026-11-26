"""Synthetic API/storage fixtures only; no NCERT content or runtime seed."""
from uuid import uuid4
import importlib.util
from pathlib import Path
import pytest
import pytest_asyncio
from sqlalchemy import select, delete, create_engine, inspect, text
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from backend.app.core.security import create_refresh_token, create_access_token
from backend.app.models.entities import utc_now
from backend.app.models.ncert_catalogue import (
    CatalogueBatch as Batch, CatalogueRelease as Release, CatalogueIdentity as Identity,
    CatalogueNode as Node, CatalogueSource as Source, CatalogueText as Text,
    CatalogueEvidence as Evidence, CatalogueNodeEvidence as NodeEvidence,
    CatalogueRelationship as Relationship, CatalogueRelationshipEvidence as RelationshipEvidence,
)
from backend.app.models.ncert_review import CatalogueMappingDecision as Review

BASE = '/api/v1/ncert'
def uid(): return str(uuid4())
def auth(token): return {'Authorization': 'Bearer ' + token}


@pytest_asyncio.fixture
async def catalogue(db_session):
    db = db_session
    batch = Batch(id=uid(), manifest_sha256=uuid4().hex * 2, importer_version='synthetic-test', started_at=utc_now(), status='STAGED', report={})
    db.add(batch); await db.flush()
    release = Release(id=uid(), release_key=uid(), edition='SYNTHETIC TEST ONLY', status='DRAFT', created_at=utc_now(), batch_id=batch.id)
    db.add(release); await db.flush()
    nodes = []
    for i, kind in enumerate(('GRADE', 'SUBJECT', 'CHAPTER', 'TOPIC', 'SUBTOPIC', 'LEARNING_OUTCOME')):
        identity = Identity(id=uid(), authority_key='test-' + uid(), kind=kind)
        db.add(identity); await db.flush()
        node = Node(id=uid(), release_id=release.id, identity_id=identity.id, parent_id=nodes[-1].id if nodes else None,
                    kind=kind, grade_number=6 if kind == 'GRADE' else None, sequence=i,
                    verification='AWAITING_REVIEW', completeness='PARTIAL', batch_id=batch.id)
        db.add(node); await db.flush(); nodes.append(node)
    source = Source(id=uid(), publisher='SYNTHETIC', title='Synthetic test source', document_type='TEXTBOOK', grade_scope='6', subject_scope='Synthetic',
        edition='test', publication_year=None, language='en', official_url='https://example.invalid/' + uid(), retrieved_at=utc_now(),
        rights_status='METADATA_APPROVED', rights_decision='Synthetic fixture permission only', access_status='FULL_REVIEW')
    db.add(source); await db.flush()
    evidence = Evidence(id=uid(), source_id=source.id, locator='Synthetic locator', supported_claim='Synthetic evidence only', batch_id=batch.id)
    db.add(evidence); await db.flush()
    for n in nodes:
        db.add(NodeEvidence(node_id=n.id, evidence_id=evidence.id))
        db.add(Text(id=uid(), node_id=n.id, language='en', title='Synthetic ' + n.kind, origin='OFFICIAL_ORIGINAL', source_language='en', evidence_id=evidence.id, verification='AWAITING_REVIEW'))
    mapping = Relationship(id=uid(), release_id=release.id, source_node_id=nodes[3].id, destination_node_id=nodes[5].id,
        relationship_type='PREREQUISITE', directionality='DIRECTED', explanation='Synthetic AI rationale', overlapping_outcomes='Synthetic partial overlap',
        uncovered_outcomes='Synthetic uncovered scope', coverage_assessment='Unverified synthetic assessment', verification='AI_SUGGESTED', creation_method='AI_SUGGESTED',
        recovery_eligible=False, batch_id=batch.id)
    db.add(mapping); await db.flush()
    for role in ('SOURCE_ENDPOINT', 'DESTINATION_ENDPOINT', 'RELATIONSHIP'):
        db.add(RelationshipEvidence(relationship_id=mapping.id, evidence_id=evidence.id, role=role))
    await db.commit()
    yield dict(release=release, nodes=nodes, source=source, mapping=mapping, evidence=evidence)
    # Only this fixture's rows; no production database or teammate test data touched.
    await db.execute(delete(Review).where(Review.relationship_id == mapping.id))
    await db.execute(delete(RelationshipEvidence).where(RelationshipEvidence.relationship_id == mapping.id))
    await db.execute(delete(Relationship).where(Relationship.id == mapping.id))
    ids = [n.id for n in nodes]
    await db.execute(delete(Text).where(Text.node_id.in_(ids)))
    await db.execute(delete(NodeEvidence).where(NodeEvidence.node_id.in_(ids)))
    for n in reversed(nodes): await db.execute(delete(Node).where(Node.id == n.id))
    await db.execute(delete(Evidence).where(Evidence.id == evidence.id))
    await db.execute(delete(Source).where(Source.id == source.id))
    for n in nodes: await db.execute(delete(Identity).where(Identity.id == n.identity_id))
    await db.execute(delete(Release).where(Release.id == release.id))
    await db.execute(delete(Batch).where(Batch.id == batch.id)); await db.commit()


@pytest.mark.asyncio
async def test_empty_and_validation(client, admin_token):
    headers = auth(admin_token)
    response = await client.get(BASE + '/availability?grade=6', headers=headers)
    assert response.status_code == 200
    assert response.json()['status'] == 'NO_RELEASE_SELECTED'
    assert response.json()['resources'] == []
    assert (await client.get(BASE + '/releases', headers=headers)).json() == {'items': [], 'next_offset': None}
    for url in ('/availability?grade=5', '/availability?grade=9', '/availability?grade=6&language=fr', '/availability?grade=6&release_id=bad', '/subjects?grade=6', '/releases?limit=101', '/releases?offset=-1', '/nodes/bad'):
        assert (await client.get(BASE + url, headers=headers)).status_code == 422


@pytest.mark.asyncio
async def test_auth_not_demo_fallback(client, student_token, parent_token):
    for suffix in ('/releases', '/availability?grade=6', '/nodes/' + uid(), '/mappings?release_id=' + uid()):
        assert (await client.get(BASE + suffix)).status_code == 401
        assert (await client.get(BASE + suffix, headers=auth('bad'))).status_code == 401
        for token in (student_token, parent_token):
            assert (await client.get(BASE + suffix, headers=auth(token))).status_code == 403
    for token in (create_refresh_token('user-admin'), create_access_token('missing-user')):
        assert (await client.get(BASE + '/releases', headers=auth(token))).status_code == 401
    # A forged claim in an otherwise valid signed fixture token cannot elevate the DB role.
    spoof = create_access_token('user-teacher-1', role='admin')
    assert (await client.post(BASE + '/mappings/' + uid() + '/reviews', headers=auth(spoof), json=dict(
        decision='REJECTED', rationale='Synthetic rationale.', expected_revision=0))).status_code == 403


@pytest.mark.asyncio
async def test_reads_hierarchy_language_sources_and_mapping(client, admin_token, catalogue):
    h = auth(admin_token); rid = catalogue['release'].id; nodes = catalogue['nodes']; mid = catalogue['mapping'].id
    assert any(r['id'] == rid for r in (await client.get(BASE + '/releases', headers=h)).json()['items'])
    subjects = (await client.get(BASE + f'/subjects?release_id={rid}&grade=6', headers=h)).json()
    assert subjects['items'][0]['id'] == nodes[1].id
    availability = (await client.get(BASE + f'/availability?release_id={rid}&grade=6&subject_identity_id={nodes[1].identity_id}', headers=h)).json()
    assert availability['status'] == 'PARTIAL'
    assert availability['permissions_status'] == 'CLEARED_FOR_METADATA'
    assert availability['missing_resource_types'] == ['FRAMEWORK', 'SYLLABUS', 'LEARNING_OUTCOMES']
    assert len(availability['resources']) == 1
    assert availability['resources'][0]['citations'][0]['locator'] == 'Synthetic locator'
    english = (await client.get(BASE + f'/nodes/{nodes[1].id}', headers=h)).json()
    assert english['title'] == 'Synthetic SUBJECT'
    assert english['children'][0]['id'] == nodes[2].id
    hindi = (await client.get(BASE + f'/nodes/{nodes[1].id}?language=hi', headers=h)).json()
    assert hindi['title'] is None and hindi['resolved_language'] is None
    mappings = (await client.get(BASE + f'/mappings?release_id={rid}&subject_node_id={nodes[1].id}', headers=h)).json()
    assert mappings['items'][0]['id'] == mid
    data = (await client.get(BASE + '/mappings/' + mid, headers=h)).json()
    assert data['verification'] == 'AI_SUGGESTED'
    assert data['human_review_state'] == 'AWAITING_REVIEW' and data['revision'] == 0
    assert data['curriculum_applicability'] == 'UNVERIFIED' and data['recovery_eligible'] is False
    assert len(data['evidence']) == 3


@pytest.mark.asyncio
async def test_persistent_review_history_and_transitions(client, admin_token, catalogue):
    h = auth(admin_token); mid = catalogue['mapping'].id; path = BASE + f'/mappings/{mid}/reviews'
    for revision, decision in enumerate(('APPROVED', 'REVISION_REQUESTED', 'REJECTED', 'APPROVED'), 1):
        response = await client.post(path, headers=h, json=dict(decision=decision, expected_revision=revision - 1, rationale='Synthetic editorial decision rationale.'))
        assert response.status_code == 201, response.text
        assert response.json()['revision'] == revision
        assert response.json()['reviewer_id'] == 'user-admin'
        assert response.json()['reviewed_at'].endswith('Z')
    data = (await client.get(BASE + '/mappings/' + mid, headers=h)).json()
    assert data['verification'] == 'AI_SUGGESTED' and data['human_review_state'] == 'APPROVED'
    assert data['recovery_eligible'] is False and data['publication_status'] == 'DRAFT'
    assert data['curriculum_applicability'] == 'UNVERIFIED'
    history = (await client.get(path + '?limit=2', headers=h)).json()
    assert [r['revision'] for r in history['items']] == [1, 2] and history['next_offset'] == 2
    assert len((await client.get(path + '?offset=2', headers=h)).json()['items']) == 2
    for revision, decision, code in ((0, 'REJECTED', 'STALE_REVISION'), (4, 'APPROVED', 'INVALID_TRANSITION')):
        response = await client.post(path, headers=h, json=dict(decision=decision, expected_revision=revision, rationale='Synthetic rationale.'))
        assert response.status_code == 409 and response.json()['detail']['code'] == code


@pytest.mark.asyncio
async def test_review_validation_and_permissions(client, admin_token, teacher_token, principal_token, catalogue):
    path = BASE + '/mappings/' + catalogue['mapping'].id + '/reviews'
    valid = dict(decision='REJECTED', rationale='Synthetic rationale.', expected_revision=0)
    for token in (teacher_token, principal_token):
        assert (await client.post(path, headers=auth(token), json=valid)).status_code == 403
    for update in ({'decision': 'SOURCE_VERIFIED'}, {'rationale': '          '}, {'expected_revision': -1}, {'expected_revision': '0'}, {'reviewer_id': 'spoof'}, {'rationale': 'x' * 4001}):
        assert (await client.post(path, headers=auth(admin_token), json={**valid, **update})).status_code == 422


@pytest.mark.asyncio
async def test_rights_redaction_and_approval_gate(client, admin_token, catalogue, db_session):
    source = catalogue['source']; source.rights_status = 'PERMISSION_REQUIRED'; source.rights_decision = None
    await db_session.commit(); h = auth(admin_token); mid = catalogue['mapping'].id
    data = (await client.get(BASE + '/mappings/' + mid, headers=h)).json()
    assert data['rationale'] is None and data['source']['title'] is None
    assert all(e['citation']['official_url'] is None for e in data['evidence'])
    body = dict(decision='APPROVED', rationale='Synthetic review rationale.', expected_revision=0)
    response = await client.post(BASE + f'/mappings/{mid}/reviews', headers=h, json=body)
    assert response.status_code == 409 and response.json()['detail']['code'] == 'RIGHTS_BLOCKED'
    assert (await client.post(BASE + f'/mappings/{mid}/reviews', headers=h, json={**body, 'decision': 'REVISION_REQUESTED'})).status_code == 201


@pytest.mark.asyncio
async def test_draft_published_withdrawn_and_not_found(client, admin_token, teacher_token, catalogue, db_session):
    rel = catalogue['release']; mid = catalogue['mapping'].id; h = auth(admin_token)
    url = BASE + '/mappings/' + mid
    assert (await client.get(url, headers=auth(teacher_token))).status_code == 403
    rel.status = 'PUBLISHED'; rel.published_at = utc_now(); await db_session.commit()
    assert (await client.get(url, headers=auth(teacher_token))).status_code == 200
    response = await client.post(url + '/reviews', headers=h, json=dict(decision='REJECTED', rationale='Synthetic rationale.', expected_revision=0))
    assert response.status_code == 409 and response.json()['detail']['code'] == 'READ_ONLY_RELEASE'
    rel.status = 'WITHDRAWN'; await db_session.commit()
    assert (await client.get(url, headers=h)).status_code == 409
    for path in ('/nodes/', '/mappings/'):
        assert (await client.get(BASE + path + uid(), headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_incomplete_evidence_not_approved(client, admin_token, catalogue, db_session):
    mid = catalogue['mapping'].id
    await db_session.execute(delete(RelationshipEvidence).where(RelationshipEvidence.relationship_id == mid, RelationshipEvidence.role == 'RELATIONSHIP'))
    await db_session.commit()
    response = await client.post(BASE + f'/mappings/{mid}/reviews', headers=auth(admin_token), json=dict(decision='APPROVED', rationale='Synthetic rationale.', expected_revision=0))
    assert response.status_code == 409 and response.json()['detail']['code'] == 'EVIDENCE_INCOMPLETE'


def test_additive_review_migration_and_postgres_ddl():
    def load(name):
        spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / 'migrations' / (name + '.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        load('001_ncert_catalogue').upgrade(connection)
        connection.execute(text('CREATE TABLE teammate_data (note TEXT)'))
        connection.execute(text("INSERT INTO teammate_data VALUES ('preserved')"))
        migration = load('002_ncert_mapping_decisions')
        migration.upgrade(connection); migration.upgrade(connection)
        assert 'ncert_mapping_decisions' in inspect(connection).get_table_names()
        assert connection.scalar(text('SELECT note FROM teammate_data')) == 'preserved'
        assert connection.scalar(text('SELECT count(*) FROM ncert_mapping_decisions')) == 0
    assert 'UNIQUE' in str(CreateTable(Review.__table__).compile(dialect=postgresql.dialect()))
    engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_review_has_one_winner(client, admin_token, catalogue):
    import asyncio
    mid = catalogue['mapping'].id
    body = dict(decision='REJECTED', rationale='Synthetic concurrent review.', expected_revision=0)
    url = BASE + f'/mappings/{mid}/reviews'
    responses = await asyncio.gather(*(client.post(url, headers=auth(admin_token), json=body) for _ in range(2)))
    assert sorted(r.status_code for r in responses) == [201, 409]
    history = (await client.get(url, headers=auth(admin_token))).json()
    assert len(history['items']) == 1 and history['items'][0]['revision'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('first,second', [('APPROVED','REJECTED'), ('REJECTED','REVISION_REQUESTED'), ('REVISION_REQUESTED','APPROVED')])
async def test_remaining_allowed_transitions(client, admin_token, catalogue, first, second):
    url = BASE + '/mappings/' + catalogue['mapping'].id + '/reviews'
    for revision, decision in enumerate((first, second)):
        response = await client.post(url, headers=auth(admin_token), json=dict(decision=decision, rationale='Synthetic transition rationale.', expected_revision=revision))
        assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_scope_missing_and_invalid_mapping(client, admin_token, catalogue, db_session):
    h = auth(admin_token); rid = catalogue['release'].id
    assert (await client.get(BASE + f'/availability?grade=6&release_id={rid}', headers=h)).json()['status'] == 'SUBJECT_NOT_SELECTED'
    assert (await client.get(BASE + f'/availability?grade=7&release_id={rid}&subject_identity_id={catalogue["nodes"][1].identity_id}', headers=h)).json()['status'] == 'SUBJECT_NOT_FOUND'
    assert (await client.get(BASE + f'/mappings?release_id={rid}&subject_node_id={catalogue["nodes"][3].id}', headers=h)).status_code == 409
    catalogue['mapping'].destination_node_id = catalogue['nodes'][2].id
    await db_session.commit()
    assert (await client.get(BASE + '/mappings/' + catalogue['mapping'].id, headers=h)).status_code == 409


def test_review_constraint_prevents_duplicate_revision_and_bad_decisions():
    from sqlalchemy.exc import IntegrityError
    from backend.app.models.ncert_catalogue import catalogue_metadata
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        catalogue_metadata().create_all(connection)
        Review.__table__.create(connection)
        # FK-off scratch connection only: isolates audit CHECK/UNIQUE behavior.
        statement = text('INSERT INTO ncert_mapping_decisions (id,relationship_id,revision,decision,rationale,reviewer_id,reviewed_at) VALUES (:id,:rel,:rev,:decision,:rationale,:reviewer,:date)')
        values = dict(id=uid(), rel=uid(), rev=1, decision='APPROVED', rationale='Synthetic valid rationale.', reviewer='test', date='2026-11-10')
        connection.execute(statement, values)
        for change in ({'id': uid()}, {'id': uid(), 'rev': 2, 'decision': 'SOURCE_VERIFIED'}, {'id': uid(), 'rev': 0}, {'id': uid(), 'rev': 2, 'rationale': 'short'}):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(statement, {**values, **change})
    engine.dispose()
