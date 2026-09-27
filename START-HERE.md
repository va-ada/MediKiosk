# Start here — building MediKiosk with Claude Code

## What's in this kit
| File | Purpose |
|---|---|
| `CLAUDE.md` | Project context. Claude Code loads it automatically every session (and it imports `CONTRACTS.md`). |
| `CONTRACTS.md` | Every endpoint, field, enum and file format — the reason independent tasks fit together. |
| `TASKS.md` | 70 task cards, ~20 minutes each. The cards are the prompts. |
| `PROGRESS.md` | Build order with checkboxes + notes passed between tasks. |
| `.claude/commands/` | `/next`, `/task <ID>`, `/check`, `/status`. **Hidden folder** — copy it too. |
| `.claude/settings.json` | Lets Claude run tests/builds without asking each time; blocks `git push` and reading `.env`. |

## One-time setup (Mac)
1. Install: Docker Desktop, Android Studio, Claude Code, and `brew install uv node ffmpeg ollama`.
2. Start the model download early (large): `ollama pull qwen2.5:3b-instruct-q4_K_M`.
3. Create the repo and copy **everything**, including hidden files:
   ```bash
   mkdir medikiosk && cp -R medikiosk-build-kit/. medikiosk/ && cd medikiosk
   git init && git add -A && git commit -m "Build kit"
   ```

## The loop
```text
claude          # start Claude Code in the repo root
/next           # builds the next ready task, runs its checks, commits
                # review: git show --stat   (undo a bad task: git revert HEAD)
/clear          # fresh context — the files remember everything
/next           # …repeat
/check          # at the end of every phase
```

## Rules that keep it working
- **One task per context.** Always `/clear` between tasks; long conversations drift.
- **Don't let Claude edit `CONTRACTS.md`.** If a task needs a change, it writes a proposal in `docs/contract-change-requests.md`; you decide.
- **Human steps** (Android Studio project creation, phone tests) — Claude stops and tells you.
- Content files marked `DRAFT — clinician review required` (questions, red flags, AYUSH) must be reviewed by a doctor before the finale.

## Working with teammates
Everyone clones the repo. Assign task IDs from `PROGRESS.md` (tracks: F/S server, N NLP, W web, A Android, C content, D demo).
Each person runs `/task <ID>`, then pulls, commits and pushes. If `PROGRESS.md` conflicts, keep both ticks.

## Time
70 tasks × ~20 min ≈ 23 hours of focused work. Budget about double for review and phone testing.
Milestones in `PROGRESS.md` tell you when there is something worth showing.
