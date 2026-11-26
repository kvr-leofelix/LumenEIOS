# Curriculum Catalogue API contract v1 — 2026-11-10

Codex owns all backend APIs, schemas, catalogue models, migrations and tests. Claude owns frontend only. This contract supersedes earlier proposed HTTP routes/ownership in NCERT_DATABASE_INTEGRATION.md and chronological implementation plans. Existing curriculum/time-aware endpoints remain unchanged. No importer, publication endpoint or research-CSV ingestion is introduced.

## Transport and permissions

Base `/api/v1/ncert`. JSON. Mandatory `Authorization: Bearer <existing login token>` even in DEMO_MODE. Database user role, not token role or X-School-Id, controls access. Catalogue is global: no school filters or school copies. Read: admin/principal/teacher. Review: admin only (global editorial authority; school principal may read but cannot change global decisions). Draft release access: admin only; teachers/principals may read PUBLISHED releases only. WITHDRAWN releases return 409. No silent latest release selection.

Language query: `en|hi|ur`, default en. No fallback: absent requested text returns title=null, resolved_language=null. Additional languages require a documented contract expansion. IDs: UUID strings. grade: integer 6..8. limit: integer 1..100 default50; offset: integer >=0 default0. List response always `{items: [...], next_offset: integer|null}`. Offset pagination is deterministic by id (hierarchy by sequence,id); refresh after writes.

## Routes

| Method | Route | Parameters/body | Response |
|---|---|---|---|
| GET | `/releases` | limit,offset | Page[Release] permitted visible releases |
| GET | `/subjects` | release_id required UUID, grade required, language,limit,offset | Page[Node] direct SUBJECT children of grade |
| GET | `/availability` | grade required; release_id optional UUID; subject_identity_id optional UUID; language | Availability (below); no release => explicit empty status, never chooses latest |
| GET | `/nodes/{node_id}` | language | Node, including direct children and citations |
| GET | `/mappings` | release_id required; subject_node_id optional UUID; language,limit,offset | Page[Mapping], source TOPIC/SUBTOPIC -> destination LEARNING_OUTCOME only; all verification states included |
| GET | `/mappings/{mapping_id}` | language | Mapping |
| GET | `/mappings/{mapping_id}/reviews` | limit,offset | Page[Review], chronological revision order |
| POST | `/mappings/{mapping_id}/reviews` | ReviewRequest | 201 Review; admin, DRAFT only |

`Release={id,release_key,edition,academic_year:string|null,status:DRAFT|PUBLISHED|WITHDRAWN,created_at:UTC ISO8601,published_at:UTC ISO8601|null}`.

`Citation={evidence_id,source_id,document_type,source_verification:FULL_REVIEW|DISCOVERY_ONLY|INACCESSIBLE,rights_status,metadata_visible:boolean,title:string|null,official_url:string|null,edition:string|null,language:string|null,locator:string|null,notes:string|null}`. Source verification is access/research status, never legal clearance. Bibliographic values/locators are redacted unless rights_status METADATA_APPROVED or CONTENT_APPROVED with nonempty rights_decision. Source/evidence IDs and statuses remain visible. No source paragraphs or outcome wording returned even when CONTENT_APPROVED.

`Node={id,identity_id,release_id,parent_id:string|null,kind,sequence:int,grade_number:int|null,title:string|null,requested_language,resolved_language:string|null,translation_origin:string|null,verification,completeness,citations:Citation[],children:Node[]}`. Only node detail includes direct children; children have empty children arrays (fetch next level explicitly). Titles require the text's own evidence with scoped metadata clearance; missing/unapproved text is null. Translation origin is stored evidence-backed origin, never inferred. No outcome_text returned. Verification/completeness enums are the existing model enums.

`Availability={grade,requested_language,release:Release|null,subject:Node|null,status:NO_RELEASE_SELECTED|SUBJECT_NOT_SELECTED|SUBJECT_NOT_FOUND|AVAILABLE|PARTIAL,resources:Resource[],missing_resource_types:string[],permissions_status:NOT_EVALUATED|PENDING|CLEARED_FOR_METADATA,applicability:UNVERIFIED}`.
`Resource={source_id,document_type,language:string|null,rights_status,source_verification,citations:Citation[]}`. Resources are distinct sources evidenced by the selected subject or descendants; counts refer to registered evidence, never completeness of official publication. Framework, syllabus, LEARNING_OUTCOMES and textbook types remain separate. Missing types are FRAMEWORK,SYLLABUS,LEARNING_OUTCOMES,TEXTBOOK minus observed source types. Empty does NOT mean officially unavailable, never published, or not applicable. Per-edition part/reprint/lifecycle structure is not yet supported by the old source schema; do not invent it from URLs. An unavailable language is an explicit null/unverified result, not a translation.

