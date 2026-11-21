# LEARNINGS.md: what the official scorer has taught us (team V.exe)

Read this before proposing any change. It is the evidence behind every rule in `CLAUDE.md`.
Last updated: Sat Nov 21, 6:19 AM ET.

## How the official practice score behaves
- **It is deterministic.** Practice runs the same 48 private seeds every time. Resubmitting identical behaviour
  gives the identical score (v6 = v3 = 3.81 to two decimals; another team saw the same).
- **Noise is small: about ±0.1.** Re-rolling only our own RNG (same strategy, `SALT=1`) moved the score by
  0.06 (3.81 -> 3.75). Any behaviour change reshuffles all 48 matches, so treat differences under ~0.15 as
  "no effect" and anything larger as a real effect.
- **Best score counts.** A worse submission never lowers our entry, so submissions are safe experiments. Keep
  re-rolls for measurement only. They don't make the bot stronger and can't close a gap of more than ~0.1.
- **Per-match placements are not published.** Every "why" below is a hypothesis backed only by the score.

## Official results (practice, 48 matches; points = 16 - place)
| Build | Change (single change from the parent) | Score | Delta | Verdict |
|---|---|---|---|---|
| v0 `b62bd5f` | first bot (had a crash that stopped firing) | 2.56 | | |
| v1 `df300ff` | fix the 3D-goal crash | 3.44 | +0.88 | keep |
| v2 `81d2537` | break line of sight to cover when hurt | 3.58 | +0.14 | keep |
| **v3 `293eefc`** | **only engage mechs that shot at / aim at us (leave passive squad bots alone)** | **3.81** | +0.23 | keep |
| v4 `879177e` | 1v1 no-retreat + face whoever hit us last | 3.50 | -0.31 | reject (target switching) |
| v6 `b8006c5` | stricter free-for-all detection | 3.81 | 0.00 | no effect (never triggered) |
| v7 `e887124` | long-range duelling, backpedal at 130/160 m | 3.04 | -0.77 | reject |
| v8 `b53c940` | closer engagement (40/60 m) | 3.79 | -0.02 | no effect |
| v3 re-roll `d5e7b76` | v3, RNG salt only | 3.75 | -0.06 | noise measurement |
| v10 `4c977b2` | commit to fights, finish kills (Wolverines' losing/finishing thresholds) | 3.92 | +0.11 vs v3 | keep |
| v12 `1c8f31a` | random strafe reversal every 0.35-1.05 s | 3.83 | -0.09 | reject |
| v14 `c0a7d14` | active farming (walk to drones/crates, cubes to 120 m) | 3.69 | -0.23 | reject |
| v15 `08fe076` | quiet: no optional gunfire | 3.85 | -0.07 vs v10 | no effect: **sound is not the cost** |
| v16 `3881e26` | stay put when idle (no drift to the zone hold point) | 4.02 | +0.10 vs v10 | keep (edge of noise, consistent with the exposure pattern) |
| v17a `dd5fc9c` | shorter weapon-pickup search (60/40 m instead of 160/90 m) | 3.75 | -0.27 vs v16 | reject: **weapons are worth the walk** |
| v18 `6f03444` | upgrade order: plating, nanites, then armor | 3.92 | -0.10 vs v16 | no effect: upgrade order barely matters | Same 3.92 as v10 with a different build: a repeat by coincidence (188/48), not identical behaviour.
| v19 `1db8cb8` | remember weapon pickups after they leave view; fetch one when a slot is empty | 4.21 | +0.19 vs v16 | keep |
| v24 `7034345` | **bundle** (team decision, not one change): heal + keep-gun + bullet dodge | 4.31 | +0.10 vs v19 | no effect as a whole; the ablations separate the parts |
| v24a `a941c5d` | v24 without bullet dodge (heal + keep-gun) | 3.81 | -0.50 vs v24 | reject: **dodge is worth ~+0.5**. 3.81 = v3/v6 by coincidence (183/48), very different builds |
| **v24b `cfd3911`** | **v24 without heal (keep-gun + bullet dodge)** | **4.50** | +0.19 vs v24, +0.29 vs v19 | **keep: heal costs ~0.19. Current best / baseline** |
| v25 `d57c157` | **bundle** from v24b: laser dodge + laser seek to 240 m + never take a mortar | 4.02 | -0.48 vs v24b | reject; the ablations separate the parts |
| v25a `343ecad` | v25 without laser dodge | 4.10 | +0.08 vs v25 | laser dodge: **no effect** (noise) |
| v25b `d8766a6` | v25 without laser seek | 4.25 | +0.23 vs v25 | laser seek to 240 m **costs ~0.23** |
| v25c `8a73e9b` | v25 without no-mortar (takes mortars again) | 4.17 | +0.15 vs v25 | refusing mortars **costs ~0.15**. Parts add up (0.46 vs 0.48 drop): small interactions |
| v26a `89186db` | dodge holds its sidestep 0.35 s | 4.54 | +0.04 vs v24b | keep (noise, but best before v28) |
| v26b `e2fd894` | dodge never boosts | 3.85 | -0.65 vs v24b | reject: **the boost is the dodge** |
| v26c `8d18fc4` | dodge reach 3.6 -> 5.0 | 4.21 | -0.29 vs v24b | reject: over-dodging hurts |
| v26d `25b327e` | supply-drop capture | 4.40 | -0.10 vs v24b | no effect |
| v27r `1bf5a51` | giddygiddyboy's latest tweaks only (focus, finish, lethal, fight cubes) | 4.46 | -0.08 vs v26a | no effect: tweaks need their combat core |
| **v28 `05180cc`** | **giddygiddyboy's practice combat core (engage rules, fight positioning, latency aim, short retreat)** | **5.13** | **+0.59 vs v26a** | **keep: current best / baseline** |

## The pattern: exposure costs points
In practice we fight 15 house bots that **share every sighting** and **hunt us** (one hunter at first, more as we
kill them, all of them late). Every change that made us **more visible or more audible** lost points:
- v7 backpedalled through open streets (-0.77). v14 roamed to drones and crates and fired more often (-0.23).
- v4 switched targets more, so fights lasted longer (-0.31).

Every change that **reduced exposure or aggro, or shortened fights**, gained:
- v3 stopped poking passive squad bots (+0.23). v10 finishes kills instead of breaking off (+0.11).

**Refined by v15 (Sat 12:56 AM):** removing optional gunfire changed nothing (-0.07), so being *heard* is not
the cost. What hurts is **movement and visibility**: roaming (v14), open-street backpedalling (v7), longer fights (v4).

**Exception found by v17a (Sat 1:40 AM):** walking to *weapons* pays; cutting the weapon search to 60/40 m cost -0.27.
Roaming for drones/crates/cubes (v14) is what hurts, not fetching a laser/lightning/mortar.

**Confirmed by v19 (Sat 1:58 AM):** remembering weapons we saw and fetching one when a slot is empty gave +0.19.
Weapon acquisition is our strongest lever so far.

**Refined by v25 + ablations (Sat 6:19 AM):** only *nearby* weapon pickups pay (v19: remembered pickups within the usual
160/90 m). Long walks don't: seeking the first laser up to 240 m cost ~0.23 (v25b). Empty slots don't either: refusing mortars,
which leaves a slot empty, cost ~0.15 (v25c). Any second weapon beats none.

**Learned from v24 + ablations (Sat 5:16 AM):** **dodging inside fights pays**: the bullet sidestep is worth about +0.50
(v24 4.31 -> 3.81 without it), our largest single gain. **Passive hiding/healing costs**: the heal mode (no farming,
hide in cover or stand still while hurt) is worth about -0.19 (4.31 -> 4.50 without it), because the hunters always know
where we are, so standing still does not keep us hidden. Keep-gun barely fires (4 blocked swaps in 16 sim matches): treat it
as neutral. The sim predicted the dodge would hurt (more die-first, earlier deaths); it was wrong again.
So "exposure" is about *roaming and being seen in the open*, not about moving inside a fight: active evasion during a fight is good.
**v28 (Sat 1:40 PM): porting a top team's *combat core* (+0.59) beat porting its tuning tweaks (v27r, -0.08).** The top-10 bots
mostly run giddygiddyboy's MIT Go bot (6.19); another team's Python port of its core scored ~5.0-5.2, matching our 5.13.

**Bullet dodge (v24b, +0.29 vs v19) was the strongest single lever before v28.** Extending it to laser charges (v25 laser dodge) added nothing.

**Rule of thumb:** win the fight you're in quickly, then stay out of sight and don't roam. Don't roam, don't make noise,
don't start optional fights. Gunfire is heard 320 m away, and being seen by one squad bot tips off the hunters.

## Things that look good but aren't (don't repeat without new evidence)
- **More cubes via farming** (v14): +50% cubes in the sim, -0.23 officially. Exposure outweighs the stats.
- **Long range** (v7): we out-shoot house bots at range (live feed: their experts hit 36% at 120-160 m, ours
  ~94%), yet it lost 0.77, because backpedalling exposes us to the rest of the squad.
- **Faster strafing** (v12): a full reversal takes ~0.4 s (58.5 m/s^2), so reversing every 0.35-1.05 s mostly
  jitters in place, which is easy to lead.
- **Weapon-rank tweaks** (v13, not submitted): `WEAPON_RANK` mainly controls *swaps*. Setting gun=0 made us
  trade the gun for a mortar. Check `loadout_gain()` effects before changing ranks.
- **Passive heal / holding still to heal** (v5/v9 in the sim, v24 officially): removed the recovery "leak", but the
  sim got worse where it triggered, and officially v24's heal mode cost about -0.19 (v24 4.31 vs v24b 4.50 without it).
  The hunters always know where we are, so hiding to regen doesn't hide us.
- **Far weapon seeking** (v21 idea, tested in v25): seeking the first laser up to 240 m (also as a swap) cost ~0.23.
  Long walks across the map expose us. Keep the v19 limits (160 m with an empty slot, 90 m to swap).
- **Refusing mortars** (v20 idea, tested in v25): never taking a mortar cost ~0.15, despite the laser cook-off risk.
  A mortar in the slot beats an empty slot.
- **Laser dodge** (v25): sidestepping any mech charging a laser at us had no effect (+0.08 when removed, noise). The existing
  strafe already dodges a charging target, so the extra cases are rare or don't matter.

## Testing tools: what each one can and can't tell you
| Tool | Good for | Not good for |
|---|---|---|
| Official submission | **The only real test of practice score** (deterministic, ±0.1) | per-match detail |
| `tools/precheck.sh` + CI | crashes, timing, Docker sandbox, conformance | strategy |
| `tools/replay.py` (recorded stream) | decision traces and timing; it doesn't react to us | outcomes |
| scenario scripts (see the skill) | does a specific decision change as intended? | outcomes |
| `tools/sim.py` | **mechanism checks only** (did cubes/kills/trigger counts move?) | **predicting scores. It ranked v7 highest (officially worst) under two calibrations** |
| `tools/live_browser.js` | real engine, free-for-all vs house bots (v3 won 6 of 9 live FFA matches) | the practice squad |

Measured real house-bot gun accuracy (spectator feed, 5 live matches): experts 90% <40 m, 70% 40-80 m,
61% 80-120 m, 36% 120-160 m, 10% beyond; our bot 62-94% across 40-160 m.

## Ideas not yet tested (rank by "reduces exposure")
1. ~~v15 quiet~~: tested, no effect (3.85).
2. ~~Stay put when idle~~: tested as v16, 4.02 (+0.10). Was: v10 still walks toward a zone hold point and up to 160 m for weapons when idle.
   Holding near cover until the zone forces a move would cut exposure further.
3. **Pick idle spots that are hard to see** (few long sightlines), not just the nearest cover.
4. ~~Recovery that doesn't leak~~: tested as v24's heal mode, about -0.19. Rejected.

## Outside sources
- Wolverines / TTUN bot (MIT): [varchaskukreja/TTUN](https://github.com/varchaskukreja/TTUN). v10's thresholds
  came from here. Their farming and strafe timing did **not** transfer to our bot.
- jklein07 (MIT): house-bot behaviour notes and the play-server room protocol our live harness uses.
- Credits for anything adapted are in `CREDITS.md`.
