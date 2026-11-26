"""Persistent, isolated acceptance runner using the existing roster, ORM and migrations.

Run prepare, serve, exercise, then restart serve and run verify-restart.
--fixture-ai replaces ONLY model text output; it is not a live AI quality test.
Never accepts a database outside this clone's ignored .local-demo directory.
"""
import argparse
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time
import uuid

APP = Path(__file__).resolve().parents[2]
ROOT = APP / ".local-demo"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def originals():
    workspace = APP.parents[1]
    return {str(p): digest(p) for p in (
        APP / "lumeneios.db", workspace.parent / "arena-learnsphere/lumeneios.db",
        workspace.parent / "arena-github-upload/apps/lumeneios/lumeneios.db")}


def configure(run):
    manifest = json.loads((run / "run.json").read_text())
    os.environ.update(APP_ENV="test", DEBUG="false", DEMO_MODE="false",
        AUTO_SEED_CURRICULUM="false", DEV_LOGIN_BYPASS="false", DEMO_ROOT_PASSWORD="",
        DATABASE_URL="sqlite+aiosqlite:///" + (run / "acceptance.db").as_posix(),
        STORAGE_LOCAL_DIR=str(run / "uploads"), SECRET_KEY=manifest["secret"],
        BACKEND_CORS_ORIGINS='["http://127.0.0.1:18881"]')
    return manifest


def prepare(run):
    if run.exists():
        raise RuntimeError("New run directory required; existing data will never be reset.")
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"secret": secrets.token_hex(32),
        "originals": originals(), "purpose": "synthetic persistent acceptance"}), encoding="utf-8")
    configure(run)
    from sqlalchemy import create_engine
    from backend.app.db import base  # registers current models without opening the default DB
    from backend.app.db.session import Base
    engine = create_engine("sqlite:///" + (run / "acceptance.db").as_posix())
    with engine.begin() as connection:
        Base.metadata.create_all(connection, tables=[t for t in Base.metadata.sorted_tables
                                                    if not t.name.startswith("learning_")])
    engine.dispose()
    # Existing backup + rehearsal + guarded apply, never stamp over existing tables.
    subprocess.run([sys.executable, "-B", "-m", "backend.scripts.migrate_learnsphere",
        "--database", str(run / "acceptance.db"), "--backup-dir", str(run / "migration-backups"),
        "--apply"], cwd=APP, check=True)

    async def seed():
        from backend.app.db.session import init_db, AsyncSessionLocal, engine
        from backend.app.seed.seed_data import seed_database_if_empty, roster_users
        await init_db()
        async with AsyncSessionLocal() as session:
            await seed_database_if_empty(session)
        # Only credentials explicitly defined by the existing seed, never new passwords.
        (run / "seed-accounts.json").write_text(json.dumps(roster_users()), encoding="utf-8")
        await engine.dispose()
    asyncio.run(seed())
    audit(run)


def fixture_questions():
    # Reuse established question-content-based stage fixtures, never the demo script's
    # LU/CU/AU/CT -> stage lookup. Only this acceptance runner imports test fixtures.
    from backend.tests.test_panchapadi import questions_and_mapping
    questions, mapping = questions_and_mapping()
    for q, code in zip(questions, ("LU", "CU", "AU", "AU", "CT", "CT")):
        q["competency"] = code
    questions[1]["type"] = "descriptive"
    questions[1]["options"] = []
    questions.append({"id": "unknown-written", "position": 6, "text": "Explain the unavailable context.",
        "type": "descriptive", "options": [], "marks": 2, "competency": "CU", "bloom_level": "Understand"})
    mapping.append({"position": 6, "mappings": []})
    return questions, mapping


