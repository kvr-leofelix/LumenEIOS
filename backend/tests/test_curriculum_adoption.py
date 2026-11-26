"""Adopting the existing curriculum dataset: leaf-unit rule, stable ids, additive/idempotent writes, protected databases, topic preference."""
import json
import sqlite3

import pytest

from backend.app.services import curriculum_adoption as ad

DATASET = {
    "id": "import-x", "kind": "SCHOOL_IMPORT", "label": "Batch", "description": "Heading structure only. Incomplete.",
    "textbooks": [{"id": "ncert-review-book_a1", "grade": 7, "subject": "Mathematics"}],
    "nodes": [
        {"id": "ncert-review-ch_a1_01", "textbookId": "ncert-review-book_a1", "grade": 7, "subject": "Mathematics", "kind": "CHAPTER", "parentId": None, "number": "1", "title": "Ch One", "sequence": 1},
        {"id": "ncert-review-section_1", "textbookId": "ncert-review-book_a1", "grade": 7, "subject": "Mathematics", "kind": "TOPIC", "parentId": "ncert-review-ch_a1_01", "number": "1.1", "title": "Parent topic", "sequence": 2},
        {"id": "ncert-review-subtopic_1", "textbookId": "ncert-review-book_a1", "grade": 7, "subject": "Mathematics", "kind": "SUBTOPIC", "parentId": "ncert-review-section_1", "number": "1.1.1", "title": "Child", "sequence": 3},
        {"id": "ncert-review-section_2", "textbookId": "ncert-review-book_a1", "grade": 7, "subject": "Mathematics", "kind": "TOPIC", "parentId": "ncert-review-ch_a1_01", "number": "1.2", "title": "Leaf topic", "sequence": 4},
    ],
}
UUIDS = {n["id"]: f"uuid-{n['id']}" for n in DATASET["nodes"]}


def test_only_leaf_topics_and_subtopics_become_planning_units():
    assert [n["id"] for n in ad.eligible_units(DATASET["nodes"])] == ["ncert-review-subtopic_1", "ncert-review-section_2"]


def test_plan_topics_keep_dataset_ids_chapter_and_order():
    rows = ad.plan_topic_rows(DATASET, UUIDS)
    assert [r["topic_key"] for r in rows] == ["ncert-review-subtopic_1", "ncert-review-section_2"]
    assert [r["sort_order"] for r in rows] == [1, 2]
    assert rows[1]["section_label"] == "1.2 Leaf topic" and rows[1]["chapter_number"] == "1" and rows[1]["chapter_title"] == "Ch One"
    assert rows[0]["source_ref"] == "ncert-batch:uuid-ncert-review-subtopic_1"


def test_authority_key_mapping_round_trips():
    assert ad.authority_key("ncert-review-section_src_ab") == "ncert-review:section_src_ab"
    assert ad.authority_key_to_dataset("ncert-review:section_src_ab") == "ncert-review-section_src_ab"


def test_overlong_topic_id_is_refused():
    long = {**DATASET, "nodes": [DATASET["nodes"][0], {**DATASET["nodes"][3], "id": "x" * 65}]}
    with pytest.raises(ad.AdoptionError):
        ad.plan_topic_rows(long, {**UUIDS, "x" * 65: "u"})


@pytest.mark.parametrize("name", sorted(ad.PROTECTED))
def test_protected_databases_are_refused(name):
    with pytest.raises(ad.AdoptionError):
        ad.refuse_protected(f"somewhere/{name}")
    ad.refuse_protected("somewhere/lumeneios_teacherplan_demo.db")


def _work_db():
    c = sqlite3.connect(":memory:")
    c.executescript("""
      create table schools (id text primary key);
      insert into schools values ('s1'),('s2');
      create table plan_topics (topic_key text primary key, grade int, subject text, chapter_number text, chapter_title text, section_label text, sort_order int, source_ref text);
      create table planning_workspace_revisions (id text primary key, school_id text, revision int, action text, summary text, actor_id text, actor_name text, actor_role text, state text, created_at text);
      create table teacher_topic_configs (topic_key text); create table teacher_topic_coverage (topic_key text);
    """)
    return c


