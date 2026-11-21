# CLAUDE.md: rules for this repo (team V.exe, Mech Royale)

Read this before changing anything. These rules exist because breaking one can cost us a
submission, our qualifying spot, or the final. They apply to people and AI assistants alike.

## What this is
- Bot for the Builders Buildathon **Mech Royale** track. Protocol and rules: `protocol.md`.
- The scorer builds the `Dockerfile` at the repo top on linux/amd64 and runs `bot.py`.
- Cutoff: **Sun Nov 22, 2026, 11:00 AM ET**. The track page has our submissions:
  https://www.joinbuilders.org/buildathon/tracks/builders
- Practice board: 48 matches vs a 15-bot house squad. The **top 32 qualify** for a
  16-match free-for-all round, and the top 16 of that round play the 64-match free-for-all
  final. So the bot must be good at both practice **and** free-for-all.

## Never do these
1. **Never force-push, rebase or delete `main` history, and never delete the repo or make it
   private.** The final rebuilds the exact commit we choose. If that commit is gone, we score
   nothing.
2. **Never commit secrets, tokens, `.env` files, or the `cache/` folder** (it's gitignored and
   rebuilt by the Dockerfile).
3. **Never copy code from another team's repo** unless it has an explicit permissive license
   (MIT, BSD, Apache), and then credit it in `CREDITS.md`. Repos with no license are
   all-rights-reserved: read them for ideas only.
4. **Never submit a commit that hasn't passed both checks under "Before you submit".**
5. **Never print to stdout** except protocol messages. Logs go to stderr (`mf.log`).
6. **Never write files at runtime outside `/tmp`.** The disk is read-only and the bot runs as
   uid 65534.
7. **Never unpin versions** in the Dockerfile (base image, numpy, scipy). Finalists are rebuilt
   later, and an unpinned dependency can break the build.

## Runtime limits (from the rules)
- 1 CPU, 512 MB RAM, no network, 50 ms per decision, 20 s to send `ready`.
- A late answer means 1 s of coasting **without firing**. Keep the p99 decision time
  **under 15 ms** in `check.py` (currently about 5 ms). Anything heavy belongs in
  `build_cache.py`, which runs at image build time.
- Repo size at the submitted commit must be under 20 MB, and the build must finish
  within 10 minutes.

## Code rules (learned the hard way)
- `act()` must **never raise**. Movement is wrapped in try/except so a bug can't stop us
  firing, and that wrapper must stay. A crash inside `act()` makes the wrapper resend the
  last move without firing. That bug cost us about 0.9 points in v0.
- Pathfinding (`nav.steer`, `walk_clear`) takes **2D** `(x, y)`. Positions from observations
  are **3D** `[x, y, z]`. Convert with `(p[0], p[1])` before passing them in.
- Read numbers from `hello["config"]`, not hard-coded constants, wherever practical.
- Angles: yaw is from +x (east), counter-clockwise, in radians. Wrap differences with `wrap()`.

## Before you submit (every time)
```sh
pip install numpy==2.3.5 scipy==1.16.3   # once
python3 build_cache.py arena              # once, or after changing world.py/nav.py
cd check && python3 check.py -- python3 -u ../bot.py && cd ..   # must PASS, p99 < 15 ms
python3 tools/errscan.py 3 4              # must report 0 errors
python3 tools/sim.py --mode practice --bots bot.py --matches 16
python3 tools/sim.py --mode ffa --bots bot.py:8,tools/bots/<last-submitted>.py:8 --matches 6
```
- The sim (`tools/sim.py`) is an approximation. Use it to compare **A vs B**, not to predict
  absolute scores. Practice mode uses our stand-in house bots (`tools/house.py`).
- The real Docker sandbox check (same flags as the scorer) is in `README.md`.

## Submitting
- **4 submissions per hour per team**, shared by everyone. Coordinate in the team chat
  before using one, and keep at least 1 per hour in reserve for fixes.
- Submit the **exact 40-character commit hash** on the track page. Don't leave the field
  blank if anyone else might push in the meantime.
- After a version is submitted, freeze a copy: `cp bot.py tools/bots/vN.py`. That copy is the
  reference opponent for the next sim comparisons.
- Log every submission in `SUBMISSIONS.md`: hash, time, score, and what changed.
- Scores move ±0.3 between runs from noise alone (48 matches). Don't conclude much from a
  difference smaller than that.

## Picking the final entry
- By default the scorer enters our **best practice score**. Qualifying and the final are
  **free-for-all** against other teams' bots, so before the cutoff, decide deliberately: the
  entry must be top-32 on practice **and** strong in free-for-all. Check the free-for-all sim
  results before picking.

## Strategy notes (how to think about changes)
- Every place is worth the same: going from 16th to 15th is +1, the same as 2nd to 1st.
  Track **how often we score 0** (die first), not just the mean. A policy that survives longer
  but still dies first scores nothing.
- **Practice:** the squad shares sightings, never fights itself, and sends the weakest hunter
  first. More hunters join as we kill them, and all of them hunt late. Non-hunters leave us
  alone unless we hurt them. That's why v3 only engages mechs that shot at or aim at us.
  The goal: kill each pursuer cheaply, recover behind cover, survive the next one.
- **Free-for-all (qualifying and final):** when others are fighting each other, staying healthy
  behind cover through their eliminations earns placement. With one opponent left, waiting
  only helps if it improves our chance to win.
- **Free-for-all detection** (`ffa_score` in `bot.py`) counts drops in `alive` we didn't cause. A
  zone or NPC death could fake it. Test ambiguous cases before leaning on it harder.
- **Zone:** compare time left against travel time along a *walkable route*. A goal that looks
  close may be behind a building. Check the final move command after dodge and unstick
  overrides, since those can undo a safe zone decision.
- **Resources:** judge loot, upgrades and fights against HP, energy, time to cover and the next
  zone crossing. Untried idea: an upgrade order that depends on which weapons we hold.
- **Experiments:** start from the best scored commit. Name one failure mode, one change, and
  the result that would justify keeping it. Only a match result establishes a gain. The
  recorded stream (`tools/replay.py`) only checks decisions and timing.
- Locking a submission other than the best practice score needs a specific free-for-all
  reason and an explicit account of the qualification risk.

(Some of these notes are adapted from a review by ChatGPT.)

## Team workflow
- `git pull` before starting, commit small, push often, and write clear commit messages.
- One feature per commit, so a bad change can be reverted with `git revert` (never by
  rewriting history).
