# LearnSphere integration amendment ? 2026-11-19

This amendment concerns LearnSphere assessment support and authoring, not the NCERT catalogue. The catalogue contracts, schema and ingestion/publication restrictions remain unchanged.

## Separate competency decisions

`POST /api/v1/learnsphere/students/{student_id}/assessments/{assessment_id}/competencies` requires the existing authenticated educator dependency plus student/result/class authorization. Body: `expected_version` nonnegative integer, `request_key` 1?64 characters, and 1?100 unique question decisions `{position: nonnegative integer, label: LU|CU|AU|CT|null, reason: trimmed 1?2000 characters}`. Unknown fields are rejected. The version counts competency reviews, independently of background heartbeats. Stale versions or reused keys with different decisions return 409; invalid positions return 422. An identical key/payload returns the existing decision. Background evaluation uses the existing result worker and transport.

Decisions append to `AssessmentResultRecord.panchapadi_json.competency_reviews`, using the existing compare-and-swap version. No table or column changes. Original questions, answers and marks-review objects remain immutable. Competency confirmation never confirms marks, Panchapadi stages or instructional completion. Teacher decisions supersede provisional suggestions. Failed inference stays pending; model confidence below 0.85 remains unmapped. Confidence is uncalibrated.

Guidance GET adds optional `automation_version`, `concept_stages`, per-question `competency_mapping`, educator-only `stored_competency` and `concept_evidence`. Noneducators receive a reduced mapping without raw model reasoning or evidence references. Written marking may return null score/correctness when evidence is insufficient. Concepts remain provisional model descriptions. Panchapadi eligibility, percentages and confirmed history retain their independent rules.

## Question Studio and bank

Beta generation accepts optional `competency_distribution: {LU,CU,AU,CT}` with strict nonnegative integer values totaling MCQ + theory counts. Optional `selected_competencies` requests stable even allocation in LU/CU/AU/CT order; optional `total_count` must match the type total. MCQ counts are strict integers 0?15, theory 0?10, total at least one. Schema violations return 422. Legacy requests may omit distributions. Explicit competencies constrain each generation slot and are validated without relabelling output. KVR's current per-question generation, source-fact targeting, duplicate checks and advisory answer-key checks remain in use. The old source Ollama batch transport and its quality-review loop are not introduced.

Manual creation uses KVR's existing `POST /assessments/question-bank`; no duplicate `/assessments/questions` creation route. Existing topic/grade metadata and 2?6 option support remain. Duplicate-option comparison additionally ignores presentation labels, case and repeated whitespace. Empty banks return `[]`, including demo mode.

Deletion keeps school scoping, returns 404 when absent/out of scope and 409 when any persisted assessment JSON snapshot references the question ID or source question ID. Homework has independent frozen snapshots and is not rewritten. Frontend bank writes await server confirmation and never rewrite existing assessment snapshots.

Assignment targets add school_id/school_name. Teachers see class-teacher classes and explicit `TeacherAssignment` class/subject allocations; assessment creation checks the same scope. Principals/admins retain the authorized active-school context. Existing bearer authentication and active-school validation are retained.

## Migrations

None required for this amendment. Existing migration histories are retained byte-for-byte. No application database upgrade, reset, seed, importer or publication operation is part of this integration.
