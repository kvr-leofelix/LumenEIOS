# Curriculum Catalogue: Frontend Notes

Owner: Claude (frontend only). Codex owns the backend, schemas, migrations and the API contract:
`apps/lumeneios/docs/CURRICULUM_API_INTEGRATION_CONTRACT.md` (contract v1, 2026-11-10). That contract
supersedes the routes proposed earlier in `NCERT_DATABASE_INTEGRATION.md`, and the frontend now follows it.

## Two data sources

| `VITE_CURRICULUM_DATA_SOURCE` | Behaviour |
|---|---|
| unset / `mock` (default) | **Demo mode.** Metadata-only research snapshot (`src/features/curriculum/mocks/researchSnapshot.json`). The screens and demo script below are unchanged. Review decisions are kept in memory only, but follow the same rules as the backend: admin only, `expected_revision`, repeated decision rejected with 409. |
| `api` | **Live backend.** Calls `{VITE_API_URL}/ncert/*` through the existing authenticated client (`apiRequest`, Bearer token from the existing login). There is no fallback to mock data. |

The mock data is loaded with a dynamic `import()`, so it is never fetched in API mode.

## API mode: routes used (exactly the contract's eight)

Adapter: `src/features/curriculum/api/ncertApi.ts`. Wire types: `api/contract.ts`, with field names copied from `backend/app/schemas/ncert.py`.

| # | Method and route | Parameters sent | Used by |
|---|---|---|---|
| 1 | `GET /ncert/releases` | `limit`, `offset` (follows `next_offset`) | Dashboard: the user must pick a release; none is selected automatically |
| 2 | `GET /ncert/availability` | `grade`, `release_id`, `subject_identity_id`, `language` | Overview tab |
| 3 | `GET /ncert/subjects` | `release_id`, `grade`, `language`, `limit`, `offset` | Dashboard subject list |
| 4 | `GET /ncert/nodes/{node_id}` | `language` | Subject header and the Chapters & topics tab (one level per request) |
| 5 | `GET /ncert/mappings` | `release_id`, `subject_node_id`, `language`, `limit`, `offset` | Mapping review list, with "Load more" |
| 6 | `GET /ncert/mappings/{mapping_id}` | `language` | Refetch after a write, or after a 409 STALE_REVISION |
| 7 | `GET /ncert/mappings/{mapping_id}/reviews` | `limit`, `offset` | Review history |
| 8 | `POST /ncert/mappings/{mapping_id}/reviews` | body `{decision, rationale (trimmed, 10–4000 characters), expected_revision}` and nothing else | Approve / Reject / Request revision |

API-mode URLs:
- Dashboard: `/curriculum/catalogue?release=<uuid>&grade=6..8&lang=en|hi|ur`
- Subject: `/curriculum/catalogue/<grade>/<subject node id>?release=<uuid>&lang=..&view=overview|explorer|review`

The subject is identified by the node ID returned from `/subjects`. It is never matched by title.

## Error and empty-state handling

| Response | UI |
|---|---|
| 401 `AUTHENTICATION_REQUIRED` / `INVALID_TOKEN` | "Sign in required" state |
| 403 `FORBIDDEN` | "No access" state, or "Not permitted" inside the decision dialog |
| 404 `NOT_FOUND` | "Record not found" state, or a message in the dialog |
| 409 `STALE_REVISION` | Mapping is refetched and the dialog stays open showing the new revision |
| 409 `INVALID_TRANSITION`, `READ_ONLY_RELEASE`, `EVIDENCE_INCOMPLETE`, `RIGHTS_BLOCKED`, `RELEASE_UNAVAILABLE`, `INVALID_MAPPING` | Specific message; nothing changes in the UI |
| 422 (FastAPI validation) | Field-level message |
| 503 `DATABASE_UNAVAILABLE`, network failure | Error state with "Try again" |
| Empty release, subject, mapping or child lists | Explicit empty states. Never shown as verified or complete |
| `title: null` | "… title not available in <language> (absent or not rights-cleared)" |
| Citation with `metadata_visible: false` | "Redacted pending rights clearance" |
| Mapping rationale or coverage fields `null` | "Not shown: free text stays hidden until evidence is metadata-cleared" |

Availability `AVAILABLE` / `PARTIAL` is described as *registered evidence*, never as official completeness. Missing types are shown as placeholders, stating that missing does not mean officially unavailable. Applicability is always shown as UNVERIFIED.

## Permissions (UI gating only; the backend enforces them using the database role)

- `VIEW_CURRICULUM_CATALOGUE`: admin, principal, teacher.
- `REVIEW_CURRICULUM_MAPPINGS`: **admin only** (contract: global editorial authority). Principals were previously allowed in the prototype and are now view only in both modes.
- Review buttons appear only for admins, and only when `publication_status === 'DRAFT'`. Only allowed transitions are offered.

## Contract and implementation notes for Codex

1. **Transition ambiguity.** The contract says "REVISION_REQUESTED → any decision" and also "Same decision twice ⇒ 409". `decide()` rejects every repeat, including REVISION_REQUESTED → REVISION_REQUESTED. The UI follows the implementation and does not offer that repeat.
2. **Mapping list has no review-state filter.** A "pending review" count covers loaded pages only. The UI labels it "loaded", not total.
3. **Persona vs. token.** The backend authorises using the database user behind the Bearer token. The demo persona switcher logs in asynchronously, so a switch that fails to obtain a token produces 401s. These are shown as such and are never replaced with mock data.

## Integration status

- The adapter and screens are tested against mocked HTTP responses that use the contract's shapes (`__tests__/ncertApi.test.ts`, `__tests__/ApiScreens.test.tsx`). The fixtures in `ncertTestHttp.ts` are synthetic and test-only.
- **Not yet verified against a running backend.** The backend currently has no catalogue rows, so a live run would show the empty-release state. A populated demo needs authorised catalogue data (see `CURRICULUM_BACKEND_IMPLEMENTATION_STATUS.md`).

## Mock-mode demonstration script (unchanged screens)

1. `cd apps/lumeneios && npm install && npm run dev`, then open http://localhost:3000/curriculum/catalogue.
2. Dashboard: scope pill, violet "mock" banner, six combination cards with counts.
3. **Class VII · Mathematics** → Overview: language matrix, syllabus placeholders, Urdu Part II gap.
4. Any **Evidence** button opens the source panel.
5. **Chapters & topics** (Class VI Maths): only the source-checked sections are listed.
6. **Mapping review** as **Admin**: Request revision → a rationale is required → the status changes and the revision increments.
7. Switch persona to **Principal** or **Teacher**: view only. **Student**: unauthorized.

API-mode run: start Codex's backend (`python -m uvicorn backend.app.main:app --port 8000` from `apps/lumeneios`), then
`VITE_CURRICULUM_DATA_SOURCE=api npm run dev`. Log in through the existing persona switcher so a token is issued.
