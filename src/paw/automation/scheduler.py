"""Heartbeat + cron scheduler."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import structlog

from paw.config import HeartbeatConfig
from paw.db.engine import Database

logger = structlog.get_logger()

PromptRunner = Callable[[str, str], Awaitable[None]]


class AutomationScheduler:
    """Simple scheduler for heartbeat checks and cron prompts."""

    def __init__(self, *, config: HeartbeatConfig, db: Database, runner: PromptRunner) -> None:
        self.config = config
        self.db = db
        self.runner = runner
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_heartbeat_minute: str | None = None
        self._last_cron_minute: dict[int, str] = {}

    async def start(self) -> None:
        if not self.config.enabled or self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="paw-automation-scheduler")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            now = datetime.now(UTC)
            try:
                await self._run_heartbeat_if_due(now)
                await self._run_cron_if_due(now)
            except Exception as exc:
                logger.warning("automation.scheduler.error", error=str(exc))
            await asyncio.sleep(30)

    async def _run_heartbeat_if_due(self, now: datetime) -> None:
        interval = max(1, int(self.config.interval_minutes))
        minute_bucket = now.strftime("%Y-%m-%dT%H:%M")
        if now.minute % interval != 0 or self._last_heartbeat_minute == minute_bucket:
            return

        checklist = _load_checklist(self.config.checklist_path)
        if checklist:
            await self.runner(f"[HEARTBEAT]\n{checklist}", "heartbeat")
            logger.info("automation.heartbeat.ran", minute=minute_bucket)
        self._last_heartbeat_minute = minute_bucket

    async def _run_cron_if_due(self, now: datetime) -> None:
        jobs = await self.db.heartbeat_cron_list()
        minute_bucket = now.strftime("%Y-%m-%dT%H:%M")
        for job in jobs:
            job_id = int(job["id"])
            if self._last_cron_minute.get(job_id) == minute_bucket:
                continue
            if not _cron_matches(str(job["schedule"]), now):
                continue
            await self.runner(f"[CRON:{job['label']}]\n{job['prompt']}", "cron")
            await self.db.heartbeat_cron_mark_run(job_id=job_id)
            self._last_cron_minute[job_id] = minute_bucket
            logger.info("automation.cron.ran", job_id=job_id, label=job["label"])


def _load_checklist(path: str) -> str:
    primary = Path(path)
    if primary.exists():
        return primary.read_text(encoding="utf-8").strip()
    return ""


def _cron_matches(schedule: str, now: datetime) -> bool:
    fields = schedule.strip().split()
    if len(fields) != 5:
        return False
    values = [now.minute, now.hour, now.day, now.month, now.weekday()]
    return all(_match_field(field, value) for field, value in zip(fields, values, strict=True))


def _match_field(field: str, value: int) -> bool:
    if field == "*":
        return True
    if field.startswith("*/"):
        try:
            step = int(field[2:])
        except ValueError:
            return False
        return step > 0 and value % step == 0
    try:
        return int(field) == value
    except ValueError:
        return False
