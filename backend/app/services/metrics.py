"""Tiny dependency-free Prometheus exposition + LLM usage persistence.

Counters are in-process (reset on restart, per worker). These are MEASURED request stats, not SLOs.
"""
from __future__ import annotations

import threading
from collections import defaultdict

from sqlalchemy import func, select

from app.db import session_factory
from app.models import LLMUsage, Task

_lock = threading.Lock()
_requests: dict[tuple[str, str, int], int] = defaultdict(int)
_lat_sum: dict[str, float] = defaultdict(float)
_lat_count: dict[str, int] = defaultdict(int)


def observe_request(method: str, path: str, status: int, seconds: float) -> None:
    with _lock:
        _requests[(method, path, status)] += 1
        _lat_sum[path] += seconds
        _lat_count[path] += 1


def install_usage_sink() -> None:
    from app.llm import providers

    def sink(row: dict) -> None:
        with session_factory()() as db:
            db.add(LLMUsage(**row))
            db.commit()

    providers.usage_sink = sink


def render() -> str:
    lines = ["# HELP jarvis_http_requests_total HTTP requests by route and status",
             "# TYPE jarvis_http_requests_total counter"]
    with _lock:
        for (m, p, st), n in sorted(_requests.items()):
            lines.append(f'jarvis_http_requests_total{{method="{m}",route="{p}",status="{st}"}} {n}')
        lines += ["# HELP jarvis_http_request_seconds_sum Total request latency", "# TYPE jarvis_http_request_seconds_sum counter"]
        for p, v in sorted(_lat_sum.items()):
            lines.append(f'jarvis_http_request_seconds_sum{{route="{p}"}} {v:.6f}')
            lines.append(f'jarvis_http_request_seconds_count{{route="{p}"}} {_lat_count[p]}')
    lines += ["# HELP jarvis_tasks Tasks by status", "# TYPE jarvis_tasks gauge"]
    try:
        with session_factory()() as db:
            for status, n in db.execute(select(Task.status, func.count()).group_by(Task.status)).all():
                lines.append(f'jarvis_tasks{{status="{status}"}} {n}')
    except Exception:
        lines.append("# task counts unavailable")
    return "\n".join(lines) + "\n"
