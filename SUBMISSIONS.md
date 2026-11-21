# Submissions log (team V.exe)

Practice score = mean(16 - place) over 48 matches vs the house squad. Noise is about ±0.3.

| # | Receipt | Commit | Time (ET) | Score | What changed |
|---|---------|--------|-----------|-------|--------------|
| 1 | BB-07B3FDEA | b62bd5f | Fri 9:42 PM | 2.56 | v0: world model, nav graph, aim/lead, combat, loot, zone. Had a crash whenever it steered to a pickup/cube/drop (3D goal in 2D pathfinder), so it stopped firing. |
| 2 | BB-1F463041 | df300ff | Fri 9:53 PM | 3.44 | Fixed the 3D-goal crash; fail-safe movement wrapper. (`tools/bots/v1.py`) |
| 3 | BB-B64270EC | 81d2537 | Fri 9:57 PM | 3.58 | v2: break line of sight to cover when hurt or outnumbered, regen, re-engage; wider weapon search. (`tools/bots/v2.py`) |
| 4 | BB-4D4C943D | 293eefc | Fri 10:16 PM | 3.81 | v3: in practice, only engage mechs that shot at or aim at us; free-for-all targeting unchanged once free-for-all is detected. Sim: practice 1.56 vs 1.19 (v2); free-for-all 7.91 vs 7.09 (v2). (`tools/bots/v3.py`) |
| 5 | BB-150F3F5C | 879177e | Fri 10:43 PM | (scoring) | v4: never retreat in the final 1v1; face whoever is hitting us now. CI green. Sim practice = v3. (`tools/bots/v4.py`) |

## Live free-for-all tests (play.joinbuilders.org, real engine vs server house bots, `tools/live_browser.js`)

| Commit | Match | Place | Kills | Notes |
|--------|-------|-------|-------|-------|
| 293eefc (v3) | YDWHE | 2 | 4 | Reached the final 1v1 with 14 cubes, then kept retreating to cover and lost: motivated v4. Rear hits (x1.5) seen. |
| 879177e (v4) | - | 10 | 1 | Died at 44 s. Single matches are very noisy. |
