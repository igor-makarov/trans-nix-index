"""Shared narinfo transport: thread-local keepalive, bounded retries, GET metadata."""

import http.client
import threading
import time

CACHE_HOST = "cache.nixos.org"
USER_AGENT = "nixpkgs-multiverse"
RETRIES = 3
TIMEOUT_SECONDS = 30
DIGEST_LEN = 32
_local = threading.local()


def reset_connection():
    conn = getattr(_local, "conn", None)
    if conn:
        conn.close()
    _local.conn = None


def get_connection():
    if getattr(_local, "conn", None) is None:
        _local.conn = http.client.HTTPSConnection(CACHE_HOST, timeout=TIMEOUT_SECONDS)
    return _local.conn


def parse_narinfo(text):
    out = {}
    for line in text.splitlines():
        k, _, v = line.partition(": ")
        out[k] = v
    refs = [base[:DIGEST_LEN] for base in out.get("References", "").split()]
    sp = out.get("StorePath", "")
    name = (
        sp[len("/nix/store/") + DIGEST_LEN + 1 :]
        if sp.startswith("/nix/store/")
        else None
    )
    return {
        "name": name,
        "ns": int(out["NarSize"]) if out.get("NarSize") else None,
        "fs": int(out["FileSize"]) if out.get("FileSize") else None,
        "url": out.get("URL"),
        "refs": refs,
    }


def fetch(digest):
    for attempt in range(RETRIES):
        try:
            conn = get_connection()
            conn.request(
                "GET", f"/{digest}.narinfo", headers={"User-Agent": USER_AGENT}
            )
            r = conn.getresponse()
            body = r.read()
            if r.status == 200:
                rec = parse_narinfo(body.decode())
                rec.update(d=digest, ok=True)
                return rec
            if r.status == 404:
                return {"d": digest, "ok": False}
            # transient (429/5xx): retry on a fresh connection
            reset_connection()
        except Exception:
            reset_connection()
        time.sleep(0.5 * (attempt + 1))
    return {"d": digest, "ok": False, "err": True}
