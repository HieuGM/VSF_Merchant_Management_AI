#!/usr/bin/env python
"""Inspect một customer-agent run từ DB — timeline events + thống kê tool calls.

Dùng sau khi chạy flow để verify observability pipeline (agent_runs + agent_events),
phát hiện tool call trùng (constraint "mỗi tool tối đa 1 lần") và breakdown thời gian.

Cách chạy:
    conda run -n ai_restaurant python backend/scripts/inspect_customer_run.py [session_id]

Mặc định session_id = session_diag_01.
"""
from __future__ import annotations

import io
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
os.environ.pop("SSL_CERT_FILE", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from database.connection import SessionLocal  # noqa: E402


def main() -> None:
    session_id = sys.argv[1] if len(sys.argv) > 1 else "session_diag_01"
    db = SessionLocal()
    try:
        # 1. Run record
        run = db.execute(
            text(
                "SELECT trace_id, status, intent, crew_name, started_at, finished_at, "
                "error_code FROM agent_runs WHERE session_id = :sid "
                "ORDER BY started_at DESC LIMIT 1"
            ),
            {"sid": session_id},
        ).fetchone()

        print("=" * 70)
        print(f"RUN (session={session_id})")
        print("=" * 70)
        if not run:
            print(f"[MISSING] không có agent_runs cho session_id={session_id}")
            return
        print(f"trace_id    : {run.trace_id}")
        print(f"status      : {run.status}")
        print(f"intent      : {run.intent}")
        print(f"crew_name   : {run.crew_name}")
        print(f"started_at  : {run.started_at}")
        print(f"finished_at : {run.finished_at}")
        print(f"error_code  : {run.error_code}")

        trace_id = run.trace_id

        # 2. Event timeline
        rows = db.execute(
            text(
                "SELECT event_type, agent_name, task_name, tool_name, duration_ms, status, "
                "error_code, created_at FROM agent_events WHERE trace_id = :tid "
                "ORDER BY created_at ASC"
            ),
            {"tid": trace_id},
        ).fetchall()

        print(f"\n{'=' * 70}\nEVENT TIMELINE ({len(rows)} events)\n{'=' * 70}")
        for r in rows:
            dur = f"{r.duration_ms}ms" if r.duration_ms is not None else "-"
            tag = r.event_type
            if r.tool_name:
                tag = f"{r.event_type}:{r.tool_name}"
            elif r.task_name:
                tag = f"{r.event_type}:{r.task_name}"
            err = f"  ERR={r.error_code}" if r.error_code else ""
            agent = (r.agent_name or "")[:40]
            print(f"  {r.created_at}  {tag:36} {dur:>9}  {agent}{err}")

        # 3. Tool call summary + duplicate detection
        tool_starts = [
            r.tool_name for r in rows
            if r.event_type == "tool_started" and r.tool_name
        ]
        print(f"\n{'=' * 70}\nTOOL CALLS\n{'=' * 70}")
        counts = Counter(tool_starts)
        for name, c in counts.items():
            flag = "  <-- DUPLICATE (constraint: max 1)" if c > 1 else ""
            print(f"  {name:32} started={c}{flag}")

        # 4. Per-task duration
        print(f"\n{'=' * 70}\nTASK DURATIONS\n{'=' * 70}")
        per_task: dict[str, list[int]] = defaultdict(list)
        for r in rows:
            if r.event_type == "task_finished" and r.task_name and r.duration_ms is not None:
                per_task[r.task_name].append(r.duration_ms)
        for task, durs in per_task.items():
            print(f"  {task:24} total={sum(durs)}ms  calls={len(durs)}")
        if not per_task:
            print("  (no task_finished events with duration)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
