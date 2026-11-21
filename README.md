# mech-royale-bot

Bot for **Mech Royale** (Builders Buildathon). Python 3.13 + numpy/scipy.

| File | What it does |
| --- | --- |
| `bot.py` | Entry point. Targeting, aiming (gun lead, laser charge/release, lightning cone, mortar ballistics), movement (zone > retreat > fight spacing/strafe > loot > farm > supply drop > hold). |
| `world.py` | Map model: terrain + buildings/bridges rasterized to 1 m, line-of-sight raycasts, eroded walk grid. |
| `nav.py` | 8 m waypoint graph + per-goal Dijkstra (cached), path steering with look-ahead. |
| `build_cache.py` | Precomputes `cache/world.npz` + `cache/nav.npz` at image build time. |
| `mechfight.py` | Kit wrapper (stdin/stdout loop, debug drawing). |
| `arena/` | Copy of the map, used only to precompute at build time. |
| `check/` | Kit conformance check + recorded stream. |
| `tools/replay.py` | Feeds the recorded stream through the bot in-process and prints decisions + timings. |

## Test locally

```sh
pip install numpy==2.3.5 scipy==1.16.3
python3 build_cache.py arena
python3 check/check.py -- python3 -u bot.py
python3 tools/replay.py . check/stream.jsonl.gz

# the way the scorer runs it
docker build --platform linux/amd64 -t mech-bot .
python3 check/check.py --map-dir /arena -- docker run --rm -i --platform linux/amd64 --network none --cpus 1 --memory 512m --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 -v "$PWD/arena:/arena:ro" mech-bot
```

## Rules to keep

- Never force-push / rewrite history: the final rebuilds the chosen commit.
- Logs go to stderr only. Write files only under /tmp.
