"""HTTP/2 transport on one event-loop thread, driven by the bounded queue."""

import asyncio

import httpx
from narinfo import (
    CACHE_HOST,
    RETRIES,
    TIMEOUT_SECONDS,
    USER_AGENT,
    parse_narinfo,
)


class AsyncPool:
    async def start(self):
        self.metrics = {"attempts": 0, "retries": 0, "transportErrors": 0}
        self.client = httpx.AsyncClient(
            http2=True,
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "Cache-Control": "max-age=3600"},
        )

    async def fetch(self, digest):
        for attempt in range(RETRIES):
            self.metrics["attempts"] += 1
            self.metrics["retries"] += int(attempt > 0)
            try:
                response = await self.client.get(
                    f"https://{CACHE_HOST}/{digest}.narinfo"
                )
                if response.status_code == 200:
                    record = parse_narinfo(response.text)
                    record.update(d=digest, ok=True)
                    return record
                if response.status_code == 404:
                    return {"d": digest, "ok": False}
            except Exception:
                self.metrics["transportErrors"] += 1
            await asyncio.sleep(0.5 * (attempt + 1))
        return {"d": digest, "ok": False, "err": True}
