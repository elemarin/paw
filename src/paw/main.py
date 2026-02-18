"""PAW — FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from paw.agent.conversation import ConversationManager
from paw.agent.loop import AgentLoop
from paw.agent.memory import MemoryTool
from paw.agent.soul import load_soul
from paw.agent.tools import ToolRegistry
from paw.automation.scheduler import AutomationScheduler
from paw.channels.base import ChannelInboundEvent
from paw.channels.manager import ChannelRuntimeManager
from paw.channels.router import ChannelRouter
from paw.coder.engine import CoderTool
from paw.config import get_config
from paw.db.engine import Database
from paw.extensions.loader import load_plugins
from paw.gateway import InboundEvent, OutputRouter, PawEventGateway
from paw.llm.gateway import LLMGateway
from paw.logging import setup_logging
from paw.tools.automation import AutomationTool
from paw.tools.files import FileTool
from paw.tools.shell import ShellTool

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup/shutdown lifecycle."""
    config = get_config()
    setup_logging(level=config.log_level, fmt=config.log_format)

    logger.info("paw.starting", version="1.0.0", model=config.llm.model)

    # Load soul (just the base text, full prompt built after memory loads)
    soul_text = load_soul(config.soul_path)
    logger.info("paw.soul.loaded", length=len(soul_text))

    # Initialize database
    db = Database(config.database_url, data_dir=config.data_dir)
    await db.initialize()

    # Initialize LLM gateway
    gateway = LLMGateway(config.llm)

    # Initialize tool registry
    registry = ToolRegistry()

    # Register built-in tools
    memory_tool = MemoryTool(db)
    registry.register(ShellTool(config.shell))
    registry.register(FileTool(config))
    registry.register(memory_tool)
    registry.register(CoderTool(config.workspace_dir, config.plugins_dir))
    automation_tool = AutomationTool(
        db=db,
        heartbeat=config.heartbeat,
        llm=config.llm,
    )
    registry.register(automation_tool)

    # Load plugins
    plugin_tools = await load_plugins(config.plugins_dir, registry)
    logger.info("paw.plugins.loaded", count=len(plugin_tools))

    # Load memories from DB
    await memory_tool.load_from_db()

    # Initialize conversation manager — rebuild soul with DB memories
    soul = load_soul(config.soul_path)
    conversations = ConversationManager(db=db, soul=soul)
    await conversations.load_from_db()

    # Initialize agent
    agent = AgentLoop(
        gateway=gateway,
        registry=registry,
        config=config.agent,
        soul=soul,
    )

    channel_router = ChannelRouter(db)
    output_router = OutputRouter(
        channel_manager=None,
        webhook_timeout_s=config.webhooks.outbound_timeout_s,
    )
    event_gateway = PawEventGateway(
        config=config,
        conversations=conversations,
        agent=agent,
        llm_gateway=gateway,
        memory_tool=memory_tool,
        channel_router=channel_router,
        output_router=output_router,
    )

    async def handle_channel_inbound(event: ChannelInboundEvent) -> str:
        processed = await event_gateway.handle_event(
            InboundEvent(
                kind="user_message",
                channel=event.channel,
                session_key=event.session_key,
                sender_id=event.sender_id,
                peer_id=event.peer_id,
                text=event.text,
                model=event.model,
                agent_mode=event.agent_mode,
                metadata={
                    "message_id": event.message_id,
                    "update_id": event.update_id,
                    "thread_id": event.thread_id,
                },
            )
        )
        return processed.response_text

    channel_manager = ChannelRuntimeManager(
        config=config,
        db=db,
        inbound_handler=handle_channel_inbound,
    )
    output_router.channel_manager = channel_manager
    await channel_manager.start()
    automation_tool.on_models_updated = channel_manager.set_models
    automation_tool.on_runtime_event = event_gateway.emit_hook

    async def run_automation_prompt(
        prompt: str,
        source: str,
        output_target: str | None = None,
    ) -> None:
        target = (output_target or "").strip() or "log"
        await event_gateway.handle_event(
            InboundEvent(
                kind="heartbeat" if source == "heartbeat" else "cron",
                channel="automation",
                session_key=f"automation:{source}:{target}",
                sender_id="system",
                peer_id="system",
                text=prompt,
                model=None,
                agent_mode=True,
                output_target=target,
                metadata={"source": source},
            )
        )

    scheduler = AutomationScheduler(config=config.heartbeat, db=db, runner=run_automation_prompt)
    await scheduler.start()

    # Store on app state
    app.state.config = config
    app.state.gateway = gateway
    app.state.registry = registry
    app.state.agent = agent
    app.state.conversations = conversations
    app.state.db = db
    app.state.soul = soul
    app.state.memory_tool = memory_tool
    app.state.channel_router = channel_router
    app.state.channel_manager = channel_manager
    app.state.scheduler = scheduler
    app.state.event_gateway = event_gateway

    logger.info(
        "paw.ready",
        tools=list(registry.tools.keys()),
        tool_count=len(registry.tools),
    )

    yield

    # Shutdown
    logger.info("paw.shutting_down")
    await scheduler.stop()
    await channel_manager.stop()
    await db.close()
    logger.info("paw.stopped")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="PAW — Personal Agent Workspace",
        version="1.0.0",
        description="A self-hosted AI agent with its own Linux environment.",
        lifespan=lifespan,
    )

    # Register routes
    from paw.api.routes.channels import router as channels_router
    from paw.api.routes.chat import router as chat_router
    from paw.api.routes.conversations import router as conversations_router
    from paw.api.routes.health import router as health_router
    from paw.api.routes.memory import router as memory_router
    from paw.api.routes.webhooks import router as webhooks_router

    app.include_router(health_router, tags=["health"])
    app.include_router(chat_router, tags=["chat"])
    app.include_router(channels_router, tags=["channels"])
    app.include_router(conversations_router, tags=["conversations"])
    app.include_router(memory_router, tags=["memory"])
    app.include_router(webhooks_router, tags=["webhooks"])

    return app


app = create_app()


def main() -> None:
    """Run the server directly."""
    config = get_config()
    setup_logging(level=config.log_level, fmt=config.log_format)
    uvicorn.run(
        "paw.main:app",
        host=config.host,
        port=config.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
