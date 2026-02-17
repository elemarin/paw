"""Automation skill for heartbeat and cron management."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from paw.agent.tools import Tool
from paw.config import HeartbeatConfig
from paw.db.engine import Database


class AutomationTool(Tool):
    def __init__(self, *, db: Database, heartbeat: HeartbeatConfig) -> None:
        self.db = db
        self.heartbeat = heartbeat

    @property
    def name(self) -> str:
        return "automation"

    @property
    def description(self) -> str:
        return "Manage heartbeat checks, cron jobs, and channel pairing codes."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "heartbeat_show",
                        "heartbeat_set_interval",
                        "cron_add",
                        "cron_list",
                        "cron_remove",
                        "telegram_pair_code",
                    ],
                },
                "interval_minutes": {"type": "integer"},
                "checklist": {"type": "string"},
                "label": {"type": "string"},
                "schedule": {"type": "string"},
                "prompt": {"type": "string"},
                "job_id": {"type": "integer"},
            },
            "required": ["action"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> str:
        action = str(kwargs.get("action") or "").strip().lower()
        if action == "heartbeat_show":
            return self._heartbeat_show()
        if action == "heartbeat_set_interval":
            interval = int(kwargs.get("interval_minutes") or 5)
            self.heartbeat.interval_minutes = max(1, interval)
            checklist = kwargs.get("checklist")
            if isinstance(checklist, str) and checklist.strip():
                Path(self.heartbeat.checklist_path).write_text(checklist.strip(), encoding="utf-8")
            return f"Heartbeat interval set to {self.heartbeat.interval_minutes} minute(s)."
        if action == "cron_add":
            await self.db.heartbeat_cron_add(
                label=str(kwargs.get("label") or "cron"),
                schedule=str(kwargs.get("schedule") or "*/30 * * * *"),
                prompt=str(kwargs.get("prompt") or "").strip(),
            )
            return "Cron job added."
        if action == "cron_list":
            jobs = await self.db.heartbeat_cron_list()
            if not jobs:
                return "No cron jobs configured."
            lines = [
                f"{job['id']}. [{job['schedule']}] {job['label']} -> {job['prompt']}"
                for job in jobs
            ]
            return "\n".join(lines)
        if action == "cron_remove":
            ok = await self.db.heartbeat_cron_remove(job_id=int(kwargs.get("job_id") or 0))
            return "Cron job removed." if ok else "Cron job not found."
        if action == "telegram_pair_code":
            code = secrets.token_hex(3).upper()
            await self.db.channel_pairing_code_create(
                channel="telegram",
                code=code,
                ttl_minutes=10,
            )
            return f"Telegram pairing code: {code}"
        return "Unsupported action."

    def _heartbeat_show(self) -> str:
        path = Path(self.heartbeat.checklist_path)
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
        else:
            content = ""
        return (
            f"interval_minutes={self.heartbeat.interval_minutes}\n"
            f"checklist_path={self.heartbeat.checklist_path}\n"
            f"checklist:\n{content or '(empty)'}"
        )
