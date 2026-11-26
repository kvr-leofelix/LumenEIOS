"""Structure-only staging of the review package. Synthetic data only; no NCERT content."""
import csv
import importlib.util
import io
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text

from backend.app.services import ncert_review_import as imp

SRC = 'src_aaaaaaaaaaaaaaaaaaaa'


def rows(header, data):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(data)
    return out.getvalue()


def build_zip(path, nodes=None, pages=10):
    nodes = nodes if nodes is not None else [
        ['ch1', 'chapter', '', 'book_xxgp1', 'ed1', '1', 'Synthetic Chapter', SRC + '_p0001', '', '1', 'TOC_EXTRACTED', 'TOC CHECKED'],
        ['s1', 'section', 'ch1', 'book_xxgp1', 'ed1', '1.1', '1.1 Synthetic Section', SRC + '_p0002', '', '2', 'EXTRACTED_HEADING', 'PENDING'],
        ['sub1', 'subtopic', 's1', 'book_xxgp1', 'ed1', '1.1.1', '1.1.1 Synthetic Sub', SRC + '_p0003', '', '3', 'EXTRACTED_HEADING', 'PENDING'],
        ['cand', 'topic', 's1', 'book_xxgp1', 'ed1', '', 'Unnumbered candidate', SRC + '_p0003', '', '4', 'TYPOGRAPHIC_HEADING_CANDIDATE', 'PENDING'],
    ]
    tables = {
        'textbooks': rows(['id', 'class', 'subject', 'title', 'subtitle', 'part', 'publisher'],
                          [['book_xxgp1', '6', 'Mathematics', 'Synthetic Book', 's', 'NOT FOUND IN SOURCE', 'NCERT']]),
        'editions': rows(['id', 'textbook_id'], [['ed1', 'book_xxgp1']]),
        'sources': rows(['id', 'textbook_id', 'filename', 'archive_path', 'sha256', 'pdf_page_count', 'role', 'duplicate_of'],
                        [[SRC, 'book_xxgp1', 'xxgp101.pdf', 'a/b', 'f' * 64, str(pages), 'chapter', '']]),
        'curriculum_nodes': rows(['id', 'kind', 'parent_id', 'textbook_id', 'edition_id', 'number', 'title', 'source_page_id',
                                  'source_line_id', 'order_in_book', 'extraction_status', 'review_status'], nodes),
        'learning_outcomes': rows(['id', 'origin'], [['lo1', 'INFERRED']]),
        'classification_proposals': rows(['id', 'review_status'], [['p1', 'PENDING EXPERT REVIEW']]),
        'content_items': rows(['id'], [['c1'], ['c2']]),
        'concept_relationships': rows(['id', 'review_status'], [['r1', 'PENDING EXPERT REVIEW']]),
    }
    with zipfile.ZipFile(path, 'w') as z:
        for k, v in tables.items():
            z.writestr(f'Pkg/csv/{k}.csv', v)
    return path


REGISTER = {'TB-xxgp1': dict(source_id='TB-xxgp1', publisher='NCERT', title='Synthetic Book', grade='6', subject='Mathematics',
                             edition='First Edition 2024', language='en', official_url='https://example.test/xxgp1ps.pdf',
                             retrieval_date='2026-11-09', rights_status='PERMISSION_REQUIRED', publication_year='2024',
                             access_status='DIRECT_FRONT_MATTER_VERIFIED')}


