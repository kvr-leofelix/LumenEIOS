# Archived: Codex academic-workflow prototype (10 Nov 2026)

These uncommitted files were Codex's first browser-only implementation of the
configuration → schedule → execution → recovery workflow. They are superseded by
`src/lib/planning/*` and kept here unmodified for reference. They are outside
`src/`, so they are not compiled or tested.

Browser data written by the prototype (localStorage key `lumeneios_academicWorkflow`)
is never deleted: the new store reads its configuration once for migration and
reports how many prototype plans remain there.
