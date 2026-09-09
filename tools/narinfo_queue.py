"""One bounded HTTP pool for fresh output probes and recursive references."""

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time

from narinfo import fetch, metrics


def load_records(path):
    records = {}
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            try:
                rec = json.loads(line)
                if not rec.get("err"):
                    records[rec["d"]] = rec
            except (ValueError, KeyError):
                continue
    return records


class NarinfoQueue:
    def __init__(self, graph, threads=128, get=fetch):
        if threads < 1:
            raise ValueError("threads must be positive")
        self.graph, self.threads, self.get = graph, threads, get
        self.records = load_records(graph)
        self.requests = {}  # Single-flight futures, including completed 404/errors.
        self.queue, self.done = deque(), deque()
        self.condition = threading.Condition(threading.RLock())
        self.closing = False
        self.error = None
        self.fetched = self.errors = self.peak = 0
        self.started = time.monotonic()
        self.initial_metrics = dict(metrics)
        self.worker = threading.Thread(target=self._run)
        self.worker.start()
        self.seed({d for r in self.records.values() for d in r.get("refs", [])})

    def request(self, digest, fresh=True):
        with self.condition:
            if self.error:
                raise self.error
            if digest in self.requests:
                return self.requests[digest]
            if not fresh and digest in self.records:
                future = Future()
                future.set_result(self.records[digest])
                return future
            future = self.requests[digest] = Future()
            self.queue.append(digest)
            self.condition.notify_all()
            return future

    def seed(self, digests):
        for digest in sorted(digests):
            self.request(digest, fresh=False)

    def _complete(self, digest, future):
        with self.condition:
            self.done.append((digest, future))
            self.condition.notify_all()

    def _run(self):
        active = 0
        try:
            with ThreadPoolExecutor(self.threads) as pool, open(self.graph, "a") as out:
                out.write("\n")
                while True:
                    with self.condition:
                        while self.done:
                            digest, future = self.done.popleft()
                            active -= 1
                            rec = future.result()
                            self.fetched += 1
                            if rec.get("err"):
                                self.errors += 1
                            else:
                                self.records[digest] = rec
                                out.write(json.dumps(rec, separators=(",", ":")) + "\n")
                                self.seed(rec.get("refs", []))
                            self.requests[digest].set_result(rec)
                        out.flush()
                        while self.queue and active < self.threads:
                            digest = self.queue.popleft()
                            future = pool.submit(self.get, digest)
                            active += 1
                            self.peak = max(self.peak, active)
                            future.add_done_callback(
                                lambda f, d=digest: self._complete(d, f)
                            )
                        if self.closing and not active and not self.queue:
                            return
                        if not self.done:
                            self.condition.wait()
        except BaseException as error:
            with self.condition:
                self.error = error
                for future in self.requests.values():
                    if not future.done():
                        future.set_exception(error)
                self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closing = True
            self.condition.notify_all()
        self.worker.join()
        if self.error:
            raise self.error
        result = dict(
            fetched=self.fetched,
            errors=self.errors,
            threads=self.threads,
            peakActive=self.peak,
            elapsedSeconds=round(time.monotonic() - self.started, 3),
        )
        result.update({k: v - self.initial_metrics[k] for k, v in metrics.items()})
        print(json.dumps(result), flush=True)
        return result
