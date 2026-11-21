#!/usr/bin/env bash
# Pre-push / pre-submit checks. Exit non-zero (and block the push) if anything is wrong.
# Usage: tools/precheck.sh            (full)    QUICK=1 tools/precheck.sh   (skip the crash scan)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
fail() { echo "PRECHECK FAILED: $*" >&2; exit 1; }
echo "== 1. python compiles"
python3 -m py_compile bot.py world.py nav.py mechfight.py build_cache.py || fail "syntax error"
echo "== 2. Dockerfile sanity (pinned versions, entrypoint)"
grep -qE '^FROM python:3\.13-slim-bookworm' Dockerfile || fail "base image changed/unpinned"
grep -qE 'numpy==[0-9.]+' Dockerfile && grep -qE 'scipy==[0-9.]+' Dockerfile || fail "numpy/scipy not pinned"
grep -q 'ENTRYPOINT \["python3", "-u", "/bot/bot.py"\]' Dockerfile || fail "entrypoint changed"
echo "== 3. nothing that must not be committed"
if git ls-files | grep -qE '^cache/|\.env$|credentials|\.pem$'; then fail "cache/ or secrets are tracked"; fi
SIZE=$(git ls-files -z | xargs -0 du -cb 2>/dev/null | tail -1 | cut -f1)
[ "$SIZE" -lt 18000000 ] || fail "tracked files are ${SIZE} bytes (limit 20 MB)"
echo "== 4. no stray prints to stdout in bot code"
if grep -nE '^\s*print\(' bot.py world.py nav.py | grep -v 'file=sys.stderr'; then fail "print() to stdout in bot code"; fi
echo "== 5. cache + conformance check (must PASS, p99 < 15 ms)"
[ -f cache/nav.npz ] && [ cache/nav.npz -nt nav.py ] && [ cache/world.npz -nt world.py ] || python3 build_cache.py arena
OUT=$(cd check && python3 check.py -- python3 -u ../bot.py 2>&1) || { echo "$OUT" | tail -15; fail "check.py failed"; }
echo "$OUT" | tail -4
echo "$OUT" | grep -q '^PASS' || fail "check.py did not PASS"
P99=$(echo "$OUT" | sed -n 's/.*p99 \([0-9.]*\).*/\1/p' | head -1)
python3 -c "import sys; sys.exit(0 if float('${P99:-999}') < 15 else 1)" || fail "p99 ${P99} ms >= 15 ms"
if [ -z "${QUICK:-}" ]; then
  echo "== 6. crash scan (full sim match, bot.act must never raise)"
  ERR=$(python3 tools/errscan.py 7 2>/dev/null | sed -n 's/errors total //p')
  [ "${ERR:-1}" = "0" ] || fail "bot raised ${ERR} exceptions in the sim (run: python3 tools/errscan.py 7)"
fi
echo "ALL PRECHECKS PASSED"