`Mapping={id,release_id,relationship_type,directionality,source:Node,destination:Node,verification,creation_method,curriculum_applicability:UNVERIFIED,publication_status,permissions_status:PENDING|CLEARED_FOR_METADATA,evidence:[{role,citation:Citation}],rationale:string|null,overlapping_outcomes:string|null,uncovered_outcomes:string|null,coverage_assessment:string|null,human_review_state:AWAITING_REVIEW|APPROVED|REJECTED|REVISION_REQUESTED,revision:int,latest_review:Review|null,recovery_eligible:false}`. Free text is redacted unless all evidence is metadata-cleared; endpoint citations remain separately checked. Rationale is the stored explanation; creation_method tells whether AI-suggested. Evidence role SOURCE_ENDPOINT|DESTINATION_ENDPOINT|RELATIONSHIP. Approval does not imply source verification, applicability, publication, permissions or instructional completion; no write mutates the immutable relationship snapshot.

`ReviewRequest={decision:APPROVED|REJECTED|REVISION_REQUESTED,rationale:string (trimmed 10..4000 characters),expected_revision:int>=0}`. Unknown fields forbidden; client-supplied reviewer/verification/rights ignored by rejecting validation.
`Review={id,relationship_id,revision:int>=1,decision,rationale,reviewer_id,reviewed_at:UTC ISO8601}`. Reviewer is authenticated database user ID; timestamp is server UTC. Every decision requires a rationale. Initial revision0/AWAITING_REVIEW. Allowed transitions: AWAITING_REVIEW -> any decision; REVISION_REQUESTED -> any decision; APPROVED -> REJECTED|REVISION_REQUESTED; REJECTED -> APPROVED|REVISION_REQUESTED. Same decision twice =>409 (not an idempotency key). Reopening appends history; never overwrites it. expected_revision must equal latest revision or409. Concurrent inserts protected by unique(relationship_id,revision); losers409. APPROVED additionally requires both endpoint citation links, all three relationship evidence roles and scoped metadata clearance; absent evidence409 EVIDENCE_INCOMPLETE, uncleared rights409 RIGHTS_BLOCKED. This is editorial acceptance only; no verified/rights/publication transition is implemented. Reject/request revision may record a negative decision despite incomplete evidence.

## Separation and safety

Source verification, node/relationship verification, current-curriculum applicability, human decision, rights and release publication are six independent dimensions. No API publishes or updates source rights. Every mapping's applicability remains UNVERIFIED because the existing schema has no independently approved current-applicability assessment. API recovery_eligible always false. PUBLISHED releases read-only; never revise original snapshots through a review action. No fabricated syllabus/outcome/book/node rows, no CSV read-through, no textbook content ingestion.

Schema addition documented before implementation: `CatalogueMappingDecision` in `backend.app.models.ncert_review`, table `ncert_mapping_decisions`: id String(36) PK; relationship_id String(36) FK ncert_relationships.id RESTRICT indexed; revision Integer NOT NULL >=1; decision String(40) CHECK above three values; rationale Text NOT NULL; reviewer_id String(64) NOT NULL (audit ID retained independently of user deletion); reviewed_at DateTime(timezone=True) NOT NULL; UNIQUE(relationship_id,revision). Existing 13-table schema and CatalogueReview enum stay unchanged. Additive migration002 creates only this table, idempotent, no reset/downgrade. Startup registers it. SQLite API write transaction first enables/checks foreign_keys before auth SELECT; this dedicated dependency replaces the legacy session dependency for these routes only, leaving legacy seed ordering unchanged. No application DB is migrated as part of development/testing.

## Errors and empty example

Domain errors: `{detail:{code:string,message:string}}`. 401 AUTHENTICATION_REQUIRED/INVALID_TOKEN; 403 FORBIDDEN; 404 NOT_FOUND; 409 RELEASE_UNAVAILABLE|READ_ONLY_RELEASE|STALE_REVISION|INVALID_TRANSITION|EVIDENCE_INCOMPLETE|RIGHTS_BLOCKED|INVALID_MAPPING; 503 DATABASE_UNAVAILABLE. Standard FastAPI422 validation `{detail:[{loc,msg,type,...}]}` for invalid UUID/enum/range/missing fields. Unexpected faults500, never mock fallback. No default demo-admin authentication.

No release selected (honest current empty state):
```json
{"grade":6,"requested_language":"en","release":null,"subject":null,"status":"NO_RELEASE_SELECTED","resources":[],"missing_resource_types":["FRAMEWORK","SYLLABUS","LEARNING_OUTCOMES","TEXTBOOK"],"permissions_status":"NOT_EVALUATED","applicability":"UNVERIFIED"}
```

Frontend sequence: login; GET releases; explicitly select release; GET subjects by grade; use returned identity_id for availability and node.id for mappings; fetch node detail to explore hierarchy; show evidence/redaction and review states independently; POST review with last revision then refetch mapping/history. Empty release list is a supported real API response, not permission to fabricate fixture records. Synthetic tests are not runtime catalogue data. Live populated demonstration remains blocked on authorised metadata preparation/schema gaps/rights/current-source review, not HTTP integration.
