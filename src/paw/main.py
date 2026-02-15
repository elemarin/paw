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
from paw.agent.soul import get_system_prompt, load_soul
from paw.agent.tools import ToolRegistry
from paw.channels.base import ChannelInboundEvent
from paw.channels.manager import ChannelRuntimeManager
from paw.channels.router import ChannelRouter
from paw.coder.engine import CoderTool
from paw.config import get_config
from paw.db.engine import Database
from paw.extensions.loader import load_plugins
from paw.llm.gateway import LLMGateway
from paw.logging import setup_logging
from paw.tools.files import FileTool
from paw.tools.shell import ShellTool

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup/shutdown lifecycle."""
    config = get_config()
    setup_logging(level=config.log_level, fmt=config.log_format)

    logger.info("paw.starting", version="0.1.0", model=config.llm.model)

    # Load soul (just the base text, full prompt built after memory loads)
    soul_text = load_soul(config.soul_path)
    logger.info("paw.soul.loaded", length=len(soul_text))

    # Initialize database
    db = Database(
        config.data_dir,
        journal_mode=config.db_journal_mode,
        busy_timeout_ms=config.db_busy_timeout_ms,
    )
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

    # Load plugins
    plugin_tools = await load_plugins(config.plugins_dir, registry)
    logger.info("paw.plugins.loaded", count=len(plugin_tools))

    # Load memories from DB
    await memory_tool.load_from_db()

    # Initialize conversation manager — rebuild soul with DB memories
    soul = get_system_prompt(config.soul_path, memory_tool=memory_tool)
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

    async def handle_channel_inbound(event: ChannelInboundEvent) -> str:
        conv_id = await channel_router.resolve_conversation_id(event.channel, event.session_key)
        conversation = conversations.get_or_create(conv_id)

        fresh_soul = get_system_prompt(config.soul_path, memory_tool=memory_tool)
        if conversation.messages and conversation.messages[0].role == "system":
            conversation.messages[0].content = fresh_soul
        elif not conversation.messages:
            conversation.add_message("system", fresh_soul)

        conversation.add_message("user", event.text)

        if event.agent_mode:
            result = await agent.run(
                conversation=conversation,
                model=event.model,
                temperature=None,
                max_tokens=None,
            )
            await conversations.save_conversation(conversation)
            return result.response

        messages = [{"role": m.role, "content": m.content} for m in conversation.messages]
        response = await gateway.completion(
            messages=messages,
            model=event.model,
            temperature=None,
            max_tokens=None,
        )
        content = response.choices[0].message.content or ""
        conversation.add_message("assistant", content)
        await conversations.save_conversation(conversation)
        return content

    channel_manager = ChannelRuntimeManager(
        config=config,
        db=db,
        inbound_handler=handle_channel_inbound,
    )
    await channel_manager.start()

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

    logger.info(
        "paw.ready",
        tools=list(registry.tools.keys()),
        tool_count=len(registry.tools),
    )

    yield

    # Shutdown
    logger.info("paw.shutting_down")
    await channel_manager.stop()
    await db.close()
    logger.info("paw.stopped")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="PAW — Personal Agent Workspace",
        version="0.1.0",
        description="A self-hosted AI agent with its own Linux environment.",
        lifespan=lifespan,
    )

    # Register routes
    from paw.api.routes.chat import router as chat_router
    from paw.api.routes.conversations import router as conversations_router
    from paw.api.routes.health import router as health_router
    from paw.api.routes.memory import router as memory_router

    app.include_router(health_router, tags=["health"])
    app.include_router(chat_router, tags=["chat"])
    app.include_router(conversations_router, tags=["conversations"])
    app.include_router(memory_router, tags=["memory"])

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