@pytest.fixture
def conn():
    engine = create_engine('sqlite:///:memory:')

    @event.listens_for(engine, 'connect')
    def fk(dbapi, _):
        dbapi.execute('PRAGMA foreign_keys=ON')

    spec = importlib.util.spec_from_file_location('m001', Path(__file__).parents[1] / 'migrations/001_ncert_catalogue.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with engine.begin() as c:
        mod.upgrade(c)
        yield c
    engine.dispose()


def test_audit_never_claims_completeness_and_quarantines_candidates(tmp_path):
    pkg = imp.read_package(build_zip(tmp_path / 'p.zip'))
    r = imp.audit(pkg, REGISTER)
    assert r['complete_curriculum'] is False and r['production_ready'] is False
    assert r['valid'] and r['totals']['importable_structure_nodes'] == 3
    assert r['totals']['quarantined_unnumbered_candidates'] == 1
    assert r['not_imported']['learning_outcomes']['origins'] == {'INFERRED': 1}
    assert r['not_imported']['classification_proposals']['review_status'] == {'PENDING EXPERT REVIEW': 1}


def test_missing_register_row_blocks_staging(tmp_path, conn):
    pkg = imp.read_package(build_zip(tmp_path / 'p.zip'))
    with pytest.raises(imp.PackageError):
        imp.stage(conn, pkg, {})
    assert conn.scalar(text('SELECT count(*) FROM ncert_nodes')) == 0


def test_page_out_of_range_and_bad_parent_are_invalid(tmp_path):
    nodes = [
        ['ch1', 'chapter', '', 'book_xxgp1', 'ed1', '1', 'C', SRC + '_p0001', '', '1', 'TOC_EXTRACTED', 'x'],
        ['s1', 'section', 'ch1', 'book_xxgp1', 'ed1', '1.1', '1.1 S', SRC + '_p0099', '', '2', 'EXTRACTED_HEADING', 'x'],
        ['sub1', 'subtopic', 'ch1', 'book_xxgp1', 'ed1', '1.1.1', '1.1.1 T', SRC + '_p0002', '', '3', 'EXTRACTED_HEADING', 'x'],
    ]
    r = imp.audit(imp.read_package(build_zip(tmp_path / 'p.zip', nodes)), REGISTER)
    assert not r['valid']
    joined = ' '.join(r['problems'])
    assert 'PAGE_OUT_OF_RANGE' in joined and 'INVALID_PARENT' in joined


def test_stage_writes_draft_awaiting_review_structure_only(tmp_path, conn):
    pkg = imp.read_package(build_zip(tmp_path / 'p.zip'))
    out = imp.stage(conn, pkg, REGISTER)
    assert out['status'] == 'STAGED_DRAFT'
    assert conn.scalar(text('SELECT status FROM ncert_releases')) == 'DRAFT'
    assert conn.scalar(text('SELECT status FROM ncert_batches')) == 'VALIDATED'
    kinds = dict(conn.execute(text('SELECT kind, count(*) FROM ncert_nodes GROUP BY kind')).all())
    assert kinds == {'GRADE': 1, 'SUBJECT': 1, 'CHAPTER': 1, 'TOPIC': 1, 'SUBTOPIC': 1}
    assert conn.scalar(text("SELECT count(*) FROM ncert_nodes WHERE verification<>'AWAITING_REVIEW' OR completeness<>'PARTIAL'")) == 0
    assert conn.scalar(text("SELECT rights_status FROM ncert_sources")) == 'PERMISSION_REQUIRED'
    # no outcome nodes, no unnumbered candidate, every text is cited
    assert conn.scalar(text("SELECT count(*) FROM ncert_texts WHERE title LIKE '%candidate%' OR outcome_text IS NOT NULL")) == 0
    assert conn.scalar(text('SELECT count(*) FROM ncert_texts WHERE evidence_id IS NULL')) == 0
    assert conn.scalar(text("SELECT count(*) FROM ncert_releases WHERE published_at IS NOT NULL")) == 0
    loc = conn.scalar(text("SELECT locator FROM ncert_evidence WHERE supported_claim LIKE 'Chapter heading%'"))
    assert loc == 'xxgp101.pdf, PDF p. 1'


def test_stage_is_idempotent_and_preserves_other_data(tmp_path, conn):
    conn.execute(text('CREATE TABLE teammate_plan (id INTEGER PRIMARY KEY, note TEXT)'))
    conn.execute(text("INSERT INTO teammate_plan VALUES (1,'keep')"))
    pkg = imp.read_package(build_zip(tmp_path / 'p.zip'))
    imp.stage(conn, pkg, REGISTER)
    n = conn.scalar(text('SELECT count(*) FROM ncert_nodes'))
    again = imp.stage(conn, pkg, REGISTER)
    assert again['status'] == 'ALREADY_STAGED'
    assert conn.scalar(text('SELECT count(*) FROM ncert_nodes')) == n
    assert conn.scalar(text('SELECT note FROM teammate_plan')) == 'keep'


def test_planning_import_uses_true_document_order_and_only_teachable_structure(tmp_path):
    # order_in_book is a separate counter per kind here (subtopics 1..2 before sections 3..4), as in the real Science books
    nodes = [
        ['ch1', 'chapter', '', 'book_xxgp1', 'ed1', '1', 'Chapter One', SRC + '_p0001', '', '1', 'TOC_EXTRACTED', 'x'],
        ['ch2', 'chapter', '', 'book_xxgp1', 'ed1', '2', 'Chapter Two', SRC + '_p0005', '', '2', 'TOC_EXTRACTED', 'x'],
        ['section_a_p0002_b001_l000', 'section', 'ch1', 'book_xxgp1', 'ed1', '1.1', '1.1 First', SRC + '_p0002', '', '3', 'EXTRACTED_HEADING', 'x'],
        ['subtopic_a_p0003_b001_l000', 'subtopic', 'section_a_p0002_b001_l000', 'book_xxgp1', 'ed1', '1.1.1', '1.1.1 Sub of first', SRC + '_p0003', '', '1', 'EXTRACTED_HEADING', 'x'],
        ['section_b_p0006_b001_l000', 'section', 'ch2', 'book_xxgp1', 'ed1', '2.1', '2.1 Second', SRC + '_p0006', '', '4', 'EXTRACTED_HEADING', 'x'],
        ['subtopic_b_p0007_b001_l000', 'subtopic', 'section_b_p0006_b001_l000', 'book_xxgp1', 'ed1', '2.1.1', '2.1.1 Sub of second', SRC + '_p0007', '', '2', 'EXTRACTED_HEADING', 'x'],
        ['cand', 'topic', 'ch1', 'book_xxgp1', 'ed1', '', 'Unnumbered candidate', SRC + '_p0004', '', '5', 'TYPOGRAPHIC_HEADING_CANDIDATE', 'x'],
    ]
    pkg = imp.read_package(build_zip(tmp_path / 'p.zip', nodes))
    doc = imp.to_planning_import(pkg, REGISTER)
    ordered = [n['title'] for n in sorted(doc['nodes'], key=lambda n: n['sequence'])]
    assert ordered == ['Chapter One', 'First', 'Sub of first', 'Chapter Two', 'Second', 'Sub of second']
    assert {n['kind'] for n in doc['nodes']} == {'CHAPTER', 'TOPIC', 'SUBTOPIC'}
    assert all(n['sourceLocator'].startswith('xxgp101.pdf, PDF p. ') for n in doc['nodes'])
    assert 'Unnumbered candidate' not in {n['title'] for n in doc['nodes']}
    # numbers are not duplicated inside titles; no text, outcomes or classifications travel with the structure
    assert doc['nodes'][1]['number'] == '1.1' and doc['nodes'][1]['title'] == 'First'
    assert all(set(n) == {'id', 'textbookId', 'kind', 'parentId', 'number', 'title', 'sequence', 'sourceLocator'} for n in doc['nodes'])
