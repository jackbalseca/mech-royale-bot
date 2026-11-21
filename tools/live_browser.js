// Live test harness: runs our bot IN THE BROWSER against the real game server's bots.
//
// Why: the scorer only gives one number per submission, and our sim is approximate. The public
// play server (https://play.joinbuilders.org) runs private rooms whose empty seats are the
// server's own bots (h*-easy/medium/hard/expert house bots + others), on the real engine.
// The room protocol follows jklein07/mech-royale-bot tools/live.py (MIT); this JS port is ours.
//
// How to use (works with any browser, no install):
//   1. Open https://play.joinbuilders.org/ and open the DevTools console.
//   2. Paste this whole file, press Enter. It loads Pyodide (Python in WebAssembly) with
//      numpy + scipy, then fetches our bot from GitHub at the given ref and builds its cache.
//   3. await H.setup();                    // once per page load (~30 s)
//      await H.loadBot("main");            // or a 40-char commit hash
//      const r = await H.runMatch("main", "Vexe-test");   // plays one real-time match
//      r.place, r.kills, r.trace           // results; H.results keeps every match
//   Notes: matches run in real time (up to ~8 min; ends early when we die). These private rooms
//   are FREE-FOR-ALL against the house bots, not the practice squad, so they test qualifying /
//   final play. Keep the tab in the foreground-ish: background tabs throttle timers.

window.H = window.H || { log: [], results: [], status: "init" };

H.setup = async () => {
  if (!window.loadPyodide) {
    await new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js";
      s.onload = res; s.onerror = rej; document.head.appendChild(s);
    });
  }
  H.py = await loadPyodide({ indexURL: "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/" });
  await H.py.loadPackage(["numpy", "scipy"]);
  await H.py.runPythonAsync(`
import json, time
BOTS = {}
CLASSES = {}
def new_bot(key, ref, hello_json):
    cls, mf = CLASSES[ref]
    h = json.loads(hello_json)
    h["map"]["dir"] = "/bots/" + ref + "/arena"
    BOTS[key] = (cls(h), mf, {"lbl": ""})
    return "ok"
def bot_act(key, obs_json):
    b, mf, st = BOTS[key]
    o = json.loads(obs_json)
    mf.draw.clear()
    t0 = time.perf_counter()
    try:
        a = dict(b.act(o) or {})
    except Exception as e:
        a = {"move": [0, 0]}
        st["err"] = repr(e)
    d = mf.draw.take() or {}
    st["lbl"] = d.get("label", "")
    a["tick"] = o["tick"]
    a.pop("debug", None)
    return json.dumps({"a": a, "lbl": st["lbl"], "ms": (time.perf_counter() - t0) * 1000})
`);
  H.status = "ready";
};

H.loadBot = async (ref) => {
  const py = H.py;
  const base = "https://raw.githubusercontent.com/jackbalseca/mech-royale-bot/" + ref + "/";
  const dir = "/bots/" + ref;
  py.FS.mkdirTree(dir + "/arena/v2"); py.FS.mkdirTree(dir + "/cache");
  for (const f of ["bot.py", "world.py", "nav.py", "mechfight.py", "build_cache.py"]) {
    const r = await fetch(base + f); if (!r.ok) throw new Error(f + " " + r.status);
    py.FS.writeFile(dir + "/" + f, await r.text());
  }
  if (!H.arena) {
    H.arena = {};
    for (const f of ["world.json", "terrain.i16"]) {
      const r = await fetch(base + "arena/v2/" + f);
      H.arena[f] = new Uint8Array(await r.arrayBuffer());
    }
  }
  for (const f in H.arena) py.FS.writeFile(dir + "/arena/v2/" + f, H.arena[f]);
  const t0 = performance.now();
  await py.runPythonAsync(`
import sys, os
d = ${JSON.stringify(dir)}
for m in ["bot", "world", "nav", "mechfight", "build_cache"]:
    sys.modules.pop(m, None)
sys.path.insert(0, d)
if not os.path.exists(d + "/cache/nav.npz"):
    os.chdir(d)
    import build_cache
import mechfight as mf, bot as B
sys.path.remove(d)
CLASSES[${JSON.stringify(ref)}] = (B.Bot, mf)
`);
  return (performance.now() - t0) / 1000;
};

H.runMatch = (ref, name) => new Promise(async (resolve) => {
  const py = H.py;
  const hex = n => Array.from(crypto.getRandomValues(new Uint8Array(n))).map(b => b.toString(16).padStart(2, "0")).join("");
  const sid = hex(16);
  const info = await (await fetch("/mm/code/new?sid=" + sid)).json();
  const key = ref + ":" + info.code;
  const rec = { ref, code: info.code, room: info.room, start: Date.now(), place: null, kills: null, trace: [], ms: [], first: {} };
  H.results.push(rec);
  const ws = new WebSocket(`wss://${location.host}/r/${info.room}/play?token=&sid=${sid}&name=${encodeURIComponent(name)}&code=${info.code}`);
  let started = false;
  const done = () => { if (rec.end) return; rec.end = Date.now(); try { ws.close(); } catch (e) {} resolve(rec); };
  const act = py.globals.get("bot_act"), nb = py.globals.get("new_bot");
  ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    const ty = m.type;
    if (ty !== "obs" && !rec.first[ty]) rec.first[ty] = JSON.stringify(m).slice(0, 1500);
    if (ty === "lobby") {
      if (!m.you || !m.you.ready) ws.send(JSON.stringify({ type: "ready", name }));
      if (m.you && m.you.host && m.phase === "waiting" && !started) { started = true; setTimeout(() => ws.send(JSON.stringify({ type: "start" })), 800); }
    } else if (ty === "hello") {
      nb(key, ref, ev.data); ws.send(JSON.stringify({ type: "loaded" })); rec.slot = m.slot;
    } else if (ty === "obs") {
      const out = JSON.parse(act(key, ev.data));
      ws.send(JSON.stringify(out.a));
      rec.ms.push(out.ms);
      const s = m.self;
      const dmg = (m.events || []).filter(e => e.type === "damaged").map(e => [e.by, Math.round(e.amount), e.weapon]);
      const kills = (m.events || []).filter(e => e.type === "kill").length;
      if (m.tick % 20 === 0 || dmg.length || kills) rec.trace.push([m.t, Math.round(s.hp), m.alive, out.lbl, (m.mechs || []).filter(x => x.kind === "mech").map(x => x.id), dmg, kills]);
      rec.lastT = m.t; rec.alive = m.alive;
    } else if (ty === "end") {
      rec.place = m.place; rec.kills = m.kills; done();
    }
  };
  ws.onclose = () => done();
  ws.onerror = () => { rec.err = "ws error"; done(); };
  setTimeout(done, 9 * 60 * 1000);
});

