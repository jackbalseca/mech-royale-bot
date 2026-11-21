# Submissions log (team V.exe)

Practice score = mean(16 - place) over 48 matches vs the house squad. Noise is about ±0.1 (differences above ~0.15 are real).

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
| 15 | BB-16A0276D | 08fe076 (branch exp-v15-quiet) | Sat 12:53 AM | 3.85 | v15 = v10 + no optional gunfire (crates never; drones only in self-defence). -0.07 vs v10 = **no effect**: noise is not what costs us. |
| 16 | BB-6B0150F6 | 3881e26 (branch exp-v16-still) | Sat 1:29 AM | **4.02** | v16 = v10 + stay put when idle (no drift to the zone hold point; zone logic still moves us 10 s ahead). +0.10 vs v10 (edge of noise). **New best**; parent for the next builds. |
| 17 | BB-7B6E7FAD | dd5fc9c (branch exp-v17a-lootrange) | Sat 1:36 AM | 3.75 | v17a = v16 + weapon-pickup search cut from 160/90 m to 60/40 m. -0.27 vs v16. **Rejected**: a second weapon is worth the walk. |
| 18 | BB-F7310B92 | 6f03444 (branch exp-v18-upgrades) | Sat 1:45 AM | 3.92 | v18 = v16 + upgrade order plating, nanites, armor (was armor first). -0.10 vs v16 = noise: **no effect** (few upgrades per match). |
| 19 | BB-61461C02 | 1db8cb8 (branch exp-v19-pkmem) | Sat 1:54 AM | **4.21** | v19 = v16 + remember weapon pickups after they leave view; fetch one when a slot is empty (same 160 m / zone limits). **+0.19 vs v16: new best and baseline.** |
| 20 | BB-0F3F01A0 | 7034345e6c711cdcc5a8c4212930cc1e61a7d25e (branch exp-v24-bundle) | Sat 5:10 AM | 4.31 | v24 = v19 + bundle: heal (hurt, no mech target: no NPC/crate fire, no cube/drop/swap walks, cover or stand still), keep-gun (16c2fa3), bullet dodge (33862a2, TTUN MIT). +0.10 vs v19 (no effect as a whole); read with the ablations below. |
| 21 | BB-04370ACF | a941c5d4e363a1ba7181b047cfefdcb890267e84 (branch exp-v24a-nododge) | Sat 5:13 AM | 3.81 | v24a = v24 with V24_DODGE = False. -0.50 vs v24: **bullet dodge is worth ~+0.5.** Rejected. (3.81 = v3/v6 by coincidence, 183/48; very different builds.) |
| 22 | BB-CA3E8E44 | cfd3911dce670bf442cc26a90cdf7332b14c5581 (branch exp-v24b-noheal) | Sat 5:16 AM | **4.50** | v24b = v24 with V24_HEAL = False (keep-gun + dodge). +0.19 vs v24, +0.29 vs v19: **heal costs ~0.19. New best and baseline.** |
| 23 | BB-D7A3919D | d57c157638e76eead5cf58ce08a091a5283e5c03 (branch exp-v25-bundle) | Sat 5:42 AM | 4.02 | v25 = v24b + bundle: laser dodge (sidestep any mech charging at us), laser seek (first laser up to 240 m, from v21), never take a mortar (from v20). -0.48 vs v24b. **Rejected**; read with the ablations below. |
| 24 | BB-11AC6902 | 343ecad2eb8146b7cd69feab9f5b43a59301a7d7 (branch exp-v25a-nolaserdodge) | Sat 6:11 AM | 4.10 | v25a = v25 with V25_LASERDODGE = False. +0.08 vs v25: **laser dodge has no effect** (noise). Rejected (-0.40 vs v24b). |
| 25 | BB-2CCFDD17 | d8766a669abacf2e386e57ce49978678affb84da (branch exp-v25b-noseek) | Sat 6:14 AM | 4.25 | v25b = v25 with V25_LASERSEEK = False. +0.23 vs v25: **laser seek to 240 m costs ~0.23.** Rejected (-0.25 vs v24b). |
| 26 | BB-50A8A6E7 | 8a73e9b7d565096b0f24ec6e132c132a69037b0a (branch exp-v25c-nomortaroff) | Sat 6:19 AM | 4.17 | v25c = v25 with V25_NOMORTAR = False. +0.15 vs v25: **refusing mortars costs ~0.15.** Rejected (-0.33 vs v24b). Effects add up (0.46 vs 0.48 total drop); baseline stays v24b 4.50. |
| 27 | BB-0045A905 | 89186db1357e (branch exp-v26a-dodgehold) | Sat 10:56 AM | **4.54** | v26a = v24b + bullet dodge holds its sidestep 0.35 s. +0.04 (noise) but best. (Rayhaan) |
| 28 | BB-7CC6B1D2 | e2fd89416277 (branch exp-v26b-dodgenoboost) | Sat 10:59 AM | 3.85 | v26b = v24b + dodge never boosts. -0.65: **the boost is what makes the dodge work.** (Rayhaan) |
| 29 | BB-96F78337 | 8d18fc4acfbb (branch exp-v26c-dodgereach) | Sat 11:02 AM | 4.21 | v26c = v24b + dodge reach 3.6 -> 5.0. -0.29: over-dodging hurts. (Rayhaan) |
| 30 | BB-A170C981 | 25b327edb305 (branch exp-v26d-drops) | Sat 11:07 AM | 4.40 | v26d = v24b + supply-drop capture. -0.10: no effect. (Rayhaan) |
| 31 | BB-4C59BC59 | 8457a20 (branch exp-v27-bundle) | Sat 1:05 PM | rejected | Repo was private at submit time ("could not clone"). Still used a slot. |
| 32 | BB-1028F7DC | 1bf5a517003f (branch exp-v27r-fightloot) | Sat 1:12 PM | 4.46 | v27r = v26a + giddygiddyboy tweaks (focus, finish 20 m, lethal laser, fight-time cubes). -0.08: no effect as a bundle. |
| 33 | BB-DE6A6FE6 | 05180cc1e06a552afc81ef332935867b31c8e222 (branch exp-v28-core) | Sat 1:33 PM | **5.13** | v28 = v26a + giddygiddyboy's practice combat core (MIT, rewritten in Python): engage rules + sticky weak-target score, fight_move position scoring with range floors, latency-compensated aim + slew fire check, short lose-rule retreat, lethal laser. **+0.59: new best and baseline. Rank 64/274; cutoff 5.58.** |
| 34 | BB-03DDDE1C | fb664bb31fee70f434ffa01f6795dcd2096e3245 (branch exp-v29-path) | Sat 1:43 PM | 4.94 | v29 = v28 + laser only at mechs + drone/crate fire only >= 50% HP (with drone return fire) + eager reload (giddygiddyboy, MIT). -0.19 vs v28: **rejected**; singles v29a/b/c built to find the culprit. |
| 35 | BB-6CDF3686 | bb09304b3fe3817696f95b3a03f9eb2f0f1b7960 (branch exp-v29a-lasermech) | Sat 4:01 PM | 5.06 | v29a = v28 + laser charged only at mechs. -0.07 vs v28: no effect. So v29's -0.19 came from V29_SIDE and/or V29_RELOAD (v29b/v29c built, not submitted). |
| 36 | BB-CBC75C1F | a9448acc64eda212ed4a623eb59e6af217c4ef7c (branch exp-v31-farm) | Sat 4:49 PM | 4.77 | v31 = v28 + giddygiddyboy's loot chooser: walk to cubes (105 m), crates and drones (150 m, >50% HP) between fights. -0.36 vs v28: **rejected**. Farming hurts us (again, like v14 -0.23). |
| 37 | BB-78D5C624 | db7b7a8cbf0b0c90f63bee5963021c2c16b20b2a (branch exp-v30-nav) | Sat 4:56 PM | 4.98 | v30 = v28 + fast unstick (0.7 s, random dir 0.5 s, jump once) + grid cover search around corners. -0.15 vs v28: rejected (no gain). |
| 38 | BB-8FDD338D | e3a0da9550e035af5737dad1b3d334673f850d42 (branch exp-v32-openrec) | Sat 5:01 PM | 5.13 | v32 = v28 + Kanyaraasi opening recovery (first 60 s). **Exact repeat of v28 (246/48)**: the trigger (losing trade or gun-only vs armed in the first 60 s) evidently never fired officially. No effect. |
| 39 | BB-B6D0ABD4 | 927da0833b2384bb286e114d7bf2407a489ac1f3 (branch exp-v34-upgrades) | Sat 5:07 PM | **5.15** | v34 = v28 + giddygiddyboy upgrade orders (laser-first in practice, default in FFA). +0.02 vs v28: noise, but highest score, so **new baseline** (and auto-entered). |
| 40 | BB-0C51BA29 | a49150e9d8f27763a633644ddd4557f066d56afc (branch exp-v35b-nomortar) | Sat 5:15 PM | 4.79 | v35b = v34 + never take a mortar in practice. -0.36 vs v34: **rejected**. Third time no-mortar lost (v20-era, v25, v35b). |
| 41 | BB-73BB1D2B | fa73532471ddb663885d092a3c9584ccf806bed3 (branch exp-v36-cornered) | Sat 5:38 PM | **5.27** | v36 = v34 + Go-faithful lose rule (in-view mechs, finish <25%, no retreat late/while finishing) + fight when cornered instead of fleeing in the open (port audit finding 1). +0.12 vs v34: **new best and baseline**. |
| 42 | BB-3053960E | f89a47246c2c5765f18c1a46b2d3265c9e4445dd (branch exp-v37b-aimfix) | Sat 5:50 PM | 5.27 | v37b = v36 + aim/fire fixes (aim at top over walls, strict laser release, gun lead while laser charges). **Exact repeat of v36 (253/48)**: the changes fire constantly, so net zero / coincidence. Ties keep the earlier v36. |
| 7 | BB-C8CC3711 | e887124 (branch exp-v7-kite) | Fri 11:25 PM | 3.04 | v7 = v3 + long-range duelling (hold 130 m gun / 160 m laser, backpedal while firing). Sim predicted +0.3 to +1.0; official -0.77. **Rejected.** The sim's house aim model (angular error from jklein07 notes) overstates the long-range advantage vs the real squad. |

