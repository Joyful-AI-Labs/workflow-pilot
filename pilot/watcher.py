"""Poll the inbox folder and feed new PDFs to the pipeline.

ponytail: 2-second polling on one thread plus a 4-worker pool for extraction (LLM calls take a few seconds each).
Swap the poller for watchfiles / an S3 or email trigger when volume justifies it.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import config, db, pipeline

WORKERS = 4


def _loop(stop: threading.Event) -> None:
    config.INBOX.mkdir(parents=True, exist_ok=True)
    in_flight: set[str] = set()
    with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="pilot") as pool:
        while not stop.is_set():
            seen = db.known_files() | in_flight
            for pdf in sorted(config.INBOX.glob("*.pdf")):
                if pdf.name in seen:
                    continue
                size = pdf.stat().st_size  # skip files still being written
                time.sleep(0.2)
                if pdf.stat().st_size != size:
                    continue
                in_flight.add(pdf.name)
                invoice_id = db.add_invoice(pdf.name)  # row appears in the queue immediately
                pool.submit(_run, pdf, invoice_id, in_flight)
            stop.wait(2)


def _run(pdf, invoice_id: int, in_flight: set[str]) -> None:
    try:
        pipeline.process_file(pdf, invoice_id)
    finally:
        in_flight.discard(pdf.name)


def start() -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=_loop, args=(stop,), daemon=True, name="inbox-watcher").start()
    return stop
