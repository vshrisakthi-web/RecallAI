# Next Session — Handoff

> A short note so the next ChatGPT/Cline session can resume context quickly.
> Read `docs/PROJECT_CONTEXT.md` and `docs/mvp-requirements.md` before acting.

## Project location (in repository)

- **Working directory:** `/Users/shrisakthi/projects/RecallAI`
- **Remote:** `https://github.com/vshrisakthi-web/RecallAI.git` (branch: `main`)
- **Latest commit:** `085886b` — "first commit"

## Completed tasks

- **Module 1, Task 1.1 — Define MVP Requirements:** ✅ Complete. Produced
  `docs/mvp-requirements.md`. Documentation only — no code.
- **Module 1, Task 1.2 — Define the three interfaces:** ✅ Complete. Produced
  `docs/interface-specification.md` (popup, side panel, and the 5 dashboard screens,
  with an ownership matrix). Documentation only — no code.

## Current state

- Only documentation and a Git repo exist. **No application code, no packages, no
  configuration** have been created.
- `README.md` is still just `# RecallAI`.
- `docs/` contains: `mvp-requirements.md`, `interface-specification.md`,
  `PROJECT_CONTEXT.md`, `PROGRESS.md`, `NEXT_SESSION.md`. These are **untracked** in
  Git (not committed) pending user approval.
- Planned stack: **React + TypeScript** with **mock data**; Manifest V3 Chrome
  extension for popup + side panel; web dashboard as a standalone page. All
  privacy-first, local-only.

## Next task

- **Module 1, Task 1.3** — Generate the Overview dashboard **Google Stitch design
  prompt** → record in `docs/stitch-prompts.md`. Note: Stitch is an external tool;
  only the prompt is written by the agent, the design export requires the user.

## Relevant files to read (in order)

1. `README.md` — project title.
2. `docs/mvp-requirements.md` — source of truth for scope and boundaries.
3. `docs/interface-specification.md` — the three interfaces + ownership matrix
   (the blueprint Tasks 1.3–1.9 build against).
4. `docs/PROJECT_CONTEXT.md` — condensed context and decisions.
5. `docs/PROGRESS.md` — what is done vs. pending.

## How to continue

- Work **one task at a time**. Ask for the Task 1.2 requirements before starting.
- Do **not** invent scope, completed work, tests, or functionality — record only
  what is verified; mark the rest **[UNKNOWN]**.
- Do **not** commit or push unless explicitly asked.
- After each task, update `docs/PROGRESS.md` (mark complete + next task) and
  refresh `docs/PROJECT_CONTEXT.md` / `docs/NEXT_SESSION.md` if decisions change.
- **Stop and wait for user approval** before moving to the next task.
