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
- `bot.py` v24+ bullet sidestep (from branch exp-agent-ttun) (`Bot.bullet_dodge`: move perpendicular to each incoming bullet's path, away from
  its closest point of approach, and boost) is adapted from the "dodge incoming bullets and shells" block of
  [varchaskukreja/TTUN](https://github.com/varchaskukreja/TTUN) `mech-royale/bot/bot.ts` (branch
  `mech-royale-submit`, MIT License, Copyright (c) 2026 TTUN). Rewritten in Python; no file copied.
