"""Synthetic storage fixtures; no official curriculum records."""
import importlib.util
from pathlib import Path
import pytest
from sqlalchemy import create_engine,event,text,inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable,CreateIndex
from sqlalchemy.dialects import postgresql
from backend.app.models.ncert_catalogue import catalogue_metadata,release_id,node_id

def migration():
    spec=importlib.util.spec_from_file_location('ncert_migration',Path(__file__).parents[1]/'migrations/001_ncert_catalogue.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.fixture
def connection():
    engine=create_engine('sqlite:///:memory:')
    @event.listens_for(engine,'connect')
    def fk(dbapi,record): dbapi.execute('PRAGMA foreign_keys=ON')
    with engine.begin() as conn:
        migration().upgrade(conn)
        yield conn
    engine.dispose()

def test_additive_idempotent_preserves_teammate_data(connection):
    connection.execute(text('CREATE TABLE teammate_plan (id INTEGER PRIMARY KEY, note TEXT)'))
    connection.execute(text("INSERT INTO teammate_plan VALUES (1,'preserve')"))
    migration().upgrade(connection)
    assert connection.scalar(text('SELECT note FROM teammate_plan'))=='preserve'
    names=[n for n in inspect(connection).get_table_names() if n.startswith('ncert_')]
    assert len(names)==13
    for name in names: assert connection.scalar(text('SELECT count(*) FROM '+name))==0

def test_stable_identity_and_new_release():
    identity='62b02245-3328-4697-b84f-af6c9e5bccaf'
    assert node_id('a',identity)==node_id('a',identity)
    assert node_id('a',identity)!=node_id('b',identity)
    assert release_id('a')!=release_id('b')
    with pytest.raises(ValueError): release_id(' ')
    with pytest.raises(ValueError): node_id('a','bad')

def test_enum_fk_and_rollback(connection):
    assert connection.scalar(text('PRAGMA foreign_keys'))==1
    with pytest.raises(IntegrityError),connection.begin_nested():
        connection.execute(text("INSERT INTO ncert_identities (id,authority_key,kind) VALUES ('test','test','BAD')"))
    assert connection.scalar(text('SELECT count(*) FROM ncert_identities'))==0
    with pytest.raises(IntegrityError),connection.begin_nested():
        connection.execute(text("INSERT INTO ncert_node_evidence VALUES ('missing','missing')"))

def test_approved_rights_require_decision(connection):
    with pytest.raises(IntegrityError),connection.begin_nested():
        connection.execute(text("INSERT INTO ncert_sources (id,publisher,title,document_type,grade_scope,subject_scope,edition,language,official_url,retrieved_at,rights_status,access_status) VALUES ('test','test','test','NOTICE','','','','en','https://example.invalid','2026-11-09','CONTENT_APPROVED','DISCOVERY_ONLY')"))

def test_postgresql_schema_compiles():
    metadata=catalogue_metadata()
    assert len(metadata.tables)==13
    for table in metadata.sorted_tables:
        assert 'school_id' not in table.c
        assert str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for index in table.indexes: assert str(CreateIndex(index).compile(dialect=postgresql.dialect()))

def test_mismatch_rejected_before_creating_tables():
    engine=create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE ncert_nodes (id TEXT PRIMARY KEY)'))
        with pytest.raises(RuntimeError,match='mismatch'): migration().upgrade(conn)
        assert 'ncert_sources' not in inspect(conn).get_table_names()
    engine.dispose()

def test_restrict_delete(connection):
    connection.execute(text("INSERT INTO ncert_batches VALUES ('hash','test','2026-11-09',NULL,'STAGED','{}','batch')"))
    connection.execute(text("INSERT INTO ncert_releases (id,release_key,edition,status,created_at,batch_id) VALUES ('release','test','test','DRAFT','2026-11-09','batch')"))
    with pytest.raises(IntegrityError),connection.begin_nested(): connection.execute(text("DELETE FROM ncert_batches WHERE id='batch'"))
    assert connection.scalar(text('SELECT count(*) FROM ncert_releases'))==1
