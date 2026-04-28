# DOCS KNOWLEDGE BASE

## OVERVIEW

`docs/` is the source of project direction, research findings, roadmap, Git process, and unresolved design questions.

## WHERE TO LOOK

| Need | File | Rule |
|------|------|------|
| Reading order | `README.md` | Keep current when adding docs. |
| Stable project constraints | `project-direction.md` | Update before changing design assumptions. |
| Hermes official-source context | `hermes-research.md` | Mark webhook as background only. |
| Feishu card constraints | `feishu-card-research.md` | Keep `card_id` lifecycle central. |
| Long-term development route | `roadmap.md` | Preserve stable vs flexible split. |
| Git and PR rules | `git-standards.md` | English Conventional Commits. |
| Unresolved decisions | `open-questions.md` | Do not convert questions into silent assumptions. |

## DOC CONVENTIONS

- Keep README-style documents concise; put operational detail here or in focused docs.
- Cite official Hermes/Feishu sources when adding factual claims.
- Distinguish verified facts, project decisions, and open questions.
- Prefer Chinese prose for project docs unless a file already has English operational headings.
- Do not add implementation task lists to direction docs.

## DOC ANTI-PATTERNS

- Do not duplicate the same project constraint across every document unless it is a local scope note.
- Do not make `webhook` look like an active design target.
- Do not imply tests/build commands exist while repo is docs-only.
- Do not bury reversible Hermes-change requirements only in roadmap or Git docs.

## CURRENT VALIDATION

```bash
GIT_MASTER=1 git diff --check
```

Manual checks:

- README remains user-facing.
- Root `AGENTS.md` carries agent workflow and anti-patterns.
- `docs/README.md` links every docs file.
- No stale references to removed old implementation files except as explicit anti-patterns.
