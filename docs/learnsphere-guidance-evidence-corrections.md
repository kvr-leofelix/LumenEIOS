# Automatic guidance and Adheeti evidence corrections

## Causes

The assessment pipeline already scheduled guidance once, but had no automatic transient retry or recovery sweep after a failure/restart. It saved guidance only after finishing the whole evaluation, including the slower activity-draft calls. An interrupted job could therefore remain `running` with no saved question advice. The read adapter also required the exact review revision ID, hiding earlier saved guidance even when the same locked questions, responses, evaluated marks and stage demands remained unchanged.

The existing Science result has a teacher-confirmed Adheeti mapping for Q1 and a confirmed score of 2/2. Its immutable review snapshot also contains a redundant default-false `prerequisite_test` checkbox. The calculator treated that false checkbox as a veto of the explicit signed stage mapping, reporting no eligible evidence. Later interrupted AI jobs also contained empty mapping/score placeholders, which could hide prior valid evidence.

## Targeted fixes

- The existing submission/review/retry background hook now retries missing question guidance, initially after 5 and 20 seconds. Successful questions are reused rather than regenerated.
- The existing worker saves stages, outcomes and each completed question's guidance through its compare-and-swap metadata writes before attempting the remaining work. These checkpoints also provide running-job heartbeats.
- A recovery coroutine in the same worker module starts with the existing backend lifespan. It checks historical missing/partial guidance automatically every 30 seconds. Failures use a capped cooldown, up to 15 minutes; abandoned running jobs are recovered after their existing 30-minute lease expires. It does not introduce a queue platform, table, column, dependency or new public endpoint.
- Saved guidance can be reused across review revisions only when the frozen result/response, question marks, maximum, correctness, competency and relevant stage demands match. Changed marks or stage eligibility invalidate the affected question. Teacher-reviewed outcomes remain preferred, and advice remains labelled provisional AI guidance.
- Explicit teacher-confirmed Adheeti mappings now serve as the prerequisite/readiness attestation. A redundant false checkbox cannot negate that signed mapping. AI-only Adheeti mappings still require prerequisite evidence. Abhyas/Prasar gates, minimum question counts, weighted-mark calculations and missing-score rules remain unchanged.
- LearnSphere recalculates a read projection from confirmed mappings and actual confirmed marks. It never overwrites an archived teacher review or substitutes an AI result for it. An interrupted inference job cannot blank valid prior evidence. The existing evidence cell now includes the scored-question count and references; the layout and graph design are unchanged.
- The existing Learning Support polling receives pending/running statuses until guidance is ready. The missing-guidance message now explains automatic processing rather than requiring a teacher refresh. GET requests only read saved guidance: inference is triggered by assessment events or the recovery worker, not dashboard requests.

The existing activity assignment IDs and revision/attempt protections are retained, so retries do not create duplicate Teach-Back challenges, missions, student attempts or completion evidence. No historical answers, marks or teacher reviews are rewritten. Invalid/missing evidence remains insufficient; a genuine scored zero remains zero.

## Verification

- Full isolated backend suite: **586 passed, 4 opt-in tests skipped**.
- Five new tests cover automatic transient retries, per-question checkpoints and reuse, historical recovery and cooldown/running leases, no duplicate activities, unchanged responses/reviews, the legacy confirmed Adheeti case, independent stage gates, real zero versus unknown scores, and invalidation when actual evidence changes.
- Frontend TypeScript/Vite production build passed. Its pre-existing large-bundle advisory remains.
- Read-only inspection of the existing Science record returned **Adheeti 100%, 1 eligible scored question, Verified**, and **4/4 reusable saved guidance entries**, with the stored review objects unchanged. The original archived insufficient-evidence snapshot remains preserved as audit history.

Files changed: `backend/app/services/panchapadi.py`, `assessment_guidance.py`; `backend/app/api/v1/assessment_results.py`; `backend/app/main.py`; `src/components/learnsphere/PanchapadiEvaluation.tsx` (evidence-cell text only); `backend/tests/conftest.py`, `test_guidance_recovery.py`; this report. No Studio, question-generation, question-bank, assessment-creation or graph-design files were changed. No migration or configuration change was required. No Git operations were performed.

## Website verification

If the backend has not automatically reloaded, restart it once to load the recovery coroutine. Do not reset or initialise the database manually.

1. Open Learning Support and select the existing Science assessment. Its four matching saved guidance entries should appear without clicking Refresh. Check the Adheeti row: **100%**, **1 scored question: Q1**, **Verified**.
2. Submit another assessment normally. Guidance should appear as it is saved, with provisional advice clearly distinguished from reviewed marks. Temporary failures retry automatically while the existing page polls; no teacher action is required. Generation still requires Ollama to be available and may take minutes on CPU.
3. Reopen the assessment or wait through a retry. There should still be only one automatic Teach-Back and one automatic mission for that assessment/student; no student attempts or completions should be added until real work is submitted/reviewed.
4. Check a stage with genuinely no scored eligible questions. It must still show `Insufficient evidence`.
