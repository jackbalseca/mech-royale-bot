# Credits

All bot code in this repo (`bot.py`, `world.py`, `nav.py`, `build_cache.py`) is our own.

- `mechfight.py`, `protocol.md`, `mechfight.schema.json`, `check/` and `arena/` come from the
  organizers' `mechfight-kit`.
- `tools/house.py` (stand-in house bots for the local sim, not part of the bot image) is our own
  code. Its behaviour parameters (tier aim error, reaction times, passive non-hunters, poor
  laser accuracy) come from public notes in
  [jklein07/mech-royale-bot](https://github.com/jklein07/mech-royale-bot) (MIT License,
  Copyright (c) 2026 jklein07). No code was copied.
- `bot.py` v10+ fight-commitment thresholds ("losing" / "finishing" rules for when to break off a fight) are
  adapted from the Wolverines team's bot, [varchaskukreja/TTUN](https://github.com/varchaskukreja/TTUN)
  `mech-royale/bot/bot.ts` (MIT License, Copyright (c) 2026 TTUN). Rewritten in Python for our code; no file copied.
- `bot.py` v14+ active farming (walk into range of remembered NPC drones and nearby crates; HP and distance
  thresholds) is adapted from the same Wolverines/TTUN bot (MIT License). Rewritten in Python; no file copied.