def install_fixture_ai():
    from backend.app.services.llm_service import qwen_question_studio
    questions, mapping = fixture_questions()
    by_position = {m["position"]: m for m in mapping}

    def generate(prompt, image=None, max_new_tokens=2048, output_schema=None, report_step=None):
        data = json.loads(prompt.rsplit("\n", 1)[-1])
        title = (output_schema or {}).get("title")
        if title == "CompetencyAnalysis":
            return json.dumps({"questions": [{"position": q["position"],
                "label": questions[q["position"]]["competency"] if q.get("marking_rubric") else None,
                "confidence": 0.95 if q.get("marking_rubric") else 0.0,
                "reason": "Synthetic acceptance fixture; educator confirmation remains separate."}
                for q in data["questions"]]})
        if title == "StageClassification":
            return json.dumps({"questions": [by_position[row["question"]["position"]] for row in data]})
        if title == "WrittenMark":
            unknown = not data["question"].get("marking_rubric")
            return json.dumps({"score": None if unknown else 1, "correct": None if unknown else False,
                "insufficient_evidence": unknown, "explanation": "Acceptance fixture, not live model inference.",
                "feedback": "Ask the teacher for context." if unknown else "Explain the relationship more fully.",
                "demonstrated_concepts": [], "partial_concepts": [], "missing_concepts": []})
        if title == "QuestionGuidance":
            return json.dumps({"expected_concept": "Explain the question's stated relationship." if data["question"].get("marking_rubric") else None,
                "misunderstanding": None, "explanation": "Acceptance fixture guidance for Q" + str(data["question"]["position"] + 1),
                "activity": "Explain your own reasoning with a new example.", "practice_question": "How can you justify your method?"})
        if title == "LearningDraft":
            kind = next(k for k in ("support", "teach_back", "mission") if "review " + k + " draft" in prompt)
            pos = (data.get("required_gap_positions") or [data["questions"][0]["position"]])[0]
            return json.dumps(dict(kind=kind, positions=[pos], stage="Bodh", title="Acceptance " + kind,
                explanation="A follow-up to the saved partial explanation.", learning_tip="Explain the relationship.",
                scenario="Discuss the calculation with a classmate.", instructions="Explain the relationship in your own words.",
                expected_submission="A written explanation.", objective="Justify a relationship.", rubric="Credit a clear reason."))
        if "covered" in (output_schema or {}).get("properties", {}):
            return json.dumps({"covered": [True], "misconceptions": [], "strengths": ["Acceptance fixture"],
                               "next_step": "Provide a second example."})
        raise RuntimeError("Unsupported acceptance fixture schema: " + str(title))
    qwen_question_studio._generate_text = generate


