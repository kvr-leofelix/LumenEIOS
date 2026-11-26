"""Adopt the existing NCERT review-batch curriculum (76 chapters / 353 topics / 102 subtopics) into a working database.

Additive and idempotent. Nothing is regenerated: catalogue rows are copied verbatim (same ids) from the source database, the
planning syllabus dataset is the original JSON document, and planning topics are derived from that document's own node ids.
Draft / incomplete / unverified metadata is carried over unchanged. Protected databases are refused.

Pure functions here take sqlite3 connections so they can be tested on temporary files.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

CATALOGUE_REF = "ncert-batch:"
SCHEDULABLE = ("TOPIC", "SUBTOPIC")
EXPECTED = {"CHAPTER": 76, "TOPIC": 353, "SUBTOPIC": 102}
PROTECTED = {"lumeneios.db", "lumeneios_acceptance.db", "lumeneios_planning_dev.db", "lumeneios_takeover_acceptance.db"}
SYSTEM_ACTOR = ("system-curriculum-adoption", "Curriculum adoption (system)", "admin")


class AdoptionError(RuntimeError):
    pass


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ro_connect(path: str | Path) -> sqlite3.Connection:
    p = Path(path).resolve().as_posix()
    return sqlite3.connect(f"file:{p}?mode=ro&immutable=1", uri=True)


def refuse_protected(path: str | Path) -> None:
    if Path(path).name in PROTECTED:
        raise AdoptionError(f"{Path(path).name} is a protected database and is never modified.")


def eligible_units(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mirror of the frontend rule (src/lib/planning/syllabus.ts eligibleUnits): leaf TOPIC/SUBTOPIC nodes."""
    parents = {n["parentId"] for n in nodes if n["kind"] in SCHEDULABLE and n.get("parentId")}
    return [n for n in nodes if n["kind"] in SCHEDULABLE and n["id"] not in parents]


def authority_key(dataset_node_id: str) -> str:
    return re.sub(r"^ncert-review-", "ncert-review:", dataset_node_id, count=1)


def verify_source(src: sqlite3.Connection, dataset: Dict[str, Any]) -> Dict[str, Any]:
    """The source database and the JSON dataset must describe the same hierarchy before anything is written."""
    counts = dict(src.execute("select kind,count(*) from ncert_nodes where kind in ('CHAPTER','TOPIC','SUBTOPIC') group by kind").fetchall())
    if counts != EXPECTED:
        raise AdoptionError(f"Source curriculum counts {counts} differ from the expected {EXPECTED}.")
    ds_counts: Dict[str, int] = {}
    for n in dataset["nodes"]:
        ds_counts[n["kind"]] = ds_counts.get(n["kind"], 0) + 1
    if ds_counts != EXPECTED:
        raise AdoptionError(f"Dataset counts {ds_counts} differ from the expected {EXPECTED}.")
    ident = {r[0]: (r[1], r[2]) for r in src.execute("select authority_key,id,kind from ncert_identities")}
    node_of_ident = {r[0]: (r[1], r[2]) for r in src.execute("select identity_id,id,parent_id from ncert_nodes")}
    ident_of_node = {r[0]: r[1] for r in src.execute("select id,identity_id from ncert_nodes")}
    ident_auth = {v[0]: k for k, v in ident.items()}
    problems: List[str] = []
    node_uuid: Dict[str, str] = {}
    for n in dataset["nodes"]:
        key = authority_key(n["id"])
        if key not in ident:
            problems.append(f"{n['id']}: no catalogue identity")
            continue
        iid, kind = ident[key]
        if kind != n["kind"]:
            problems.append(f"{n['id']}: kind {kind} != {n['kind']}")
        nid, parent_node = node_of_ident.get(iid, (None, None))
        if not nid:
            problems.append(f"{n['id']}: no catalogue node")
            continue
        node_uuid[n["id"]] = nid
        want_parent = n.get("parentId")
        got_parent = authority_key_to_dataset(ident_auth.get(ident_of_node.get(parent_node))) if parent_node else None
        if want_parent is None:
            # Chapters hang under the catalogue's SUBJECT node, which the planning dataset does not carry.
            parent_kind = ident.get(ident_auth.get(ident_of_node.get(parent_node)), (None, None))[1] if parent_node else None
            if parent_kind != "SUBJECT":
                problems.append(f"{n['id']}: top-level node has catalogue parent kind {parent_kind}")
        elif want_parent != got_parent:
            problems.append(f"{n['id']}: parent {got_parent} != {want_parent}")
    if problems:
        raise AdoptionError("Source database and dataset disagree: " + "; ".join(problems[:5]) + f" (+{max(0, len(problems) - 5)} more)")
    return {"counts": counts, "node_uuid": node_uuid}


def authority_key_to_dataset(key: str | None) -> str | None:
    return None if key is None else re.sub(r"^ncert-review:", "ncert-review-", key, count=1)


def attach_source(dst: sqlite3.Connection, src_path: str | Path) -> None:
    """ATTACH must happen outside a transaction: call this before BEGIN."""
    dst.execute("ATTACH DATABASE ? AS src", (f"file:{Path(src_path).resolve().as_posix()}?mode=ro&immutable=1",))


