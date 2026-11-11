#!/usr/bin/env python3
"""Paced, explicitly asserted rate-limit checks against a local/staging API."""

from __future__ import annotations

import argparse
import asyncio
import math
import json
import os
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass

import httpx


MAX_REQUESTS = 5_000
MAX_CONCURRENCY = 50


@dataclass
class Result:
    status: int
    elapsed_ms: float
    retry_after: str | None
    error: str | None = None


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--endpoint", default="/locations/regions")
    parser.add_argument("--method", default="GET", choices=("GET", "POST", "PUT", "PATCH", "DELETE"))
    parser.add_argument("--count", type=int, default=90)
    parser.add_argument("--duration", type=float, default=40.0, help="Target pacing duration in seconds")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--mode", choices=("general", "login", "endpoint"), default="general")
    parser.add_argument("--token-env", default="RATE_LIMIT_TEST_TOKEN")
    parser.add_argument("--expected-allowed", type=int, required=True)
    parser.add_argument("--expected-429", type=int, required=True)
    parser.add_argument("--expected-auth-failures", type=int, default=0)
    parser.add_argument("--json-body", help="JSON request body for non-login endpoint testing")
    parser.add_argument("--origin", default="http://localhost:5173")
    return parser.parse_args()


def validate(args: argparse.Namespace) -> tuple[str, dict | None]:
    if not args.endpoint.startswith("/"):
        raise ValueError("--endpoint must be an absolute API path beginning with '/'")
    if not 1 <= args.count <= MAX_REQUESTS:
        raise ValueError(f"--count must be between 1 and {MAX_REQUESTS}")
    if not 0 < args.duration <= 3600:
        raise ValueError("--duration must be greater than 0 and no more than 3600 seconds")
    if not 1 <= args.concurrency <= MAX_CONCURRENCY:
        raise ValueError(f"--concurrency must be between 1 and {MAX_CONCURRENCY}")
    if not 0 <= args.expected_allowed <= args.count:
        raise ValueError("--expected-allowed must be between 0 and --count")
    if not 0 <= args.expected_429 <= args.count:
        raise ValueError("--expected-429 must be between 0 and --count")
    if not 0 <= args.expected_auth_failures <= args.count:
        raise ValueError("--expected-auth-failures must be between 0 and --count")
    if args.expected_allowed + args.expected_429 + args.expected_auth_failures > args.count:
        raise ValueError("expected response counts cannot exceed --count")

    headers = {"Accept": "application/json"}
    body = json.loads(args.json_body) if args.json_body else None
    if args.mode == "login":
        email = os.getenv("RATE_LIMIT_TEST_EMAIL")
        password = os.getenv("RATE_LIMIT_TEST_BAD_PASSWORD")
        if not email or not password:
            raise ValueError("Login mode requires RATE_LIMIT_TEST_EMAIL and RATE_LIMIT_TEST_BAD_PASSWORD environment variables")
        if args.method != "POST" or args.endpoint != "/users/login":
            raise ValueError("Login mode requires --method POST --endpoint /users/login")
        headers.update({"Origin": args.origin, "X-CSRF-Token": "1"})
        body = {"email": email, "password": password}
    else:
        token = os.getenv(args.token_env)
        if not token:
            raise ValueError(f"No token found in environment variable {args.token_env}")
        headers["Authorization"] = f"Bearer {token}"
        if args.mode == "endpoint" and body is None and args.method in {"POST", "PUT", "PATCH"}:
            raise ValueError("Write endpoint tests require --json-body")
    return args.base_url.rstrip("/"), (headers, body)


async def run(args: argparse.Namespace) -> int:
    try:
        base_url, request_data = validate(args)
    except (ValueError, json.JSONDecodeError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    headers, body = request_data
    gate = asyncio.Semaphore(args.concurrency)
    results: list[Result] = []
    start = time.perf_counter()

    async with httpx.AsyncClient(base_url=base_url, timeout=15.0, follow_redirects=False) as client:
        async def send(index: int) -> None:
            scheduled = start + (args.duration * index / args.count)
            await asyncio.sleep(max(0.0, scheduled - time.perf_counter()))
            async with gate:
                request_start = time.perf_counter()
                try:
                    response = await client.request(
                        args.method,
                        args.endpoint,
                        headers=headers,
                        json=body,
                    )
                    results.append(Result(
                        response.status_code,
                        (time.perf_counter() - request_start) * 1000,
                        response.headers.get("Retry-After"),
                    ))
                except httpx.HTTPError as error:
                    results.append(Result(0, (time.perf_counter() - request_start) * 1000, None, type(error).__name__))

        await asyncio.gather(*(send(index) for index in range(args.count)))

    duration = time.perf_counter() - start
    statuses = Counter(result.status for result in results)
    successful = sum(count for code, count in statuses.items() if 200 <= code < 300)
    auth_failures = statuses[401]
    limited = statuses[429]
    other = len(results) - successful - auth_failures - limited
    latencies = sorted(result.elapsed_ms for result in results)
    average = statistics.fmean(latencies) if latencies else 0.0
    p95 = latencies[min(len(latencies) - 1, max(0, math.ceil(0.95 * len(latencies)) - 1))] if latencies else 0.0
    retry_values = [result.retry_after for result in results if result.status == 429 and result.retry_after]
    invalid_retry_after = any(
        result.status == 429
        and (not result.retry_after or not result.retry_after.isdigit() or int(result.retry_after) < 1)
        for result in results
    )

    print("RATE LIMIT TEST RESULTS")
    print(f"Target endpoint: {args.endpoint}")
    print(f"Total requests: {len(results)}")
    print(f"Successful responses: {successful}")
    print(f"Authentication failures: {auth_failures}")
    print(f"Rate limited (429): {limited}")
    print(f"Other responses: {other}")
    print(f"HTTP status counts: {dict(sorted(statuses.items()))}")
    print(f"Average response time: {average:.1f} ms")
    print(f"95th percentile response time: {p95:.1f} ms")
    print(f"Test duration: {duration:.2f} seconds (target pacing: {args.duration:.2f} seconds)")
    print(f"Retry-After values: {', '.join(retry_values) if retry_values else 'none'}")

    network_errors = sum(result.status == 0 for result in results)
    passed = (
        successful == args.expected_allowed
        and auth_failures == args.expected_auth_failures
        and limited == args.expected_429
        and other == 0
        and network_errors == 0
        and not invalid_retry_after
    )
    print(f"Result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(arguments())))
