# Mech Royale bot. Scorer builds on linux/amd64 with network on; runs with no network, read-only
# root (writable /tmp), 1 CPU, 512 MB, uid 65534, map mounted at /arena.
FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# system-wide install (the bot runs as an unprivileged user)
RUN pip install numpy==2.3.5 scipy==1.16.3
WORKDIR /bot
COPY . .
# precompute world grids + nav graph into /bot/cache, precompile bytecode, make readable by uid 65534
RUN python3 build_cache.py arena && python3 -m compileall -q /bot && chmod -R a+rX /bot
ENTRYPOINT ["python3", "-u", "/bot/bot.py"]
