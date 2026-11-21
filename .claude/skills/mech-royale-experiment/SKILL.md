---
name: mech-royale-experiment
description: Run one Mech Royale bot experiment safely, from idea to logged official result. Use whenever someone proposes a bot change, a new version, or a submission for team V.exe.
---

# Mech Royale experiment procedure (team V.exe)

Follow these steps in order. They encode what the official scorer taught us (see `LEARNINGS.md`).

## 0. Read first
- `LEARNINGS.md`: every official result so far and the **exposure** pattern (being seen or heard costs points).
- `CLAUDE.md`: the repo rules. `SUBMISSIONS.md`: the log.
- Check that the idea isn't already in "Things that look good but aren't" in `LEARNINGS.md`.

## 1. Frame the experiment (write it down before coding)
- **Parent (baseline rule):** always the highest *official* score (currently v19 `1db8cb836b21bc00e6d15f3399b5e9b0b0ea1c60`, 4.21, branch exp-v19-pkmem). Never build on a lower-scoring commit.
  Check `SUBMISSIONS.md` for a newer best.
- **One change only.** Name the failure mode it fixes and the mechanism.
- **Exposure check:** does it make the bot more visible, more audible, roam more, or fight longer? If yes,
  expect a loss unless there's strong evidence otherwise.
- **Decision rule, stated up front:** keep it only if official > parent + 0.15. Within ±0.15 = no effect.

## 2. Build on a branch (never on `main`)
```sh
git fetch origin <parent-branch> && git checkout -B exp-vN-<name> FETCH_HEAD
# edit bot.py: one change, with a comment naming the version and why
git diff <parent-sha> -- bot.py        # confirm the diff is exactly the intended change
cp bot.py tools/bots/vN.py
```
If the idea comes from another team's code: only MIT/BSD/Apache, rewritten in our code, credited in `CREDITS.md`.

## 3. Verify the decision actually changes
- `python3 tools/replay.py . check/stream.jsonl.gz`: mode counts and timing vs the parent.
- For targeted changes, write a **scenario script** that builds an `obs` for the exact situation and asserts the
  new mode/action, plus the cases that must *not* change (zone danger, clear shot, and so on).
- Optional sim **mechanism** check with paired seeds. Report trigger counts, not predicted scores. **Never
  use the sim to justify a submission:** it ranked v7 best when it was officially worst.

## 4. Gates (all must pass)
```sh
tools/precheck.sh                      # compile, pins, size, no stdout prints, check.py p99<15ms, crash scan
git push -u origin exp-vN-<name>       # triggers CI (scorer sandbox Docker check)
curl -s https://api.github.com/repos/jackbalseca/mech-royale-bot/commits/<sha>/check-runs   # must be success
```

## 5. Submit (only with the team's explicit OK)
- Submissions are the team's decision. Ask before submitting, every time.
- 4 per hour, shared. Use the **full 40-character hash** on the track page.
- A worse score never lowers our entry. Never touch "Pick as our final entry" without the team.

## 6. Log and learn
- Add a row to `SUBMISSIONS.md` and to the results table in `LEARNINGS.md`, with the delta vs the parent and
  a verdict.
- Update the pattern section if the result supports or contradicts it.
- If it wins (> parent + 0.15), it becomes the new parent for the next experiment.
