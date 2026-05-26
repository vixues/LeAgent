#!/usr/bin/env python3
"""Lightweight LeAgent performance benchmark harness.

Targets a running backend and measures chat streaming latency under load:
request upload, time to first SSE event, total stream time, and success rate.
It intentionally uses only stdlib modules so it can run from any checkout.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4


@dataclass
class Sample:
    scenario: str
    ok: bool
    status: int
    first_event_ms: float
    total_ms: float
    bytes_read: int
    error: str = ""


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[index]


def _summarize(samples: list[Sample]) -> dict[str, Any]:
    ok = [s for s in samples if s.ok]
    first = [s.first_event_ms for s in ok]
    total = [s.total_ms for s in ok]
    return {
        "requests": len(samples),
        "success": len(ok),
        "error": len(samples) - len(ok),
        "success_rate": len(ok) / len(samples) if samples else 0.0,
        "first_event_ms": {
            "p50": statistics.median(first) if first else 0.0,
            "p95": _percentile(first, 95),
            "p99": _percentile(first, 99),
        },
        "total_ms": {
            "p50": statistics.median(total) if total else 0.0,
            "p95": _percentile(total, 95),
            "p99": _percentile(total, 99),
        },
    }


def _encode_multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----leagent-perf-{uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        if value == "":
            continue
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def _read_stream(
    *,
    url: str,
    message: str,
    session_id: str,
    timeout: float,
    slow_consumer_ms: int,
) -> Sample:
    body, content_type = _encode_multipart({"message": message, "session_id": session_id})
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "Accept": "text/event-stream",
        },
    )
    started = time.perf_counter()
    first_event_at: float | None = None
    bytes_read = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            while True:
                line = response.readline()
                if not line:
                    break
                bytes_read += len(line)
                if first_event_at is None and line.strip():
                    first_event_at = time.perf_counter()
                if slow_consumer_ms > 0:
                    time.sleep(slow_consumer_ms / 1000)
        total = time.perf_counter() - started
        return Sample(
            scenario="chat_stream",
            ok=200 <= status < 300,
            status=status,
            first_event_ms=((first_event_at or time.perf_counter()) - started) * 1000,
            total_ms=total * 1000,
            bytes_read=bytes_read,
        )
    except urllib.error.HTTPError as exc:
        total = time.perf_counter() - started
        return Sample(
            scenario="chat_stream",
            ok=False,
            status=exc.code,
            first_event_ms=0.0,
            total_ms=total * 1000,
            bytes_read=bytes_read,
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        total = time.perf_counter() - started
        return Sample(
            scenario="chat_stream",
            ok=False,
            status=0,
            first_event_ms=0.0,
            total_ms=total * 1000,
            bytes_read=bytes_read,
            error=str(exc),
        )


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    stream_url = urllib.parse.urljoin(args.base_url.rstrip("/") + "/", "chat/stream")
    semaphore = asyncio.Semaphore(args.concurrency)
    samples: list[Sample] = []

    async def one(index: int) -> None:
        async with semaphore:
            # Empty session_id lets the API create an owned ChatSession with the
            # authenticated local user. Sending an arbitrary UUID makes the
            # stream succeed but later DB persistence can fail FK/NOT NULL checks.
            session_id = "" if args.new_session_per_request else args.session_id
            sample = await asyncio.to_thread(
                _read_stream,
                url=stream_url,
                message=args.message.format(i=index),
                session_id=session_id,
                timeout=args.timeout,
                slow_consumer_ms=args.slow_consumer_ms,
            )
            samples.append(sample)

    started = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(args.requests)))
    elapsed = time.perf_counter() - started
    return {
        "config": {
            "base_url": args.base_url,
            "requests": args.requests,
            "concurrency": args.concurrency,
            "slow_consumer_ms": args.slow_consumer_ms,
            "new_session_per_request": args.new_session_per_request,
        },
        "elapsed_ms": elapsed * 1000,
        "summary": _summarize(samples),
        "samples": [asdict(s) for s in samples],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LeAgent chat stream benchmarks.")
    parser.add_argument("--base-url", default="http://localhost:7860/api/v1")
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--slow-consumer-ms", type=int, default=0)
    parser.add_argument(
        "--session-id",
        default="",
        help=(
            "Existing chat session UUID. Omit to let the API create a valid "
            "owned session for each request."
        ),
    )
    parser.add_argument("--new-session-per-request", action="store_true")
    parser.add_argument(
        "--message",
        default="Perf smoke request {i}: answer with one short sentence.",
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    result = asyncio.run(_run(args))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.write("\n")


if __name__ == "__main__":
    main()