def copy_catalogue(dst: sqlite3.Connection) -> Dict[str, int]:
    """Copy every ncert_* table verbatim (same ids) from the attached read-only 'src'. Existing rows are never overwritten."""
    out: Dict[str, int] = {}
    if True:
        tables = [r[0] for r in dst.execute("select name from src.sqlite_master where type='table' and name like 'ncert\\_%' escape '\\'")]
        have = {r[0] for r in dst.execute("select name from main.sqlite_master where type='table'")}
        for t in tables:
            if t not in have:
                raise AdoptionError(f"Target database lacks table {t}; run the catalogue migrations on the working copy first.")
            cols = [r[1] for r in dst.execute(f'pragma main.table_info("{t}")')]
            scols = [r[1] for r in dst.execute(f'pragma src.table_info("{t}")')]
            if cols != scols:
                raise AdoptionError(f"{t}: column mismatch between source and target.")
            col_sql = ",".join(f'"{c}"' for c in cols)
            before = dst.execute(f'select count(*) from main."{t}"').fetchone()[0]
            dst.execute(f'insert or ignore into main."{t}" ({col_sql}) select {col_sql} from src."{t}"')
            after = dst.execute(f'select count(*) from main."{t}"').fetchone()[0]
            want = dst.execute(f'select count(*) from src."{t}"').fetchone()[0]
            if after < want:
                raise AdoptionError(f"{t}: target holds {after} rows, source {want}; conflicting rows exist, not overwritten.")
            out[t] = after - before
    return out


def plan_topic_rows(dataset: Dict[str, Any], node_uuid: Dict[str, str]) -> List[Dict[str, Any]]:
    nodes = dataset["nodes"]
    by_id = {n["id"]: n for n in nodes}
    book_index = {t["id"]: i for i, t in enumerate(dataset["textbooks"])}
    units = eligible_units(nodes)

    def chapter_of(n):
        cur = n
        while cur["kind"] != "CHAPTER":
            cur = by_id[cur["parentId"]]
        return cur

    out: List[Dict[str, Any]] = []
    groups: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}
    for u in units:
        groups.setdefault((u["grade"], u["subject"]), []).append(u)
    for (grade, subject), members in sorted(groups.items()):
        members.sort(key=lambda n: (book_index.get(n["textbookId"], 99), n["sequence"]))
        for order, n in enumerate(members, start=1):
            ch = chapter_of(n)
            if len(n["id"]) > 64:
                raise AdoptionError(f"Topic id longer than 64 characters: {n['id']}")
            label = f"{n['number']} {n['title']}".strip()
            out.append({"topic_key": n["id"], "grade": grade, "subject": subject, "chapter_number": str(ch.get("number") or ""),
                        "chapter_title": ch["title"], "section_label": label[:255], "sort_order": order,
                        "source_ref": CATALOGUE_REF + node_uuid[n["id"]]})
    return out


def insert_plan_topics(dst: sqlite3.Connection, rows: List[Dict[str, Any]]) -> int:
    n = 0
    for r in rows:
        cur = dst.execute(
            "insert or ignore into plan_topics (topic_key,grade,subject,chapter_number,chapter_title,section_label,sort_order,source_ref) "
            "values (:topic_key,:grade,:subject,:chapter_number,:chapter_title,:section_label,:sort_order,:source_ref)", r)
        n += cur.rowcount
    return n


def add_workspace_dataset(dst: sqlite3.Connection, dataset: Dict[str, Any]) -> Dict[str, str]:
    """Append (never rewrite) one workspace revision per school that does not yet hold this dataset. Existing state is carried forward."""
    result: Dict[str, str] = {}
    schools = [r[0] for r in dst.execute("select id from schools order by id")]
    for school in schools:
        row = dst.execute("select revision,state from planning_workspace_revisions where school_id=? order by revision desc limit 1", (school,)).fetchone()
        if row:
            rev, state = row[0], json.loads(row[1]) if isinstance(row[1], str) else row[1]
        else:
            rev, state = 0, {"schemaVersion": 2, "config": {}, "configHistory": [], "datasets": [], "classifications": {}, "relationships": [],
                             "plans": [], "coverage": {}, "asOf": None, "audit": []}
        if any(d.get("id") == dataset["id"] for d in state.get("datasets", [])):
            result[school] = "already present"
            continue
        state = {**state, "datasets": [*state.get("datasets", []), dataset]}
        aid, aname, arole = SYSTEM_ACTOR
        dst.execute(
            "insert into planning_workspace_revisions (id,school_id,revision,action,summary,actor_id,actor_name,actor_role,state,created_at) values (?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), school, rev + 1, "SYLLABUS_IMPORT",
             f"Adopted existing curriculum dataset '{dataset['label']}' (draft, structure only, unverified)", aid, aname, arole,
             json.dumps(state), datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")))
        result[school] = f"revision {rev + 1}"
    return result


def legacy_mapping_report(dst: sqlite3.Connection, dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Explicit, evidence-based mapping PROPOSAL for earlier crosswalk keys (XW-<book>-S<number>). Nothing is rewritten."""
    nodes = {n["id"]: n for n in dataset["nodes"]}
    books = {t["id"]: t for t in dataset["textbooks"]}
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    report = []
    for key, grade, subject, label in dst.execute("select topic_key,grade,subject,section_label from plan_topics where topic_key like 'XW-%'"):
        m = re.match(r"XW-([a-z]+\d)\d+-S([\d.]+)$", key)
        hits = []
        if m:
            book, number = m.group(1), m.group(2)
            for n in nodes.values():
                if n["kind"] in SCHEDULABLE and n["grade"] == grade and n["subject"] == subject and n["textbookId"].endswith("_" + book) \
                        and n["number"] == number and norm(label).endswith(norm(n["title"])):
                    hits.append(n["id"])
        refs = dst.execute("select (select count(*) from teacher_topic_configs where topic_key=?),(select count(*) from teacher_topic_coverage where topic_key=?)", (key, key)).fetchone()
        report.append({"legacy_key": key, "label": label, "proposed_topic_key": hits[0] if len(hits) == 1 else None,
                       "status": "exact match (number + title + book)" if len(hits) == 1 else ("ambiguous" if hits else "no match"),
                       "teacher_config_rows": refs[0], "teacher_coverage_rows": refs[1]})
    return report
