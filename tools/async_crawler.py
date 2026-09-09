"""Single-loop recursive crawler with a synchronous join adapter."""

import asyncio
import json
import threading
import time

from narinfo_async import AsyncPool


class AsyncCrawler:
    def __init__(self, graph, threads=2048, get=None):
        if threads < 1:
            raise ValueError("tasks must be positive")
        self.graph, self.limit = graph, threads
        self.get = get
        self.handles = {}  # Accessed by the synchronous join coordinator only.
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever)
        self.thread.start()
        try:
            self.call(self.start()).result()
        except BaseException:
            try:
                self.call(self.cleanup()).result()
            finally:
                self.stop_loop()
            raise

    def call(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    async def start(self):
        from narinfo_queue import load_records

        self.records = load_records(self.graph)
        self.requests = {}
        self.pending = asyncio.Queue()
        self.transport = AsyncPool()
        self.transport.metrics = {"attempts": 0, "retries": 0, "transportErrors": 0}
        if self.get is None:
            await self.transport.start()
        self.out = open(self.graph, "a")
        self.out.write("\n")
        self.started = time.monotonic()
        self.fetched = self.errors = self.active = self.peak = 0
        self.failure = None
        self.workers = [asyncio.create_task(self.worker()) for _ in range(self.limit)]
        for record in list(self.records.values()):
            for digest in record.get("refs", []):
                self.enqueue(digest, False)

    def enqueue(self, digest, fresh):
        if digest in self.requests:
            return self.requests[digest]
        future = self.loop.create_future()
        if not fresh and digest in self.records:
            future.set_result(self.records[digest])
            return future
        self.requests[digest] = future
        self.pending.put_nowait(digest)
        return future

    async def worker(self):
        while True:
            digest = await self.pending.get()
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                if self.failure:
                    raise self.failure
                record = await (
                    self.get(digest) if self.get else self.transport.fetch(digest)
                )
                self.fetched += 1
                if record.get("err"):
                    self.errors += 1
                else:
                    self.records[digest] = record
                    self.out.write(json.dumps(record, separators=(",", ":")) + "\n")
                    self.out.flush()
                    for child in record.get("refs", []):
                        self.enqueue(child, False)
                self.requests[digest].set_result(record)
            except Exception as error:
                self.failure = error
                self.requests[digest].set_exception(error)
                self.requests[digest].exception()  # Observe dependency-only errors.
            finally:
                self.active -= 1
                self.pending.task_done()

    async def wait_record(self, digest, fresh):
        return await self.enqueue(digest, fresh)

    def request(self, digest, fresh=True):
        if digest not in self.handles:
            self.handles[digest] = self.call(self.wait_record(digest, fresh))
        return self.handles[digest]

    def seed(self, digests):
        async def add():
            for digest in sorted(digests):
                self.enqueue(digest, False)

        self.call(add()).result()

    async def cleanup(self):
        workers = getattr(self, "workers", [])
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        try:
            if hasattr(self, "out"):
                self.out.close()
        finally:
            client = getattr(getattr(self, "transport", None), "client", None)
            if client is not None:
                await client.aclose()

    async def finish(self):
        try:
            await self.pending.join()
        finally:
            await self.cleanup()
        if self.failure:
            raise self.failure
        result = dict(
            fetched=self.fetched,
            errors=self.errors,
            threads=self.limit,
            peakActive=self.peak,
            elapsedSeconds=round(time.monotonic() - self.started, 3),
        )
        result.update(self.transport.metrics)
        print(json.dumps(result), flush=True)
        return result

    def stop_loop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()
        self.loop.close()

    def close(self):
        try:
            return self.call(self.finish()).result()
        finally:
            self.stop_loop()
