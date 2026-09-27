---
description: Build one MediKiosk task card from TASKS.md
argument-hint: <task ID, e.g. S04>
---
Build MediKiosk task $ARGUMENTS.

1. Read PROGRESS.md, including its Notes section.
2. Read ONLY the card for $ARGUMENTS in TASKS.md: from the line starting `## $ARGUMENTS · ` up to the next line starting with `## `. Do not read other cards.
3. Check that every task in the card's **Needs** is ticked in PROGRESS.md. If any is not, stop and list what's missing.
4. If the card has a **Human step**, tell me exactly what to do and wait until I confirm.
5. Follow CLAUDE.md and CONTRACTS.md exactly. Create or change only the files the card lists (plus PROGRESS.md). If the card seems to need a contract change, stop and write the proposal in docs/contract-change-requests.md instead.
6. Build it. Then run every Acceptance check and show the output. Checks that need a phone or a browser: give me a short manual checklist instead.
7. If a check fails, fix and re-run — at most 3 attempts. If it still fails, stop and explain what is wrong and what you tried.
8. Update PROGRESS.md: tick $ARGUMENTS. Add one line under "Notes for later tasks" only if a later task needs to know something (a decision, a gotcha, a TODO you left).
9. Commit: `git add -A && git commit -m "T-$ARGUMENTS: <card title>"`.
10. Finish with three short lines — Built / How to see it / Manual checks left — then remind me to run /clear before the next task.
