#!/usr/bin/env python3
import asyncio
import importlib.util
from pathlib import Path
import sys
import httpx

spec = importlib.util.spec_from_file_location("census", Path(sys.argv[1]) / "census.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.RETRY_BACKOFF_SECONDS = 0


async def test():
    calls = {}

    def respond(request):
        key = (request.method, request.url.path)
        calls[key] = calls.get(key, 0) + 1
        path = request.url.path
        if path == "/absent.narinfo" or path == "/nar/missing":
            return httpx.Response(404)
        if path == "/nar/error":
            raise httpx.ReadTimeout("test")
        if path == "/nar/retry" and calls[key] == 1:
            return httpx.Response(503)
        if request.method == "GET":
            name = path[1:].removesuffix(".narinfo")
            body = "invalid" if name == "malformed" else f"URL: nar/{name}\n"
            return httpx.Response(200, text=body)
        return httpx.Response(200)

    async with httpx.AsyncClient(
        base_url="https://cache.nixos.org", transport=httpx.MockTransport(respond)
    ) as client:
        c = m.Census(client)
        rows = await asyncio.gather(
            *(
                c.check(n)
                for n in ("ok", "absent", "missing", "error", "retry", "malformed")
            )
        )
    by = {r["d"]: r for r in rows}
    assert by["ok"]["nar"] and by["retry"]["nar"]
    assert not by["absent"]["narinfo"] and not by["absent"]["err"]
    assert not by["missing"]["nar"] and not by["missing"]["err"]
    assert by["error"]["err"] and by["malformed"]["err"]
    assert calls[("HEAD", "/nar/error")] == 3
    assert calls[("HEAD", "/nar/retry")] == 2
    assert all(method in {"GET", "HEAD"} for method, _ in calls)
    assert not any(
        method == "GET" and path.startswith("/nar/") for method, path in calls
    )


asyncio.run(test())
print(
    "Census: async probes, HEAD only for payloads, retries, unknown versus missing: OK"
)
