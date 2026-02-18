"""Routing for gateway outbound targets."""

from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger()


class OutputRouter:
    """Routes generated outputs to channels, webhooks, or logs."""

    def __init__(self, *, channel_manager=None, webhook_timeout_s: int = 10) -> None:
        self.channel_manager = channel_manager
        self.webhook_timeout_s = max(1, int(webhook_timeout_s))

    async def dispatch(self, *, target: str, text: str, source: str, metadata: dict | None = None) -> bool:
        normalized = (target or "").strip()
        if not normalized:
            return False

        if normalized.lower() == "log":
            logger.info(
                "gateway.output.log",
                source=source,
                target=normalized,
                preview=(text or "")[:240],
            )
            return True

        if normalized.startswith("webhook:"):
            return await self._dispatch_webhook(
                url=normalized.split(":", 1)[1].strip(),
                text=text,
                source=source,
                target=normalized,
                metadata=metadata or {},
            )

        if normalized.startswith("http://") or normalized.startswith("https://"):
            return await self._dispatch_webhook(
                url=normalized,
                text=text,
                source=source,
                target=normalized,
                metadata=metadata or {},
            )

        if self.channel_manager is None:
            logger.warning("gateway.output.unhandled", source=source, target=normalized)
            return False

        handled = await self.channel_manager.dispatch_output_target(normalized, text)
        if handled:
            return True

        logger.warning("gateway.output.unhandled", source=source, target=normalized)
        return False

    async def _dispatch_webhook(
        self,
        *,
        url: str,
        text: str,
        source: str,
        target: str,
        metadata: dict,
    ) -> bool:
        if not url:
            logger.warning("gateway.output.webhook.invalid", reason="missing_url", target=target)
            return False

        timeout = httpx.Timeout(self.webhook_timeout_s)
        payload = {
            "source": source,
            "target": target,
            "text": text,
            "metadata": metadata,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                if response.status_code >= 400:
                    logger.warning(
                        "gateway.output.webhook.failed",
                        status_code=response.status_code,
                        target=target,
                        body=response.text[:300],
                    )
                    return False
            return True
        except Exception as exc:
            logger.warning("gateway.output.webhook.error", target=target, error=str(exc))
            return False
