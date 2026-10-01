# Task briefs for Codex

One brief per piece of [PANEL-PLAN.md](../PANEL-PLAN.md). Codex reads `AGENTS.md` itself; a brief holds only the goal,
files, names, the acceptance test and what not to touch. Run one task at a time, in its own worktree:

    git worktree add ../vw-task -b task/<name> && codex exec -p unsloth -s workspace-write -C ../vw-task "$(cat docs/tasks/<file>)"

Tests gate the merge; a done brief is deleted in the commit that finishes it.
