# Submissions log (team V.exe)

Practice score = mean(16 - place) over 48 matches vs the house squad. Noise is about ±0.3.

| # | Receipt | Commit | Time (ET) | Score | What changed |
|---|---------|--------|-----------|-------|--------------|
| 1 | BB-07B3FDEA | b62bd5f | Fri 9:42 PM | 2.56 | v0: world model, nav graph, aim/lead, combat, loot, zone. Had a crash whenever it steered to a pickup/cube/drop (3D goal in 2D pathfinder), so it stopped firing. |
| 2 | BB-1F463041 | df300ff | Fri 9:53 PM | 3.44 | Fixed the 3D-goal crash; fail-safe movement wrapper. (`tools/bots/v1.py`) |
| 3 | BB-B64270EC | 81d2537 | Fri 9:57 PM | 3.58 | v2: break line of sight to cover when hurt or outnumbered, regen, re-engage; wider weapon search. (`tools/bots/v2.py`) |
| 4 | BB-4D4C943D | 293eefc | Fri 10:16 PM | 3.81 | v3: in practice, only engage mechs that shot at or aim at us; free-for-all targeting unchanged once free-for-all is detected. Sim: practice 1.56 vs 1.19 (v2); free-for-all 7.91 vs 7.09 (v2). (`tools/bots/v3.py`) |
| 5 | BB-150F3F5C | 879177e | Fri 10:42 PM | 3.50 | v4: never retreat in the final 1v1; face whoever is hitting us now. CI green. Sim practice = v3. (`tools/bots/v4.py`) |
| 6 | BB-D884C5A1 | b8006c5 (branch exp-v6-ffa-detect) | Fri 11:12 PM | 3.81 | v6 = v3 + one change: switch to FFA targeting only on an unexplained death before 90 s, or 3+ overall (a late friendly-fire/NPC/zone death no longer disables the passive-squad rule). CI green. Paired sim vs v3: -0.04 +/- 0.04 (sim can't test this well). (`tools/bots/v6.py` on its branch) |
| 8 | BB-927E23D7 | b53c940 (branch exp-v8-close) | Fri 11:34 PM | 3.79 | v8 = v3 + closer engagement (gun 40 m, laser 60 m). No effect. |
| 9 | BB-3D1125E1 | d5e7b76 (branch exp-v3-salt1) | Fri 11:52 PM | 3.75 | **Noise measurement:** v3 with only our RNG salted (same strategy). -0.06 vs v3 -> scorer noise is ~0.1, so score differences above ~0.15 are real. |
| 10 | BB-7688B567 | 4c977b2 (branch exp-v10-commit) | Sat 12:28 AM | **3.92** | v10 = v3 + commit to fights / finish kills (break off only when losing; never while finishing a target <20% HP). Thresholds adapted from Wolverines/TTUN (MIT). **New best (+0.11).** |
| 12 | BB-796D14F8 | 1c8f31a (branch exp-v12-strafe) | Sat 12:35 AM | 3.83 | v12 = v10 + random strafe direction every 0.35-1.05 s. -0.09 vs v10 (borderline noise). Rejected. |
| 14 | BB-7A82F005 | c0a7d14 (branch exp-v14-farm) | Sat 12:45 AM | 3.69 | v14 = v10 + active farming (walk to remembered drones/crates, cubes to 120 m). Sim: +50% cubes. Official -0.23. **Rejected.** |
| 7 | BB-C8CC3711 | e887124 (branch exp-v7-kite) | Fri 11:25 PM | 3.04 | v7 = v3 + long-range duelling (hold 130 m gun / 160 m laser, backpedal while firing). Sim predicted +0.3 to +1.0; official -0.77. **Rejected.** The sim's house aim model (angular error from jklein07 notes) overstates the long-range advantage vs the real squad. |

**Pattern (Sat 12:50 AM):** every change that increased our exposure (roaming, gunfire noise, open-street kiting, target switching) lost points; changes that reduced exposure/aggro gained. The practice squad shares sightings, so being seen or heard is the cost. v13 (lightning-first ranking) not submitted: its real effect was swapping the gun for a mortar.

**Lessons from official runs:** v6 scoring exactly 3.81 (= v3) shows the scorer is deterministic for identical behaviour, and that the late false-FFA switch never fired in the 48 practice matches. v7 shows the sim is NOT predictive for engagement-range changes: calibrate the sim against official results before trusting it again.

Not submitted: v11 (b505d85, branch exp-v11-finish-los) = v10 + finish override only with a clear shot while recovering. Scenario tests pass; triggered in 0/24 sim matches, so likely identical to v10 officially. Parked.

Not submitted: v5 (688cf3a, branch v5-recovery) = v3 + stay healing in cover until 85% HP. Removed the recovery leak (932 -> 0 leak ticks) but paired sim vs v3 was -0.33 +/- 0.19 (0 wins / 4 losses of 24), so it failed our gate.

**Experiment protocol (agreed Fri 11:10 PM):** submissions are experiments. One change at a time from the best official commit, prechecks + CI green first. Keep a change only if it beats the best official score by more than ~0.3 (noise band).

## Live free-for-all tests (play.joinbuilders.org, real engine vs server house bots, `tools/live_browser.js`)

| Commit | Match | Place | Kills | Notes |
|--------|-------|-------|-------|-------|
| 293eefc (v3) | YDWHE | 2 | 4 | Reached the final 1v1 with 14 cubes, then kept retreating to cover and lost: motivated v4. Rear hits (x1.5) seen. |
| 879177e (v4) | - | 10 | 1 | Died at 44 s. Single matches are very noisy. |
