"""PAW — FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
import uvicorn
from fastapi import FastAPI

from paw.config import get_config
from paw.logging import setup_logging
from paw.llm.gateway import LLMGateway
from paw.agent.soul import load_soul
from paw.agent.loop import AgentLoop
from paw.agent.conversation import ConversationManager
from paw.agent.tools import ToolRegistry
from paw.tools.shell import ShellTool
from paw.tools.files import FileTool
from paw.agent.memory import MemoryTool
from paw.coder.engine import CoderTool
from paw.extensions.loader import load_plugins
from paw.db.engine import Database

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup/shutdown lifecycle."""
    config = get_config()
    setup_logging(level=config.log_level, fmt=config.log_format)

    logger.info("paw.starting", version="0.1.0", model=config.llm.model)

    # Load soul
    soul = load_soul(config.soul_path)
    logger.info("paw.soul.loaded", length=len(soul))

    # Initialize database
    db = Database(config.data_dir)
    await db.initialize()

    # Initialize LLM gateway
    gateway = LLMGateway(config.llm)

    # Initialize tool registry
    registry = ToolRegistry()

    # Register built-in tools
    registry.register(ShellTool(config.shell))
    registry.register(FileTool(config))
    registry.register(MemoryTool(db))
    registry.register(CoderTool(config.workspace_dir, config.plugins_dir))

    # Load plugins
    plugin_tools = await load_plugins(config.plugins_dir, registry)
    logger.info("paw.plugins.loaded", count=len(plugin_tools))

    # Initialize conversation manager
    conversations = ConversationManager(db=db, soul=soul)
    await conversations.load_from_db()

    # Initialize agent
    agent = AgentLoop(
        gateway=gateway,
        registry=registry,
        config=config.agent,
        soul=soul,
    )

    # Store on app state
    app.state.config = config
    app.state.gateway = gateway
    app.state.registry = registry
    app.state.agent = agent
    app.state.conversations = conversations
    app.state.db = db
    app.state.soul = soul

    logger.info(
        "paw.ready",
        tools=list(registry.tools.keys()),
        tool_count=len(registry.tools),
    )

    yield

    # Shutdown
    logger.info("paw.shutting_down")
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
    from paw.api.routes.health import router as health_router
    from paw.api.routes.chat import router as chat_router
    from paw.api.routes.conversations import router as conversations_router

    app.include_router(health_router, tags=["health"])
    app.include_router(chat_router, tags=["chat"])
    app.include_router(conversations_router, tags=["conversations"])

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
