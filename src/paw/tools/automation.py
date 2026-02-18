"""Automation skill for heartbeat, cron, and runtime model management."""

from __future__ import annotations

import inspect
import secrets
from pathlib import Path
from typing import Any

from paw.agent.tools import Tool
from paw.config import HeartbeatConfig, LLMConfig
from paw.db.engine import Database


class AutomationTool(Tool):
    def __init__(
        self,
        *,
        db: Database,
        heartbeat: HeartbeatConfig,
        llm: LLMConfig,
        on_models_updated: Any = None,
        on_runtime_event: Any = None,
    ) -> None:
        self.db = db
        self.heartbeat = heartbeat
        self.llm = llm
        self.on_models_updated = on_models_updated
        self.on_runtime_event = on_runtime_event

    @property
    def name(self) -> str:
        return "automation"

    @property
    def description(self) -> str:
        return (
            "Manage heartbeat checks (add/edit/remove), cron jobs with output targets, "
            "channel pairing codes, and runtime models."
        )

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
                        "heartbeat_add_item",
                        "heartbeat_edit_item",
                        "heartbeat_remove_item",
                        "cron_add",
                        "cron_list",
                        "cron_remove",
                        "telegram_pair_code",
                        "model_show",
                        "model_set",
                        "model_set_regular",
                        "model_set_smart",
                    ],
                },
                "interval_minutes": {"type": "integer"},
                "checklist": {"type": "string"},
                "text": {"type": "string"},
                "index": {"type": "integer"},
                "label": {"type": "string"},
                "schedule": {"type": "string"},
                "prompt": {"type": "string"},
                "output_target": {"type": "string"},
                "job_id": {"type": "integer"},
                "model": {"type": "string"},
                "regular_model": {"type": "string"},
                "smart_model": {"type": "string"},
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
        if action == "heartbeat_add_item":
            text = str(kwargs.get("text") or "").strip()
            output_target = _normalize_output_target(str(kwargs.get("output_target") or "").strip())
            if not text:
                return "Please provide text for the heartbeat item."
            if not output_target:
                return "Please specify output_target (example: telegram or email)."
            items = self._heartbeat_items()
            items.append(f"- {text} | output={output_target}")
            self._write_heartbeat_items(items)
            return f"Added heartbeat item #{len(items)}."
        if action == "heartbeat_edit_item":
            index = int(kwargs.get("index") or 0)
            text = str(kwargs.get("text") or "").strip()
            output_target = _normalize_output_target(str(kwargs.get("output_target") or "").strip())
            items = self._heartbeat_items()
            if index < 1 or index > len(items):
                return "Heartbeat item not found."
            if not text and not output_target:
                return (
                    "Please provide text and/or output_target to edit the heartbeat item."
                )
            current = items[index - 1]
            current_text, current_target = _parse_heartbeat_item(current)
            next_text = text or current_text
            next_target = output_target or _normalize_output_target(current_target)
            if not next_target:
                return "Please specify output_target (example: telegram or email)."
            items[index - 1] = f"- {next_text} | output={next_target}"
            self._write_heartbeat_items(items)
            return f"Updated heartbeat item #{index}."
        if action == "heartbeat_remove_item":
            index = int(kwargs.get("index") or 0)
            items = self._heartbeat_items()
            if index < 1 or index > len(items):
                return "Heartbeat item not found."
            items.pop(index - 1)
            self._write_heartbeat_items(items)
            return f"Removed heartbeat item #{index}."
        if action == "cron_add":
            output_target = _normalize_output_target(str(kwargs.get("output_target") or "").strip())
            if not output_target:
                return "Please specify output_target (example: telegram or email)."
            await self.db.heartbeat_cron_add(
                label=str(kwargs.get("label") or "cron"),
                schedule=str(kwargs.get("schedule") or "*/30 * * * *"),
                prompt=str(kwargs.get("prompt") or "").strip(),
                output_target=output_target,
            )
            return "Cron job added."
        if action == "cron_list":
            jobs = await self.db.heartbeat_cron_list()
            if not jobs:
                return "No cron jobs configured."
            lines = [
                (
                    f"{job['id']}. [{job['schedule']}] {job['label']} -> {job['prompt']} "
                    f"(output={job.get('output_target') or 'unset'})"
                )
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
        if action == "model_show":
            return self._model_show()
        if action == "model_set":
            regular = str(kwargs.get("regular_model") or kwargs.get("model") or "").strip()
            smart = str(kwargs.get("smart_model") or kwargs.get("model") or "").strip()
            return await self._set_models(regular_model=regular, smart_model=smart)
        if action == "model_set_regular":
            regular = str(kwargs.get("regular_model") or kwargs.get("model") or "").strip()
            return await self._set_models(regular_model=regular, smart_model="")
        if action == "model_set_smart":
            smart = str(kwargs.get("smart_model") or kwargs.get("model") or "").strip()
            return await self._set_models(regular_model="", smart_model=smart)
        return "Unsupported action."

    def _heartbeat_show(self) -> str:
        items = self._heartbeat_items()
        listed = "\n".join([f"{idx}. {item}" for idx, item in enumerate(items, start=1)])
        return (
            f"interval_minutes={self.heartbeat.interval_minutes}\n"
            f"checklist_path={self.heartbeat.checklist_path}\n"
            f"default_output_target={self.heartbeat.default_output_target or '(unset)'}\n"
            f"checklist:\n{listed or '(empty)'}"
        )

    async def _set_models(self, *, regular_model: str, smart_model: str) -> str:
        if regular_model:
            self.llm.model = regular_model
        if smart_model:
            self.llm.smart_model = smart_model
        if callable(self.on_models_updated):
            self.on_models_updated(
                regular_model=self.llm.model,
                smart_model=self.llm.smart_model,
            )
        if callable(self.on_runtime_event):
            maybe = self.on_runtime_event(
                name="model_changed",
                payload={
                    "regular_model": self.llm.model,
                    "smart_model": self.llm.smart_model,
                },
            )
            if inspect.isawaitable(maybe):
                await maybe
        return (
            "Runtime models updated.\n"
            f"regular_model={self.llm.model}\n"
            f"smart_model={self.llm.smart_model}"
        )

    def _model_show(self) -> str:
        return f"regular_model={self.llm.model}\nsmart_model={self.llm.smart_model}"

    def _heartbeat_items(self) -> list[str]:
        path = Path(self.heartbeat.checklist_path)
        if not path.exists():
            return []
        content = path.read_text(encoding="utf-8").splitlines()
        # Keep checklist format strict to "-" bullets so add/edit/remove stays deterministic.
        return [line.strip() for line in content if line.strip().startswith("-")]

    def _write_heartbeat_items(self, items: list[str]) -> None:
        path = Path(self.heartbeat.checklist_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(items) + ("\n" if items else ""), encoding="utf-8")


def _parse_heartbeat_item(line: str) -> tuple[str, str]:
    raw = line.strip().removeprefix("-").strip()
    text, sep, tail = raw.partition("|")
    output_target = ""
    if sep:
        for part in tail.split("|"):
            part = part.strip()
            if part.lower().startswith("output="):
                output_target = part.split("=", 1)[1].strip()
                break
    return text.strip(), output_target


def _normalize_output_target(value: str) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    if ":" in normalized:
        normalized = normalized.split(":", 1)[0].strip()
    if normalized in {"telegram", "email", "log", "webhook"}:
        return normalized
    return normalized
