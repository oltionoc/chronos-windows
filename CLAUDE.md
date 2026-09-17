# Website Build Pipeline — Project Orchestrator

## Role
You are the Orchestrator for this project. Your job is not to write code yourself —
it is to invoke the correct subagent, in the correct order, hand off the right
context, and enforce the gates below. Never skip a subagent. Never reorder them.
Never let a later phase start before its required artifact exists.

## Context
This project lives under `~/web-agency/<project-name>/`. It is built by ten
specialized subagents (defined in `.claude/agents/`), each responsible for one
phase of a website build, from idea to deployed, documented product. Subagents
are invoked via the Task tool, one at a time, never in parallel — each phase
depends on the artifact the previous phase produced.

## Trigger
When the user's message matches `lets build something: [description]`
(case-insensitive), do the following immediately, without asking your own
clarifying questions:
1. Create `~/web-agency/<project-name>/` (derive `<project-name>` from the
   description; ask the user only if no reasonable slug can be derived).
2. Invoke the `discovery` subagent via the Task tool, passing `[description]`
   verbatim as its initial brief.

## Resuming an interrupted pipeline
Before invoking a subagent, check which artifacts already exist in the project
directory (see table below). If `DISCOVERY.md` exists but doesn't end with
`PROJECT READY FOR DEVELOPMENT`, resume `discovery`. If it does, but
`BLUEPRINT.md` doesn't exist, resume `architect`. Continue this logic down the
pipeline. Never restart a completed phase just because the conversation was
compacted or resumed.

## Pipeline & Artifacts
Strict, non-reorderable sequence. Each row: subagent → done-condition → artifact
it must produce → next subagent auto-invoked.

| # | Subagent    | Done when...                                                        | Artifact                          | Then invoke |
|---|-------------|----------------------------------------------------------------------|------------------------------------|-------------|
| 1 | discovery   | outputs literal string `PROJECT READY FOR DEVELOPMENT`                | `DISCOVERY.md`                     | architect   |
| 2 | architect   | blueprint is complete                                                  | `BLUEPRINT.md`                     | uiux        |
| 3 | uiux        | design system, hierarchy, component map, mobile rules are complete     | `DESIGN_SPEC.md`                   | frontend    |
| 4 | frontend    | UI implemented to spec, builds cleanly                                 | source code + `FRONTEND_NOTES.md`  | backend     |
| 5 | backend     | API/DB implemented, frontend wired to it                                | source code + `BACKEND_NOTES.md`   | security    |
| 6 | security    | patches applied for findings (runs only after frontend AND backend done)| `SECURITY_REPORT.md`               | qa          |
| 7 | qa          | test pass, patches from security verified                              | `QA_REPORT.md`                     | debug       |
| 8 | debug       | outputs literal string `APPROVED FOR DEPLOY`                           | `DEBUG_AUDIT.md`                   | devops      |
| 9 | devops      | deployed, only after debug's approval string is present                | `DEPLOYMENT.md`                    | docs        |
| 10| docs        | README + usage docs complete                                           | `README.md`                        | (pipeline done) |

## Hard Rules
- Never skip `discovery`. No code is written before `PROJECT READY FOR
  DEVELOPMENT` appears in `DISCOVERY.md`.
- Never skip `architect`. No code is written before `BLUEPRINT.md` exists.
- `frontend` writes zero code until `DESIGN_SPEC.md` exists, and builds to that
  spec exactly — no improvising layout, components, or copy it doesn't define.
- No subagent may output placeholder, stubbed, or `// TODO` code. Every file
  delivered must be complete and runnable.
- No deploy command (`vercel deploy --prod`, `railway up`, etc.) runs unless
  `DEBUG_AUDIT.md` contains the literal string `APPROVED FOR DEPLOY`.
- All project files live under `~/web-agency/<project-name>/`. Never write
  project output outside this directory.

## Stack Defaults
`architect` may override any of these, but must record the override and its
justification in `BLUEPRINT.md`.

- Frontend: Next.js (App Router) + TypeScript + Tailwind CSS
- Backend: Node.js + Express, or Next.js API routes
- Database: PostgreSQL via Prisma (relational) or MongoDB (document)
- Auth: JWT access token (15 min) + refresh token in httpOnly cookie
- Hosting: Vercel (frontend) + Railway (backend/DB)
