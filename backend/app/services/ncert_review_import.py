"""Validated, structure-only staging of the NCERT review package (LumenEIOS_NCERT_Review_Batch_01).

What this does
  * audit()  – read-only inspection: coverage, provenance, hierarchy and integrity checks. Never writes.
  * stage()  – writes ONLY validated structure (chapter, numbered section, numbered subheading headings with PDF-page
               locators) into the existing school-independent catalogue as a DRAFT release, batch VALIDATED, every row
               AWAITING_REVIEW and PARTIAL. It never publishes.

What this deliberately does NOT do (source policy: NCERT_SOURCE_POLICY.md, textbook text storage is not authorised)
  * Import page text, lines, blocks, citation quotes, or resource-marker content.
  * Import the 453 unnumbered typographic heading candidates (quarantined for structure review).
  * Import inferred learning outcomes, concept relationships, prerequisites or Core/Non-Core proposals: they reference
    concept occurrences rather than catalogue nodes, are analyst inferences, and remain PENDING EXPERT REVIEW.
  * Invent any title, edition, year, URL, page number or outcome. Bibliographic fields come from the source register.

The package is never treated as a complete curriculum: audit()['complete_curriculum'] is always False here.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid5

from sqlalchemy import select, update

from backend.app.models.ncert_catalogue import (
    CatalogueBatch, CatalogueEvidence, CatalogueIdentity, CatalogueNode, CatalogueNodeEvidence, CatalogueRelease,
    CatalogueSource, CatalogueText, NAMESPACE, node_id, release_id,
)

IMPORTER_VERSION = 'ncert-review-structure-1'
RELEASE_KEY = 'ncert-review-batch-01-structure'
IMPORTABLE_KINDS = {'chapter': 'CHAPTER', 'section': 'TOPIC', 'subtopic': 'SUBTOPIC'}
EXPECTED_PARENT = {'chapter': None, 'section': 'chapter', 'subtopic': 'section'}
SUBJECTS = ('Mathematics', 'Science')
NEEDED = ('textbooks', 'editions', 'sources', 'curriculum_nodes', 'learning_outcomes', 'classification_proposals',
          'content_items', 'concept_relationships')
PAGE_RE = re.compile(r'_p(\d{4})$')


class PackageError(ValueError):
    pass


def _read_csv(data: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))


def read_package(path: str | Path) -> dict:
    """Read the needed CSV tables from the review zip (or an extracted directory). Page-text tables are not read."""
    path = Path(path)
    tables: dict[str, list[dict]] = {}
    sha = None
    if path.is_file():
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        with zipfile.ZipFile(path) as z:
            names = {n.rsplit('/', 1)[-1]: n for n in z.namelist() if '/csv/' in n and n.endswith('.csv')}
            for t in NEEDED:
                if t + '.csv' not in names:
                    raise PackageError(f'package is missing csv/{t}.csv')
                tables[t] = _read_csv(z.read(names[t + '.csv']))
    elif path.is_dir():
        base = path / 'csv' if (path / 'csv').is_dir() else path
        for t in NEEDED:
            f = base / (t + '.csv')
            if not f.exists():
                raise PackageError(f'package is missing {f.name}')
            tables[t] = _read_csv(f.read_bytes())
    else:
        raise PackageError(f'package not found: {path}')
    return {'sha256': sha, 'tables': tables}


def read_register(path: str | Path) -> dict[str, dict]:
    with open(path, encoding='utf-8-sig', newline='') as fh:
        return {r['source_id']: r for r in csv.DictReader(fh)}


def _book_code(book_id: str) -> str:
    return 'TB-' + book_id.removeprefix('book_')


def _page_no(page_id: str) -> int | None:
    m = PAGE_RE.search(page_id or '')
    return int(m.group(1)) if m else None


def audit(package: dict, register: dict[str, dict] | None = None) -> dict:
    """Read-only coverage / provenance / integrity report. Contains counts and identifiers, no textbook content."""
    t = package['tables']
    books = {b['id']: b for b in t['textbooks']}
    sources = {s['id']: s for s in t['sources']}
    nodes = t['curriculum_nodes']
    by_id = {n['id']: n for n in nodes}
    problems: list[str] = []
    ids = Counter(n['id'] for n in nodes)
    problems += [f'duplicate node id {i}' for i, c in ids.items() if c > 1]

    per_book: dict[str, Counter] = defaultdict(Counter)
    importable, quarantined = [], []
    for n in nodes:
        book = n['textbook_id']
        if book not in books:
            problems.append(f"node {n['id']}: unknown textbook {book}")
            continue
        per_book[book][n['kind']] += 1
        kind = n['kind']
        reason = None
        if kind not in IMPORTABLE_KINDS:
            reason = 'UNNUMBERED_HEADING_CANDIDATE' if kind == 'topic' else 'UNSUPPORTED_KIND'
        else:
            parent = by_id.get(n['parent_id']) if n['parent_id'] else None
            want = EXPECTED_PARENT[kind]
            if (want is None) != (parent is None) or (parent and parent['kind'] != want):
                reason = 'INVALID_PARENT'
            elif not n['title'].strip():
                reason = 'EMPTY_TITLE'
            else:
                pno = _page_no(n['source_page_id'])
                src_id = PAGE_RE.sub('', n['source_page_id'] or '')
                src = sources.get(src_id)
                if pno is None or src is None:
                    reason = 'MISSING_PAGE_PROVENANCE'
                elif not (1 <= pno <= int(src['pdf_page_count'] or 0)):
                    reason = 'PAGE_OUT_OF_RANGE'
                elif src['textbook_id'] != book:
                    reason = 'SOURCE_BOOK_MISMATCH'
        (quarantined if reason else importable).append((n, reason))
    for n, reason in quarantined:
        if reason not in ('UNNUMBERED_HEADING_CANDIDATE',):
            problems.append(f"node {n['id']}: {reason}")

    # an importable node whose parent was quarantined cannot be staged
    bad = {n['id'] for n, _ in quarantined}
    stageable = [n for n, _ in importable if not (n['parent_id'] and n['parent_id'] in bad)]
    orphaned = len(importable) - len(stageable)

    editions = {e['textbook_id'] for e in t['editions']}
    textbooks = []
    for bid, b in books.items():
        code = _book_code(bid)
        reg = register.get(code) if register else None
        c = per_book[bid]
        textbooks.append({
            'textbook_id': bid, 'class': b['class'], 'subject': b['subject'], 'title': b['title'], 'part': b['part'],
            'edition_recorded': bid in editions, 'register_source_id': code if reg else None,
            'register_official_url': bool(reg and reg['official_url']),
            'rights_status': reg['rights_status'] if reg else 'NOT FOUND IN SOURCE',
            'chapters': c['chapter'], 'numbered_sections': c['section'], 'numbered_subheadings': c['subtopic'],
            'unnumbered_heading_candidates': c['topic'],
            'chapter_pdfs_with_page_counts': sum(1 for s in t['sources'] if s['textbook_id'] == bid and s['role'] == 'chapter'),
            'coverage_state': 'PARTIAL_STRUCTURE_ONLY' if c['chapter'] else 'NO_STRUCTURE',
        })
        if not reg:
            problems.append(f'{bid}: no matching English source-register row {code}; cannot be staged with provenance')

    outcomes = t['learning_outcomes']
    return {
        'package_sha256': package['sha256'],
        'complete_curriculum': False,
        'production_ready': False,
        'completeness_note': 'Structure extraction only. Semantic extraction, explicit-outcome audit, visual review and '
                             'expert verification are incomplete; the package itself declares INCOMPLETE.',
        'textbooks': textbooks,
        'totals': {
            'textbooks': len(books), 'nodes_read': len(nodes), 'importable_structure_nodes': len(stageable),
            'quarantined_unnumbered_candidates': sum(1 for _, r in quarantined if r == 'UNNUMBERED_HEADING_CANDIDATE'),
            'quarantined_invalid': sum(1 for _, r in quarantined if r != 'UNNUMBERED_HEADING_CANDIDATE'),
            'orphaned_by_quarantined_parent': orphaned,
            'chapters': sum(1 for n in stageable if n['kind'] == 'chapter'),
        },
        'not_imported': {
            'learning_outcomes': {'count': len(outcomes), 'origins': dict(Counter(o['origin'] for o in outcomes)),
                                  'reason': 'Analyst inferences, not official wording; reference concept occurrences, not catalogue nodes.'},
            'classification_proposals': {'count': len(t['classification_proposals']),
                                         'review_status': dict(Counter(p['review_status'] for p in t['classification_proposals'])),
                                         'reason': 'PENDING EXPERT REVIEW; no Core/Non-Core decision exists and none is applied.'},
            'concept_relationships': {'count': len(t['concept_relationships']),
                                      'review_status': dict(Counter(r['review_status'] for r in t['concept_relationships'])),
                                      'reason': 'Selected, unreviewed; reference occurrences rather than nodes.'},
            'content_items': {'count': len(t['content_items']),
                              'reason': 'Resource start-markers only; the catalogue has no content-item table. Activities, '
                                        'exercises and diagrams are never independent period requirements.'},
        },
        'problems': problems,
        'valid': not problems,
        '_stageable_ids': [n['id'] for n in stageable],
    }


def public_report(report: dict) -> dict:
    return {k: v for k, v in report.items() if not k.startswith('_')}


def _uuid(key: str) -> str:
    return str(uuid5(NAMESPACE, key))


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _when(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _access(value: str) -> str:
    return 'FULL_REVIEW' if value == 'FULL_REVIEW' else 'DISCOVERY_ONLY'


def stage(connection, package: dict, register: dict[str, dict], release_key: str = RELEASE_KEY) -> dict:
    """Write validated structure as a DRAFT release inside the caller's transaction. Idempotent; never publishes."""
    report = audit(package, register)
    if not report['valid']:
        raise PackageError('package failed validation: ' + '; '.join(report['problems'][:5]))
    if not package['sha256']:
        raise PackageError('staging requires the original zip so the batch manifest can be hashed')
    existing = connection.execute(select(CatalogueBatch.id).where(CatalogueBatch.manifest_sha256 == package['sha256'])).first()
    if existing:
        return {'status': 'ALREADY_STAGED', 'batch_id': existing[0], **public_report(report)}

    t = package['tables']
    now = datetime.now(timezone.utc)
    batch_id = _uuid('batch:' + package['sha256'])
    connection.execute(CatalogueBatch.__table__.insert(), [dict(
        id=batch_id, manifest_sha256=package['sha256'], importer_version=IMPORTER_VERSION, started_at=now,
        finished_at=None, status='STAGED', report=public_report(report))])
    rel_id = release_id(release_key)
    if not connection.execute(select(CatalogueRelease.id).where(CatalogueRelease.id == rel_id)).first():
        connection.execute(CatalogueRelease.__table__.insert(), [dict(
            id=rel_id, release_key=release_key, edition='NCERT review batch 01 (structure only, unverified)',
            academic_year=None, status='DRAFT', created_at=now, published_at=None, batch_id=batch_id)])

    books = {b['id']: b for b in t['textbooks']}
    sources = {s['id']: s for s in t['sources']}
    by_id = {n['id']: n for n in t['curriculum_nodes']}
    stage_ids = set(report['_stageable_ids'])

    # ---- sources (bibliographic metadata from the register; rights stay PERMISSION_REQUIRED) ----
    src_rows, src_id_of = [], {}
    for bid, b in books.items():
        reg = register[_book_code(bid)]
        sid = _uuid('source:' + reg['official_url'] + '|' + reg['language'] + '|' + reg['edition'])
        src_id_of[bid] = sid
        found = connection.execute(select(CatalogueSource.id).where(CatalogueSource.official_url == reg['official_url'],
                                   CatalogueSource.language == reg['language'], CatalogueSource.edition == reg['edition'])).first()
        if found:
            src_id_of[bid] = found[0]
            continue
        src_rows.append(dict(
            id=sid, publisher=reg['publisher'], title=reg['title'], document_type='TEXTBOOK', grade_scope=reg['grade'],
            subject_scope=reg['subject'], edition=reg['edition'], publication_year=_int(reg['publication_year']),
            language=reg['language'], official_url=reg['official_url'], retrieved_at=_when(reg['retrieval_date']),
            rights_status=reg['rights_status'], rights_decision=None, access_status=_access(reg['access_status'])))
    if src_rows:
        connection.execute(CatalogueSource.__table__.insert(), src_rows)

    # ---- identities + nodes, parents first ----
    ident_rows, node_rows, text_rows, ev_rows, link_rows = [], [], [], [], []
    seen_ident = {r[0] for r in connection.execute(select(CatalogueIdentity.authority_key))}
    ev_seen: dict[tuple, str] = {}

    def identity(key: str, kind: str) -> str:
        iid = _uuid(key)
        if key not in seen_ident:
            seen_ident.add(key)
            ident_rows.append(dict(id=iid, authority_key=key, kind=kind))
        return iid

    def evidence(book_id: str, locator: str, claim: str) -> str:
        k = (src_id_of[book_id], locator, claim)
        if k not in ev_seen:
            ev_seen[k] = _uuid('evidence:' + '|'.join(k))
            ev_rows.append(dict(id=ev_seen[k], source_id=k[0], locator=locator, supported_claim=claim, batch_id=batch_id))
        return ev_seen[k]

    def add_node(identity_uuid, parent, kind, grade, seq, title, ev_id):
        nid = node_id(release_key, identity_uuid)
        node_rows.append(dict(id=nid, release_id=rel_id, identity_id=identity_uuid, parent_id=parent, kind=kind,
                              grade_number=grade, sequence=seq, verification='AWAITING_REVIEW', completeness='PARTIAL',
                              batch_id=batch_id))
        text_rows.append(dict(id=_uuid('text:' + nid + ':en'), node_id=nid, language='en', title=title, outcome_text=None,
                              origin='OFFICIAL_ORIGINAL', source_language='en', evidence_id=ev_id,
                              verification='AWAITING_REVIEW', method=None, reviewer=None, reviewed_at=None))
        link_rows.append(dict(node_id=nid, evidence_id=ev_id))
        return nid

    ordered_books = sorted(books.values(), key=lambda b: (int(b['class']), b['subject'], b['part']))
    grade_node, subject_node = {}, {}
    seq = 0
    for b in ordered_books:
        g, s = int(b['class']), b['subject']
        front = f'front matter (inspected cover and colophon pages), {_book_code(b["id"])}'
        if g not in grade_node:
            ev = evidence(b['id'], front, f'Textbook is designated for Grade {g}')
            grade_node[g] = add_node(identity(f'ncert:grade:{g}', 'GRADE'), None, 'GRADE', g, g, f'Grade {g}', ev)
        if (g, s) not in subject_node:
            ev = evidence(b['id'], front, f'Textbook is designated for Grade {g} {s}')
            subject_node[(g, s)] = add_node(identity(f'ncert:grade:{g}:subject:{s.lower()}', 'SUBJECT'), grade_node[g],
                                            'SUBJECT', None, 0 if s == 'Mathematics' else 1, s, ev)

    def sort_key(n):
        b = books[n['textbook_id']]
        return (int(b['class']), b['subject'], b['part'], _int(n['order_in_book']) or 0)

    stageable = sorted((by_id[i] for i in stage_ids), key=sort_key)
    node_uuid: dict[str, str] = {}
    child_seq: Counter = Counter()
    for kind in ('chapter', 'section', 'subtopic'):          # parents before children (FK order)
        for n in (x for x in stageable if x['kind'] == kind):
            b = books[n['textbook_id']]
            g, s = int(b['class']), b['subject']
            parent = subject_node[(g, s)] if kind == 'chapter' else node_uuid[n['parent_id']]
            src = sources[PAGE_RE.sub('', n['source_page_id'])]
            locator = f"{src['filename']}, PDF p. {_page_no(n['source_page_id'])}"
            label = {'chapter': 'Chapter heading', 'section': 'Numbered section heading', 'subtopic': 'Numbered subheading'}[kind]
            ev = evidence(n['textbook_id'], locator, f'{label} appears in {b["title"]} {b["part"] if b["part"] != "NOT FOUND IN SOURCE" else ""}'.strip())
            child_seq[parent] += 1
            title = n['title'] if kind != 'chapter' else (f"{n['number']} {n['title']}".strip())
            ident = identity('ncert-review:' + n['id'], IMPORTABLE_KINDS[kind])
            node_uuid[n['id']] = add_node(ident, parent, IMPORTABLE_KINDS[kind], None, child_seq[parent] - 1, title, ev)

    for table, rows in ((CatalogueIdentity, ident_rows), (CatalogueNode, node_rows), (CatalogueEvidence, ev_rows),
                        (CatalogueText, text_rows), (CatalogueNodeEvidence, link_rows)):
        if rows:
            connection.execute(table.__table__.insert(), rows)
    connection.execute(update(CatalogueBatch).where(CatalogueBatch.id == batch_id)
                       .values(status='VALIDATED', finished_at=datetime.now(timezone.utc)))
    return {'status': 'STAGED_DRAFT', 'batch_id': batch_id, 'release_key': release_key,
            'nodes_written': len(node_rows), 'evidence_written': len(ev_rows), 'sources_written': len(src_rows),
            **public_report(report)}


