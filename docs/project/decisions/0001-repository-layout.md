# 0001: Repository layout for the LumenEIOS import

**Status:** Proposed through the pull request that adds it.

## Context

`arena` is the team's central repository. The LumenEIOS application assumes `backend/` and its frontend files sit at the project root: many Python files import `backend.app`, and the Dockerfile and documentation use those paths.

## Decision

- Place the whole application in `apps/lumeneios/`, with its internal layout unchanged.
- Place Differentiated Homework code in `apps/lumeneios/backend/app/modules/differentiated_homework/`.
- Import the application as a single new commit, since its history is unrelated to this repository's.
- Run backend and frontend commands from `apps/lumeneios/`.

## Why

- Moving the application as one unit keeps its imports and relative paths working, with minimal changes to code owned by teammates.
- A Python package can't have a hyphen in its name, so the module folder uses an underscore. Keeping it inside the backend avoids import path workarounds.
- No placeholder folders are created for other teams, because each owner should decide their own structure.

## Consequences

- Backend and frontend share one application folder. Separating them later is possible, and is a decision for their owners.
- Work on other branches, such as `Visual_Text_Extraction`, isn't affected by this change.
