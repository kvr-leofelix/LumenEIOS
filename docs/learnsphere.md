# LearnSphere and AI Question Studio

LearnSphere lives inside the existing application at `/learnsphere`. It uses real API
responses, existing JWT authentication, school membership, `ParentStudentLink`, and
`StudentAccountLink`. It does not seed student progress or call AI on dashboard reads.

## Workflows

- **Learning Support:** select an authorized student, inspect evidence and rule explanations,
  then create and assign a support intervention. Follow-up assignments can reference an
  earlier assignment for that same student.
- **Learning Journey:** inspect participation, completion, explicit Panchapadi stages,
  historical assessments, homework participation and comparable teacher-reviewed scores.
- **Teach-Back Challenge:** educators create a concept prompt and rubric; students submit an
  explanation. The response is committed before Qwen is called. Failures are retained and
  evaluation can be retried without creating another attempt.
- **Real-Life Missions:** educators create text-based practical tasks, assign to a student or
  authorized class, and review responses with feedback, outcomes and optional scored criteria.

Educator controls are inside “Create or manage …”. Topics must be explicitly authored;
chapters are never inferred from file names. Assigned activity snapshots include the
instructions, rubric, topic, subject, competency, stage and version. Editing a template does
not change those snapshots. Students may submit multiple distinct attempts. Request keys
make retries idempotent. A changed response requires a new key.

AI feedback is advisory and carries no verified score. A teacher review can record completion
without claiming measured understanding. Add scored criteria only when they were actually
assessed. Each criterion includes a score and positive maximum; correctness is optional.
Teacher reviews append revisions. Only the latest teacher revision for an attempt contributes
to analytics; prior reviews/evidence remain intact. Concurrent stale reviews return 409.

## Authorization

Every LearnSphere endpoint requires a real access token, including when legacy DEMO_MODE is
enabled. School headers never substitute for record authorization.

| Role | Scope |
| --- | --- |
| Admin | Existing administrative scope |
| Principal | Home school and active school memberships |
| Teacher | Those schools, additionally requiring `ClassSection.class_teacher_id == user.id` |
| Parent | Explicit `ParentStudentLink` children only; read-only |
| Student | Explicit `StudentAccountLink`, matching account/student school; own records only |

Student/class/school consistency is checked before access. A missing link fails closed.
Assignments from a different current class are unavailable; changing a student's class does
not grant the new teacher access to old-class activity content. Such history is retained.
Subject teachers without a validated class-teacher relationship receive no additional scope.
The frontend remounts its data boundary when account, school or role changes; selectors
remount student-specific pages. API errors never fall back to seed records.

## Evidence and recommendations

The evidence service accepts only explicitly teacher-confirmed observations associated with
a completed activity and the latest review revision. Unknown scores are null, never zero.
Activity completion, submitted homework, OCR text and AI feedback are not mastery evidence.

Existing assessment rows have uncertain provenance and are displayed as historical records,
excluded from scored analytics. Records linked to the existing simulated batch-grading path
are labeled simulated. Default student scores, fixed OCR competency increments and legacy
snapshots are never used as measured progress. Existing homework answers are shown as
participation; no new homework grading or homework lifecycle is introduced.

Recommendations group by subject/topic/competency and use the most recent eligible
observations (default 20). At least 3 observations across 2 distinct activities are required.
A weighted score below 65% then suggests practice. Every finding includes counts, source
references, denominators, correctness/hints where available, dates, the rule and a suggested
intervention. Otherwise the dashboard says **More practice data needed**. This is a dynamic
practice recommendation, never a permanent student classification.

Trend points group by subject, topic, competency and a hash of the frozen instructions/rubric.
Multiple criteria from one attempt form one weighted point. Percentage-point change appears
only with at least two comparable attempt points. It does not establish that an intervention
caused improvement. Different rubrics are not combined into a fabricated improvement curve.

Stages are explicit activity metadata: Adheeti (Prepare), Bodh (Understand), Abhyas (Practise),
Prayog (Apply), Prasar (Extend). They remain separate from LU/CU/AU/CT and Bloom levels.

Configuration defaults (optional environment overrides):

```dotenv
LEARNSPHERE_MIN_OBSERVATIONS=3
LEARNSPHERE_MIN_ACTIVITIES=2
LEARNSPHERE_RECENT_OBSERVATIONS=20
LEARNSPHERE_SUPPORT_THRESHOLD=65
```

## AI integration

Uses existing `OLLAMA_BASE_URL` and `QWEN_QUESTION_STUDIO_MODEL_ID` through the existing
`QwenQuestionStudioService` transport, inference lock, timeout and structured-output support.
The prepared Studio generation prompts are preserved. Teach-back has its own schema:
`correctly_understood`, `missing_concepts`, `misconceptions`, `strengths`, `next_step`.
Invalid output is retried at most once and never saved as successful feedback. A failed
evaluation revision is stored separately. A successful repeat request returns saved feedback.

Only concept instructions, rubric and student response are supplied to Qwen; account names,
school records and unrelated personal information are not appended. Student text is JSON
encoded as untrusted data with an instruction to ignore embedded commands. This mitigates
prompt injection but AI feedback still requires human judgment. Student-written text can
itself contain personal information; educators should discourage including it.

Ollama is optional for browsing, missions, teacher feedback and learning history.
It is required only for Studio generation and teach-back AI evaluation.

## APIs

All paths below are under `/api/v1/learnsphere`; OpenAPI includes typed request/response schemas.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/scope` | Authorized class/student selectors |
| GET | `/summary` | Educator participation/completion counts within authorized scope |
| GET | `/students/{id}/support` | Explainable support findings |
| GET | `/students/{id}/journey` | Timeline, stages, comparable scores |
| GET / POST | `/topics` | Class-scoped topic list / authoring |
| GET / POST | `/activities` | Class-scoped activity templates / authoring |
| PUT | `/activities/{id}` | Revise template, preserving assigned snapshots |
| POST | `/activities/{id}/assignments` | Idempotent student/class assignment |
| GET | `/assignments?student_id=…` | Assigned snapshots, attempts and revisions |
| POST | `/assignments/{id}/attempts` | Idempotent student response submission |
| POST | `/attempts/{id}/evaluate` | Teach-back evaluation / retry |
| POST | `/attempts/{id}/review` | Educator review and optional scored observations |

There is no client-accessible raw evidence-write endpoint. Review creates evidence only
after authorization and score validation. 401 means no valid session; 403 a disallowed role;
404 an unavailable/out-of-scope record; 409 a stale/conflicting request; 422 invalid input;
502 invalid AI feedback; 503 unavailable AI. Failed AI requests explicitly confirm that the
student response was saved.

## Known scope limits

- Teacher access is deliberately limited to validated class teachers.
- Legacy scores cannot be automatically certified or retrospectively mapped to chapters.
- The first release uses text activities; it adds no file attachments or automatic mission generation.
- School summaries report activity participation/completion, not averages of unreliable scores.
- Very large schools may need pagination and batch aggregation; no external queue/cache is required
  for this initial implementation.
- Local live Ollama teach-back and ten-question Studio persistence checks were completed.
  AI content can still be inaccurate despite model-based quality review and needs teacher review.
  PostgreSQL execution remains a deployment check; its schema and transactional offline SQL
  were compiled and validated without connecting to a PostgreSQL service.