def audit(run):
    manifest = json.loads((run / "run.json").read_text())
    assert manifest["originals"] == originals(), "An original database changed"
    with sqlite3.connect((run / "acceptance.db").as_uri() + "?mode=ro", uri=True) as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        result = {"integrity": db.execute("PRAGMA integrity_check").fetchall(),
            "foreign_key_violations": db.execute("PRAGMA foreign_key_check").fetchall(),
            "revision": db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
            "counts": {t: db.execute('SELECT count(*) FROM "' + t + '"').fetchone()[0] for t in tables},
            "learning_schema": {t: {"columns": db.execute('PRAGMA table_info("' + t + '")').fetchall(),
                "foreign_keys": db.execute('PRAGMA foreign_key_list("' + t + '")').fetchall(),
                "indexes": db.execute('PRAGMA index_list("' + t + '")').fetchall()}
                for t in tables if t.startswith("learning_")}}
        assert result["integrity"] == [("ok",)]
        assert not result["foreign_key_violations"], result["foreign_key_violations"][:10]
        assert result["revision"] == "0005_learning_interventions"
        from backend.app.main import app  # register the entire current runtime metadata
        from backend.app.db.session import Base
        result["model_column_checks"] = []
        for table in Base.metadata.sorted_tables:
            if not table.name.startswith("learning_"):
                continue
            actual = {row[1]: row for row in db.execute('PRAGMA table_info("' + table.name + '")')}
            assert set(actual) == set(table.columns.keys()), table.name
            for col in table.columns:
                if not col.primary_key:
                    assert bool(actual[col.name][3]) == (not col.nullable), (table.name, col.name)
            result["model_column_checks"].append(table.name)
        duplicates = {}
        for table, keys in (("learning_assessment_results", "assessment_id,student_id"),
                            ("learning_assignments", "assigned_by,request_key,student_id"),
                            ("learning_attempts", "assignment_id,request_key"),
                            ("learning_evidence", "source,attempt_id,observation_key")):
            duplicates[table] = db.execute(f"SELECT {keys},count(*) FROM {table} GROUP BY {keys} HAVING count(*)>1").fetchall()
        assert not any(duplicates.values()), duplicates
        result["duplicate_groups"] = duplicates
    # Probe real constraints in rolled-back transactions, only on the guarded
    # disposable file. No invalid row is ever committed.
    with sqlite3.connect(run / "acceptance.db") as db:
        db.execute("PRAGMA foreign_keys=ON")
        result["constraint_probes"] = {}
        for name, title, school in (("required_title", None, "school-1"),
                                    ("foreign_key", "Probe", "nonexistent-school")):
            try:
                db.execute("INSERT INTO learning_topics (id,school_id,class_id,subject_id,title,created_by,created_at) VALUES (?,?,?,?,?,?,?)",
                    ("constraint-probe", school, "class-sps-7a", "sub-sci", title, "user-teacher-garima", "2026-11-19"))
            except sqlite3.IntegrityError as exc:
                result["constraint_probes"][name] = str(exc)
            else:
                raise AssertionError("Expected constraint was not enforced: " + name)
            finally:
                db.rollback()
        if result["counts"].get("learning_assessment_results"):
            columns = [r[1] for r in db.execute("PRAGMA table_info(learning_assessment_results)")]
            row = list(db.execute("SELECT * FROM learning_assessment_results LIMIT 1").fetchone())
            row[columns.index("id")] = "unique-constraint-probe"
            row[columns.index("submission_id")] = None  # isolate the assessment/student composite uniqueness
            try:
                db.execute("INSERT INTO learning_assessment_results VALUES (" + ",".join("?" for _ in row) + ")", row)
            except sqlite3.IntegrityError as exc:
                assert "assessment_id" in str(exc) and "student_id" in str(exc)
                result["constraint_probes"]["unique_assessment_student"] = str(exc)
            else:
                raise AssertionError("Duplicate assessment/student was accepted")
            finally:
                db.rollback()
        assert db.execute("SELECT count(*) FROM learning_topics WHERE id='constraint-probe'").fetchone()[0] == 0
    (run / "integrity.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("Integrity verified:", len(tables), "tables; Alembic", result["revision"])
    return result


def exercise(run, base, restart=False):
    import httpx
    accounts = json.loads((run / "seed-accounts.json").read_text())
    account = {u["id"]: u for u in accounts}
    with sqlite3.connect((run / "acceptance.db").as_uri() + "?mode=ro", uri=True) as db:
        sid = db.execute("SELECT id FROM students WHERE class_id='class-sps-7a' ORDER BY roll_no LIMIT 1").fetchone()[0]
        other_sid = db.execute("SELECT id FROM students WHERE school_id='school-2' LIMIT 1").fetchone()[0]
        parent = db.execute("SELECT parent_user_id FROM parent_student_links WHERE student_id=?", (sid,)).fetchone()[0]
    roles = {"teacher": "user-teacher-garima", "student": sid, "parent": parent,
             "principal": "user-principal-1", "otherteacher": "user-teacher-arvind"}
    tokens = {}
    checks = []
    with httpx.Client(base_url=base, timeout=90) as client:
        def call(method, path, role=None, body=None, expected=200):
            response = client.request(method, path, json=body,
                headers={"Authorization": "Bearer " + tokens[role]} if role else {})
            assert response.status_code == expected, (method, path, response.status_code, response.text[:500])
            checks.append({"method": method, "path": path, "role": role, "status": response.status_code})
            return response.json() if response.content else None
        def evaluated(result_id):
            for _ in range(100):
                value = call("GET", api + "/assessments/results/" + result_id, "teacher")
                if value.get("panchapadi", {}).get("status") == "complete":
                    return value
                time.sleep(0.2)
            raise AssertionError("Background evaluation did not complete")
        call("GET", "/health")
        assert client.get("/api/v1/docs").status_code == 200
        assert client.get("/api/v1/openapi.json").status_code == 200
        for role, user_id in roles.items():
            u = account[user_id]
            tokens[role] = call("POST", "/api/v1/auth/login", body={"email": u["email"], "password": u["password"]})["access_token"]
        api = "/api/v1"
        support = api + "/learnsphere/students/"
        for role in ("student", "parent", "teacher", "principal"):
            call("GET", support + sid + "/support", role)
            call("GET", support + other_sid + "/support", role, expected=404)
            call("GET", api + "/workspace", role)
        call("GET", support + sid + "/support", "otherteacher", expected=404)
        same_school_unlinked = next(u["id"] for u in accounts if u["role"] == "student" and u["school_id"] == "school-1" and u["id"] != sid)
        for role in ("student", "parent"):
            call("GET", support + same_school_unlinked + "/support", role, expected=404)
        if restart:
            saved = json.loads((run / "workflow.json").read_text())
            result = call("GET", api + "/assessments/results/" + saved["result_id"], "teacher")
            assert result["answers"] == saved["answers"] and len(result["reviews"]) == 2
            assignments = call("GET", api + "/learnsphere/assignments?student_id=" + sid, "student")
            ours = [a for a in assignments if a["snapshot"].get("assessment_result_id") == saved["result_id"]]
            assert sorted(a["id"] for a in ours) == saved["assignment_ids"]
            assert all(a["attempts"] and a["attempts"][0]["completed"] for a in ours)
            for role in ("student", "parent", "teacher", "principal"):
                call("GET", support + sid + "/assessments/" + saved["assessment_id"] + "/guidance", role)
            (run / "restart.json").write_text(json.dumps({"passed": True, "checks": checks}, indent=2))
            audit(run)
            print("Restart persistence verified")
            return
        questions, mapping = fixture_questions()
        assessment = call("POST", api + "/classes/class-sps-7a/assessments", "teacher", {
            "class_id": "class-sps-7a", "subject_id": "sub-sci", "title": "Synthetic persisted LearnSphere acceptance",
            "date": "2026-11-19", "total_marks": sum(q["marks"] for q in questions),
            "questions": questions, "competency_focus": ["LU", "CU", "AU", "CT"]}, 201)
        answers = [{"position": q["position"], **({"answer_text": "An actual saved explanation."}
            if q["type"] == "descriptive" else {"selected_option_index": 0})} for q in questions]
        submission = {"request_key": uuid.uuid4().hex, "answers": answers}
        result = call("POST", api + "/assessments/" + assessment["id"] + "/answers", "student", submission)
        rid = result["id"]
        result_url = api + "/assessments/results/" + rid
        result = evaluated(rid)
        assert result["outcomes"][0]["score"] == questions[0]["marks"]
        assert result["outcomes"][1]["score"] == 1
        assert result["outcomes"][6].get("score") is None
        assert not result["panchapadi"]["teacher_verified"]
        assert len(result["panchapadi"]["stages"]) == 5
        gpath = support + sid + "/assessments/" + assessment["id"] + "/guidance"
        guidance = call("GET", gpath, "teacher")
        assert all(q["guidance"] for q in guidance["questions"])
        assert {q["competency"] for q in guidance["questions"]} == {"LU", "CU", "AU", "CT", "Unmapped"}
        competency_body = {"expected_version": guidance["automation_version"], "request_key": uuid.uuid4().hex,
            "questions": [{"position": 2, "label": "AU", "reason": "The authored question asks for a learned procedure."}]}
        call("POST", support + sid + "/assessments/" + assessment["id"] + "/competencies", "teacher", competency_body)
        call("POST", support + sid + "/assessments/" + assessment["id"] + "/competencies", "teacher", competency_body)
        # Missing evidence in a genuinely separate result must remain null, not zero.
        unknown = call("POST", api + "/classes/class-sps-7a/assessments", "teacher", {
            "class_id": "class-sps-7a", "subject_id": "sub-sci", "title": "Synthetic missing evidence acceptance",
            "date": "2026-11-19", "total_marks": 2, "questions": [questions[6]], "competency_focus": ["CU"]}, 201)
        unknown_result = call("POST", api + "/assessments/" + unknown["id"] + "/answers", "student",
            {"request_key": uuid.uuid4().hex, "answers": [{"position": 0, "answer_text": "Context unavailable."}]})
        missing = evaluated(unknown_result["id"])
        assert missing["outcomes"][0].get("score") is None
        assert all(s.get("score_pct") is None for s in missing["panchapadi"]["stages"])
        for revision in (1, 2):
            body = {"expected_version": result["version"], "feedback": "Acceptance teacher revision " + str(revision),
                "confirm_panchapadi": True, "panchapadi_mappings": mapping,
                "questions": [{"position": q["position"], "score": max(0, q["marks"] - (1 if revision == 1 else 0)),
                    "feedback": "Reviewed saved response.", "verify_key": q["type"] == "mcq"} for q in questions]}
            result = call("POST", result_url + "/review", "teacher", body)
        assert len(result["reviews"]) == 2 and result["reviews"][-1]["panchapadi"]["teacher_verified"]
        assert all(s["score_pct"] == 100 for s in result["reviews"][-1]["panchapadi"]["stages"])
        before = copy.deepcopy((result["answers"], result["reviews"]))
        call("POST", result_url + "/panchapadi/evaluate?refresh_guidance=true", "teacher")
        result = call("GET", result_url, "teacher")
        assert (result["answers"], result["reviews"]) == before
        call("POST", api + "/assessments/" + assessment["id"] + "/answers", "student", submission)
        assignments = call("GET", api + "/learnsphere/assignments?student_id=" + sid, "student")
        ours = [a for a in assignments if a["snapshot"].get("assessment_result_id") == rid]
        assert len(ours) == 2 and {a["snapshot"]["kind"] for a in ours} == {"teach_back", "mission"}
        for assignment in ours:
            attempt_body = {"request_key": uuid.uuid4().hex, "response": "A saved explanation with a justified example."}
            path = api + "/learnsphere/assignments/" + assignment["id"] + "/attempts"
            attempt = call("POST", path, "student", attempt_body, 201)
            duplicate = call("POST", path, "student", attempt_body, 201)
            assert attempt["id"] == duplicate["id"]
            call("POST", path, "parent", attempt_body, 403)
            if assignment["snapshot"]["kind"] == "teach_back":
                attempt = call("POST", api + "/learnsphere/attempts/" + attempt["id"] + "/evaluate", "student")
            call("POST", api + "/learnsphere/attempts/" + attempt["id"] + "/review", "teacher", {
                "expected_version": attempt["version"], "feedback": "Reviewed against the activity rubric.",
                "outcome": "Acceptance example meets the reviewed criterion.", "completed": True,
                "observations": [{"key": "justified-example", "score": 1, "maximum": 1}]})
        for role in ("student", "parent", "teacher", "principal"):
            journey = call("GET", support + sid + "/journey", role)
            assert {o["competency"] for o in journey["assessment_observations"] if o["result_id"] == rid} == {"LU", "CU", "AU", "CT"}
        graph = call("GET", support + sid + "/panchapadi?include_provisional=true", "teacher")
        assert len(graph["graphs"]) == 5
        assert all(any(p["result_id"] == rid and p["score_pct"] == 100 for p in g["points"]) for g in graph["graphs"])
        with sqlite3.connect((run / "acceptance.db").as_uri() + "?mode=ro", uri=True) as db:
            raw = db.execute("SELECT questions_json,answers_json,reviews_json,panchapadi_json FROM learning_assessment_results WHERE id=?", (rid,)).fetchone()
            assert len(json.loads(raw[2])) == 2 and len(json.loads(raw[3])["competency_reviews"]) == 1
            assert len(json.loads(raw[1])) == len(questions)
        saved = {"assessment_id": assessment["id"], "result_id": rid, "student_id": sid, "parent_id": parent, "answers": result["answers"],
            "assignment_ids": sorted(a["id"] for a in ours), "checks": checks,
            "ai_mode": "synthetic model-output fixtures; all API/database/auth/scoring code is real"}
        (run / "workflow.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")
    audit(run)
    print("Persistent API workflow passed:", len(checks), "requests")


def probe_native(run, base):
    """Use an existing seeded paper through unpatched HTTP/provider code."""
    import httpx
    from io import BytesIO
    from PIL import Image
    workflow = json.loads((run / "workflow.json").read_text())
    accounts = {u["id"]: u for u in json.loads((run / "seed-accounts.json").read_text())}
    with sqlite3.connect((run / "acceptance.db").as_uri() + "?mode=ro", uri=True) as db:
        aid, raw = db.execute("SELECT id,questions_json FROM assessments WHERE id='asm-sps-7a-sci-open1'").fetchone()
        questions = json.loads(raw)
    with httpx.Client(base_url=base, timeout=30) as client:
        def login(user_id):
            u = accounts[user_id]
            response = client.post("/api/v1/auth/login", json={"email": u["email"], "password": u["password"]})
            response.raise_for_status()
            return {"Authorization": "Bearer " + response.json()["access_token"]}
        teacher = login("user-teacher-garima")
        student = login(workflow["student_id"])
        answers = [{"position": i, **({"selected_option_index": q["options"].index(q["correct_answer"])}
            if q["type"] == "mcq" else {"answer_text": "An actual acceptance response, awaiting an educator's evaluation."})}
            for i, q in enumerate(questions)]
        response = client.post("/api/v1/assessments/" + aid + "/answers", headers=student,
            json={"request_key": "native-seeded-acceptance", "answers": answers})
        response.raise_for_status()
        rid = response.json()["id"]
        for _ in range(100):
            response = client.get("/api/v1/assessments/results/" + rid, headers=teacher)
            response.raise_for_status()
            result = response.json()
            if result.get("panchapadi", {}).get("status") in {"complete", "failed"}:
                break
            time.sleep(0.2)
        assert result["answers"] == answers
        assert result["outcomes"][0]["score"] == questions[0]["marks"]
        assert all(o.get("score") is None for o in result["outcomes"][1:])
        assert result["evaluation_warnings"], "This probe expects unavailable local model dependencies"
        data = BytesIO()
        Image.new("RGB", (32, 32), "white").save(data, format="PNG")
        ocr = client.post("/api/v1/ocr/extract-preview", headers=teacher,
            files={"files": ("acceptance.png", data.getvalue(), "image/png")}, data={"provider": "qwen"})
        assert ocr.status_code == 503, ocr.text
        summary = {"assessment_id": aid, "result_id": rid, "answers_saved": len(result["answers"]),
            "mcq_score": result["outcomes"][0]["score"], "written_scores": [o.get("score") for o in result["outcomes"][1:]],
            "warnings": result["evaluation_warnings"], "ocr_status": ocr.status_code, "ocr_error": ocr.json(),
            "ai_mode": "native, unpatched; dependencies unavailable"}
        (run / "native-probe.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    audit(run)
    print("Native provider failure verified: answers persisted, MCQ scored, written scores unknown, OCR 503")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "serve", "exercise", "verify-restart", "audit", "probe-native"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18880)
    parser.add_argument("--fixture-ai", action="store_true")
    args = parser.parse_args()
    run = args.run_dir.resolve()
    if not run.is_relative_to(ROOT.resolve()) or run == ROOT.resolve():
        parser.error("Run directory must be a child of this clone's .local-demo directory")
    if args.command == "prepare":
        prepare(run)
        return
    configure(run)
    if args.command == "serve":
        from backend.app.main import app
        from backend.app.db.session import engine
        from sqlalchemy import event
        # Seed ordering remains the legacy application's responsibility. Acceptance
        # runs enforce every FK on all subsequent server connections after seeding.
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
            assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        event.listen(engine.sync_engine, "connect", enable_foreign_keys)
        if args.fixture_ai:
            install_fixture_ai()
            print("ACCEPTANCE FIXTURE AI ENABLED: not live model inference", flush=True)
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=args.port)
    elif args.command == "audit":
        audit(run)
    elif args.command == "probe-native":
        probe_native(run, "http://127.0.0.1:" + str(args.port))
    else:
        exercise(run, "http://127.0.0.1:" + str(args.port), args.command == "verify-restart")


if __name__ == "__main__":
    main()