def test_inserts_are_additive_and_idempotent():
    c = _work_db()
    rows = ad.plan_topic_rows(DATASET, UUIDS)
    assert ad.insert_plan_topics(c, rows) == 2
    assert ad.insert_plan_topics(c, rows) == 0
    first = ad.add_workspace_dataset(c, DATASET)
    assert first == {"s1": "revision 1", "s2": "revision 1"}
    assert ad.add_workspace_dataset(c, DATASET) == {"s1": "already present", "s2": "already present"}
    assert c.execute("select count(*) from planning_workspace_revisions").fetchone()[0] == 2
    state = json.loads(c.execute("select state from planning_workspace_revisions where school_id='s1'").fetchone()[0])
    assert state["datasets"][0]["description"] == DATASET["description"] and state["datasets"][0]["kind"] == "SCHOOL_IMPORT"


def test_existing_workspace_state_is_carried_forward_not_replaced():
    c = _work_db()
    prior = {"schemaVersion": 2, "config": {"keep": 1}, "configHistory": [], "datasets": [], "classifications": {}, "relationships": [], "plans": [{"id": "p"}], "coverage": {}, "asOf": "2026-11-10", "audit": []}
    c.execute("insert into planning_workspace_revisions values ('r1','s1',4,'PLANNING_DATE','x','u','U','admin',?, 'now')", (json.dumps(prior),))
    ad.add_workspace_dataset(c, DATASET)
    rev, state = c.execute("select revision,state from planning_workspace_revisions where school_id='s1' order by revision desc limit 1").fetchone()
    state = json.loads(state)
    assert rev == 5 and state["plans"] == [{"id": "p"}] and state["asOf"] == "2026-11-10" and state["config"] == {"keep": 1}
    assert c.execute("select count(*) from planning_workspace_revisions where school_id='s1'").fetchone()[0] == 2  # old revision kept


def test_legacy_crosswalk_keys_are_only_proposed_on_exact_book_number_and_title_match():
    c = _work_db()
    c.executemany("insert into plan_topics values (?,?,?,?,?,?,?,?)", [
        ("XW-a101-S1.2", 7, "Mathematics", "1", "Ch One", "1.2 Leaf topic", 1, None),
        ("XW-a101-S1.1", 7, "Mathematics", "1", "Ch One", "1.1 Something else", 2, None),
    ])
    rep = {r["legacy_key"]: r for r in ad.legacy_mapping_report(c, DATASET)}
    assert rep["XW-a101-S1.2"]["proposed_topic_key"] == "ncert-review-section_2"
    assert rep["XW-a101-S1.1"]["proposed_topic_key"] is None and rep["XW-a101-S1.1"]["status"] == "no match"


@pytest.mark.asyncio(loop_scope="session")
async def test_adopted_topics_replace_crosswalk_rows_for_a_class_but_leave_other_classes_alone():
    from backend.app.db.session import AsyncSessionLocal
    from backend.app.models.teacher_planning import PlanTopic
    from backend.app.services.teacher_plan_service import topics_for

    async with AsyncSessionLocal() as db:
        db.add(PlanTopic(topic_key="XW-legacy-test", grade=91, subject="Mathematics", chapter_number="1", chapter_title="c", section_label="1.1 old", sort_order=1))
        db.add(PlanTopic(topic_key="XW-legacy-test-2", grade=92, subject="Mathematics", chapter_number="1", chapter_title="c", section_label="1.1 old", sort_order=1))
        db.add(PlanTopic(topic_key="ncert-review-test", grade=91, subject="Mathematics", chapter_number="1", chapter_title="c", section_label="1.2 new", sort_order=1, source_ref="ncert-batch:u"))
        await db.flush()
        assert [t.topic_key for t in await topics_for(db, 91, "Mathematics")] == ["ncert-review-test"]
        assert [t.topic_key for t in await topics_for(db, 92, "Mathematics")] == ["XW-legacy-test-2"]
        await db.rollback()
