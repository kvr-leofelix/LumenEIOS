# Differentiated Homework restoration — forensic notes

## Verdict

The original Differentiated Homework (DH) implementation was **not deleted** by PRs #22–#25.
Those PRs are additive backend ports. The regression was a **disconnect** between:

1. the live DH workflow (`homework_*` tables + Teacher/Student/Parent workspaces), and
2. legacy / ported entry points that still used `HomeworkRemediation` or demo DataContext paths.

## What was lost / disconnected

| Item | Cause |
|---|---|
| Intervention assign → student homework workspace | PR #23 `assign_via_homework` created `HomeworkRemediation` instead of DH draft→assign |
| My Classes “assign differentiated homework” | Used `DataContext.assignHomeworkRemediation` (demo), not `/teacher/homework` |
| Student dashboard primary CTA | Emphasized demo mission/quiz; live DH lived only in the sidebar |
| Confusion with dual tracks | Track A = full DH; Track B = legacy remediations still present for older APIs |

## What this restoration branch fixes

- Intervention assign uses `assign_intervention_via_dh` (bank → draft → approve → assign).
- My Classes navigates to live Teacher Workspace with class/student prefill.
- Student dashboard CTA opens `/student/homework`.
- Manual no-AI regression test + existing AI-optional evaluation tests.

## Unchanged on purpose

- PRs #22–#25 branch tips are not rewritten.
- Central question bank, draft lifecycle, submission, and manual evaluation APIs are preserved.
- AI evaluation remains optional (`include_ai_generated` defaults false; AI suggest endpoints stay separate).