def to_planning_import(package: dict, register: dict[str, dict] | None = None, label: str = 'NCERT review batch 01 structure') -> dict:
    """Validated structure as a JSON document for the existing planning syllabus import (frontend validateImport).

    Only chapter / numbered-section / numbered-subheading headings with PDF-page locators are emitted: no page text, no
    outcomes, no relationships, no Core/Non-Core data. Kinds map to CHAPTER / TOPIC / SUBTOPIC; resources are not emitted.
    """
    report = audit(package, register)
    if not report['valid']:
        raise PackageError('package failed validation: ' + '; '.join(report['problems'][:5]))
    t = package['tables']
    books = {b['id']: b for b in t['textbooks']}
    editions = {e['textbook_id']: e for e in t['editions']}
    sources = {s['id']: s for s in t['sources']}
    by_id = {n['id']: n for n in t['curriculum_nodes']}
    kind_map = {'chapter': 'CHAPTER', 'section': 'TOPIC', 'subtopic': 'SUBTOPIC'}
    ordered = sorted(books.values(), key=lambda b: (int(b['class']), b['subject'], b['part']))
    textbooks = []
    for b in ordered:
        ed = editions.get(b['id'], {})
        part = '' if b['part'] == 'NOT FOUND IN SOURCE' else b['part']
        textbooks.append({
            'id': 'ncert-review-' + b['id'], 'grade': int(b['class']), 'subject': b['subject'], 'language': 'en',
            'title': b['title'] + (f', Part {part}' if part else ''), 'part': part,
            'edition': ed.get('edition_label') or 'NOT FOUND IN SOURCE',
            'publicationYear': ed.get('publication_year') or '',
            'code': _book_code(b['id']),
        })
    # order_in_book is a separate counter per node kind in some books, so it is NOT document order. Rebuild true document
    # order per textbook from chapter number, then PDF page, block and line (the layout position encoded in each node id).
    def chapter_no(n):
        cur = n
        while cur['kind'] != 'chapter':
            cur = by_id[cur['parent_id']]
        return _int(cur['number']) or 0

    def position(n):
        m = re.search(r'_p(\d+)_b(\d+)_l(\d+)$', n['id'])
        page = _page_no(n['source_page_id']) or 0
        return (0, 0, 0) if n['kind'] == 'chapter' else (page, int(m.group(2)) if m else 0, int(m.group(3)) if m else 0)

    doc_order = {}
    for book_id in books:
        members = [by_id[i] for i in report['_stageable_ids'] if by_id[i]['textbook_id'] == book_id]
        members.sort(key=lambda n: (chapter_no(n), n['kind'] != 'chapter', position(n), _int(n['order_in_book']) or 0))
        for rank, n in enumerate(members, start=1):
            doc_order[n['id']] = rank
    nodes = []
    for node_id in report['_stageable_ids']:
        n = by_id[node_id]
        src = sources[PAGE_RE.sub('', n['source_page_id'])]
        title = n['title'].strip()
        number = (n['number'] or '').strip()
        if number and title.startswith(number):
            title = title[len(number):].strip()
        nodes.append({
            'id': 'ncert-review-' + n['id'], 'textbookId': 'ncert-review-' + n['textbook_id'], 'kind': kind_map[n['kind']],
            'parentId': ('ncert-review-' + n['parent_id']) if n['parent_id'] else None, 'number': number, 'title': title,
            'sequence': doc_order[n['id']], 'sourceLocator': f"{src['filename']}, PDF p. {_page_no(n['source_page_id'])}",
        })
    nodes.sort(key=lambda x: (next(i for i, tb in enumerate(textbooks) if tb['id'] == x['textbookId']), x['sequence']))
    return {'label': label, 'description': 'Heading structure only, from the NCERT review batch. Incomplete; not a full syllabus.',
            'textbooks': textbooks, 'nodes': nodes}
