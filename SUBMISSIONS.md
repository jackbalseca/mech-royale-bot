# Submissions log (team V.exe)

Practice score = mean(16 - place) over 48 matches vs the house squad. Noise is about ±0.3.

| # | Receipt | Commit | Time (ET) | Score | What changed |
|---|---------|--------|-----------|-------|--------------|
| 1 | BB-07B3FDEA | b62bd5f | Fri 9:42 PM | 2.56 | v0: world model, nav graph, aim/lead, combat, loot, zone. Had a crash whenever it steered to a pickup/cube/drop (3D goal in 2D pathfinder), so it stopped firing. |
| 2 | BB-1F463041 | df300ff | Fri 9:53 PM | 3.44 | Fixed the 3D-goal crash; fail-safe movement wrapper. (`tools/bots/v1.py`) |
| 3 | BB-B64270EC | 81d2537 | Fri 9:57 PM | 3.58 | v2: break line of sight to cover when hurt or outnumbered, regen, re-engage; wider weapon search. (`tools/bots/v2.py`) |
| 4 | BB-4D4C943D | 293eefc | Fri 10:16 PM | 3.81 | v3: in practice, only engage mechs that shot at or aim at us; free-for-all targeting unchanged once free-for-all is detected. Sim: practice 1.56 vs 1.19 (v2); free-for-all 7.91 vs 7.09 (v2). (`tools/bots/v3.py`) |
