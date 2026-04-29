# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-28T23:01:03+08:00
**Commit:** 55e515f
**Branch:** refactor/card-entity-rebuild

## OVERVIEW

Phase 1 minimal prototype for a Hermes → Feishu card-entity bridge. Contains Python package, tests, and CLI.

## STRUCTURE

```text
feishu_messaging_card_builder/
├── README.md              # user-facing landing page
├── AGENTS.md              # agent/developer operating rules
├── src/                   # Python package source code
├── tests/                 # core test suite (49 tests)
├── docs/                  # direction, research, phase 1 decisions, standards
├── LICENSE
└── .gitignore
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Understand phase and public purpose | `README.md` | Keep concise and user-facing. |
| Navigate docs | `docs/README.md` | Canonical reading order. |
| Phase 1 Decisions | `docs/phase-1-prototype-decisions.md` | Why the prototype is built this way. |
| Outbound Seam | `docs/hermes-outbound-seam-memo.md` | Integration points with Hermes. |
| Validation Evidence | `docs/phase-1-live-validation.md` | Proof of prototype success. |
| Project boundaries | `docs/project-direction.md` | Entity-first, websocket-only, reversible external changes. |
| Feishu card facts | `docs/feishu-card-research.md` | Card JSON v2, `card_id`, entity lifecycle constraints. |
| Git process | `docs/git-standards.md` | Branch, commit, PR, history rules. |

## CURRENT PHASE

- Phase 1: Minimal prototype implementation and validation.
- Verify core logic with `.venv/bin/python -m pytest`.
- Explore new integration seams in `docs/hermes-outbound-seam-memo.md`.
- Do not turn remaining open questions into implementation assumptions.

## NON-NEGOTIABLE PROJECT CONSTRAINTS

- Feishu connection scope is Hermes Feishu/Lark websocket only.
- Webhook is official background context, not a design target, config path, or test matrix item.
- Feishu card flow is entity-first: create card entity → obtain `card_id` → send/update by card ID.
- Prefer official Feishu APIs; check official API documentation before self-implementation; keep the implementation simple (Plan 2 live validation reference).
- One-shot raw Card JSON sending must not become the primary path.
- Any Hermes/runtime/non-repo modification must be installable, checkable, updateable, uninstallable, auditable, and recoverable.
- Hermes model calls, tool calls, sessions, and command semantics remain semantic source of truth; card display must not pollute them.

## README BOUNDARY

README is for users: what this repo is, current stage, docs links, authoritative sources.

Keep out of README:

- detailed agent workflow;
- scoring/routing instructions;
- Git process detail beyond links;
- anti-pattern lists;
- validation checklists;
- internal rationale duplicated from docs.

Put those in `AGENTS.md`, `docs/AGENTS.md`, or the focused docs under `docs/`.

## ANTI-PATTERNS

- Do not revive old patch-package assumptions.
- Do not default to modifying `Hermes/gateway/run.py`.
- Do not recreate removed files: `install.sh`, `check.sh`, `update.sh`, `uninstall.sh`, `run.py.patch`, `feishu_card_build/`, `tests/`, or old migration docs.
- Do not design webhook endpoints, request URL handling, HTTP service deployment, or webhook signature handling for the first path.
- Do not treat Card JSON as the core state model; model card entities and `card_id` lifecycle.
- Do not apply opaque overwrite-style changes to Hermes or runtime files.
- Do not make giant mixed-scope commits or PRs.

## COMMANDS

```bash
# Core logic validation
.venv/bin/python -m pytest

# Git cleanliness validation
GIT_MASTER=1 git diff --check

# CLI help check
.venv/bin/python -m feishu_messaging_card_builder.cli --help
```

## GIT RULES

- Branches start from `dev`.
- Current work branch: `refactor/card-entity-rebuild`.
- Use English Conventional Commits, e.g. `docs: define websocket-only project roadmap`.
- Keep commits atomic by concern.
- Do not rewrite shared `main` or `dev` history.
- If pushing a new branch, use upstream setup: `GIT_MASTER=1 git push -u origin <branch>`.

## VALIDATION BEFORE FINISHING

- Read `README.md` and relevant `docs/*.md` after edits.
- Ensure all 49 tests pass via `.venv/bin/python -m pytest`.
- Search for stale old-implementation references before finalizing.
- Run `GIT_MASTER=1 git diff --check`.

## NOTES

- Existing docs intentionally define direction, not short-term task breakdown.
- `docs/open-questions.md` is a constraint list; unresolved items should block design commitments, not be bypassed.
- If implementation begins later, update this file and docs validation rules in the same change.