**Pattern (Sat 12:50 AM):** every change that increased our exposure (roaming, gunfire noise, open-street kiting, target switching) lost points; changes that reduced exposure/aggro gained. The practice squad shares sightings, so being seen or heard is the cost. v13 (lightning-first ranking) not submitted: its real effect was swapping the gun for a mortar.

**Lessons from official runs:** v6 scoring exactly 3.81 (= v3) shows the scorer is deterministic for identical behaviour, and that the late false-FFA switch never fired in the 48 practice matches. v7 shows the sim is NOT predictive for engagement-range changes: calibrate the sim against official results before trusting it again.

Not submitted: v11 (b505d85, branch exp-v11-finish-los) = v10 + finish override only with a clear shot while recovering. Scenario tests pass; triggered in 0/24 sim matches, so likely identical to v10 officially. Parked.

Not submitted: v5 (688cf3a, branch v5-recovery) = v3 + stay healing in cover until 85% HP. Removed the recovery leak (932 -> 0 leak ticks) but paired sim vs v3 was -0.33 +/- 0.19 (0 wins / 4 losses of 24), so it failed our gate.

**Experiment protocol (agreed Fri 11:10 PM):** submissions are experiments. One change at a time from the best official commit, prechecks + CI green first. Keep a change only if it beats the best official score by more than ~0.15 (noise is about ±0.1).

## Live free-for-all tests (play.joinbuilders.org, real engine vs server house bots, `tools/live_browser.js`)

| Commit | Match | Place | Kills | Notes |
|--------|-------|-------|-------|-------|
| 293eefc (v3) | YDWHE | 2 | 4 | Reached the final 1v1 with 14 cubes, then kept retreating to cover and lost: motivated v4. Rear hits (x1.5) seen. |
| 879177e (v4) | - | 10 | 1 | Died at 44 s. Single matches are very noisy. |