// Summary of all live matches by bot ref: mean points (16 - place), kills, death time.
H.summary = () => {
  const by = {};
  for (const r of H.results) {
    if (r.place == null) continue;
    const g = by[r.ref] = by[r.ref] || { n: 0, pts: 0, kills: 0, zero: 0 };
    g.n++; g.pts += 16 - r.place; g.kills += r.kills || 0; if (r.place === 16) g.zero++;
  }
  for (const k in by) { by[k].mean = +(by[k].pts / by[k].n).toFixed(2); }
  return by;
};

// ---------------------------------------------------------------------------------------------
// Spectator-feed recorder: measures REAL house-bot accuracy by tier and distance on the real
// engine, to calibrate tools/house.py. Feed format (mechreplay/1) and the shot->target matching
// idea follow jklein07/mech-royale-bot tools/feed.py + aimstats.py (MIT); this JS is ours.
//   m = [id, x, y, z, yaw, ...] per mech per frame;  ev: {e:"fire", id, w}, {e:"hit", src, dst, w, amt}
H.aim = H.aim || {};          // key "tier|weapon|bucket" -> {fire, hit}
H.feeds = H.feeds || 0;
H.spectate = (room, code) => {
  const hex = n => Array.from(crypto.getRandomValues(new Uint8Array(n))).map(b => b.toString(16).padStart(2, "0")).join("");
  const ws = new WebSocket(`wss://${location.host}/r/${room}/live?token=&code=${code}&sid=${hex(16)}`);
  let hdr = null; const pending = {}; const tierOf = {};
  const bucket = d => d < 40 ? "000-040" : d < 80 ? "040-080" : d < 120 ? "080-120" : d < 160 ? "120-160" : "160-260";
  const bump = (k, f) => { const o = H.aim[k] = H.aim[k] || { fire: 0, hit: 0 }; o[f]++; };
  ws.onmessage = (ev) => {
    for (const line of String(ev.data).split("\n")) {
      if (!line.trim()) continue;
      let x; try { x = JSON.parse(line); } catch (e) { continue; }
      if (x.type === "header") {
        hdr = x; H.feeds++;
        for (const m of x.mechs) { const nm = m.name || ""; const b = (x.bots && x.bots[m.id]) || ""; tierOf[m.id] = (nm.match(/(easy|medium|hard|expert)/) || b.match(/(easy|medium|hard|expert)/) || ["", nm.startsWith("Vexe") ? "ours" : "other"])[1]; }
        continue;
      }
      if (!hdr || !x.m) continue;
      const cur = {}; for (const m of x.m) cur[m[0]] = m;
      for (const e of (x.ev || [])) {
        if (e.e === "fire" && (e.w === "gun" || e.w === "laser") && cur[e.id]) {
          const s = cur[e.id]; let best = null;
          for (const id in cur) { const m = cur[id]; if (m[0] === s[0]) continue;
            const dx = m[1] - s[1], dy = m[2] - s[2], d = Math.hypot(dx, dy); if (d < 1 || d > 280) continue;
            const ang = Math.abs(((Math.atan2(dy, dx) - s[4] + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI);
            if (ang < 0.08 && (!best || d < best[1])) best = [m[0], d]; }
          if (best) { const k = `${tierOf[s[0]] || "?"}|${e.w}|${bucket(best[1])}`; bump(k, "fire"); (pending[s[0]] = pending[s[0]] || []).push([best[0], k, x.t]); }
        }
        if (e.e === "hit" && (e.w === "gun" || e.w === "laser") && e.dst != null && e.dst < 16 && pending[e.src]) {
          const lst = pending[e.src]; const i = lst.findIndex(p => p[0] === e.dst);
          if (i >= 0) { bump(lst[i][1], "hit"); lst.splice(i, 1); }
        }
      }
    }
  };
  return ws;
};
H.aimTable = () => Object.keys(H.aim).sort().map(k => `${k}: ${H.aim[k].hit}/${H.aim[k].fire} = ${(H.aim[k].hit / Math.max(1, H.aim[k].fire)).toFixed(2)}`).join("\n");
// play matches with the spectator recorder attached (same as runMatch, plus H.spectate on the same room)
H.runMatchSpec = async (ref, name) => {
  const origFetch = window.fetch;
  let roomInfo = null;
  window.fetch = async (...a) => { const r = await origFetch(...a); if (String(a[0]).startsWith("/mm/code/new")) { const c = r.clone(); roomInfo = await c.json(); } return r; };
  const p = H.runMatch(ref, name);
  while (!roomInfo) await new Promise(r => setTimeout(r, 50));
  window.fetch = origFetch;
  const ws = H.spectate(roomInfo.room, roomInfo.code);
  const rec = await p; try { ws.close(); } catch (e) {}
  return rec;
};
