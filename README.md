# 🐾 PAW — Personal Agent Workspace

```
                            __
     ,                    ," e`--o
    ((                   (  | __,'
     \\~----------------' \_;/
     (                      /
     /) ._______________.  )
    (( (               (( (
     ``-'               ``-'

```

A self-hosted AI agent that lives in its own Linux container. CLI-first. Self-building. Model-agnostic. Sandboxed.

> PAW is the core intelligence — everything else it builds for itself.

---

## What is PAW?

PAW is a personal AI agent that:

- **Lives in a full Linux container** — it has shell access, a filesystem, and networking
- **Uses any LLM** — OpenAI, Anthropic, Google, Ollama, or any provider via [LiteLLM](https://github.com/BerriAI/litellm)
- **Has tools** — shell execution, file management, persistent memory, self-building
- **Security-hardened** — sandboxed file access, command blocking, approval patterns, directory restrictions
- **Dual memory system** — persistent key-value store in SQLite + markdown-based memory files with rolling daily logs
- **Has identity** — `soul.md` defines who PAW is, what it values, and how it works
- **Builds itself** — the Coder tool lets PAW scaffold and propose new plugins
- **Is extensible** — drop-in plugin system for adding new capabilities

## Quick Start

### 1. Clone & Configure

```bash
git clone <your-repo-url> paw
cd paw
cp .env.example .env
# Edit .env — add your LLM API key
```

### 2. Run with Docker

```bash
docker compose up -d
```

### 3. Talk to PAW

```bash
# Install CLI
pip install -e .

# Chat
paw chat "Hello! What can you do?"

# Check status
paw status

# Use specific model
paw chat "Explain quantum computing" --model anthropic/claude-sonnet-4-20250514
```

### 4. Or use the API directly

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello!"}],
    "agent_mode": true
  }'
```

## Architecture

```
┌─────────────────────────────────────────┐
│  Ubuntu 22.04 Container                │
│                                         │
│  ┌─────────┐  ┌──────────────────────┐ │
│  │ FastAPI  │  │    Agent Loop        │ │
│  │  :8000   │──│  Think→Act→Observe   │ │
│  └─────────┘  └──────┬───────────────┘ │
│                       │                 │
│  ┌────────────────────┴──────────────┐ │
│  │         Tool Registry             │ │
│  │  Shell │ Files │ Memory │ Coder   │ │
│  └───────────────────────────────────┘ │
│                                         │
│  ┌──────────┐  ┌──────────────────┐    │
│  │ SQLite   │  │  Plugin System   │    │
│  │ paw.db   │  │  /plugins/*      │    │
│  └──────────┘  └──────────────────┘    │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  LiteLLM Gateway → Any Provider │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## Built-in Tools

| Tool | Description |
|------|-------------|
| **shell** | Execute commands in PAW's Linux environment — with blocked commands, approval patterns, timeout enforcement, and working-directory sandboxing |
| **files** | Read, write, list, search, append, delete files — sandboxed to workspace/plugins/data/tmp directories only |
| **memory** | Persistent key-value memory (SQLite-backed) across conversations — remember, recall, forget, list |
| **coder** | Create plugins, standalone scripts, and self-improvement proposals — with scaffolding and source introspection |

## Security Hardening

PAW runs inside a container but also enforces at the application layer:

| Layer | What it does |
|-------|-------------|
| **File sandboxing** | All file reads and writes are restricted to `workspace/`, `plugins/`, `data/`, and `/tmp`. Path traversal attempts are blocked. |
| **Shell command blocking** | Commands like `reboot`, `shutdown`, `mkfs` are permanently blocked. |
| **Approval patterns** | Dangerous patterns (`rm -rf`, `dd`, `sudo`) are flagged and rejected unless explicitly approved. |
| **Working-dir restriction** | Shell commands can only run with a `cwd` inside allowed writable directories. |
| **API key auth** | Optional `X-API-Key` header authentication for all API endpoints. |
| **Token budgets** | Per-request and daily token limits prevent runaway LLM costs. |
| **Output truncation** | Shell output (10 KB) and file reads (50 KB) are capped to avoid prompt-stuffing. |

## Memory System

PAW has a **dual-layer memory** that persists across conversations:

### Key-Value Store (SQLite)
The agent can `remember`, `recall`, `forget`, and `list` named memories. Stored in SQLite, loaded into context on startup, and injected into the system prompt so the LLM always has access.

### Markdown Memory Files
PAW loads `MEMORY.md` (long-term notes) plus the last 3 days of daily logs (`YYYY-MM-DD.md`) from a `memory/` directory. This gives the agent a rolling context window of recent activity without unbounded growth.

Both layers are merged into a `<MEMORY>` block in the system prompt so the LLM can answer from memory without extra tool calls.

## Plugin System

PAW discovers plugins automatically from the `plugins/` directory:

```
plugins/
  my_plugin/
    plugin.yaml     # Metadata
    __init__.py     # PawPlugin subclass
```

Plugins extend the `PawPlugin` base class, receive access to the tool registry and database, and can register new tools on load. PAW can also **create its own plugins** using the Coder tool:

```bash
paw chat "Create a plugin that fetches weather data"
```

## Configuration

### Environment Variables (`.env`)

```bash
PAW_LLM__API_KEY=sk-...          # Your LLM API key
PAW_LLM__MODEL=openai/gpt-4o-mini  # Model to use
PAW_API_KEY=change-me-strong-key  # Required for API access
```

### Config File (`paw.yaml`)

See [paw.yaml.example](paw.yaml.example) for all options.

## Development

```bash
# Install in development mode
pip install -e ".[dev]"

# Run locally (without Docker)
paw serve --reload

# Run tests
pytest

# Lint
ruff check src/
```

## Project Structure

```
src/paw/
  main.py           # FastAPI app + lifespan
  config.py          # Configuration (paw.yaml + .env)
  logging.py         # Structured logging
  agent/
    loop.py          # ReAct agent loop (Think→Act→Observe)
    tools.py         # Tool base class + registry
    conversation.py  # Conversation state management
    memory.py        # Persistent memory tool
    soul.py          # soul.md loader
  llm/
    gateway.py       # LiteLLM async wrapper
  api/
    routes/          # FastAPI endpoints
    middleware/      # Auth middleware
  tools/
    shell.py         # Shell command execution
    files.py         # File operations
  db/
    engine.py        # SQLite async database
  extensions/
    base.py          # Plugin base class
    loader.py        # Auto-discovery plugin loader
  coder/
    engine.py        # Self-building tool
  cli/
    main.py          # Typer CLI
```

## Philosophy

PAW is built around the idea that an AI agent should be a **digital worker** — not just a chatbot. It has its own environment, its own identity, and the ability to build new capabilities for itself.

The core is small and focused. Everything else — web UIs, integrations, notification systems — PAW builds as plugins when you ask for them.

Security isn't an afterthought. Every tool enforces sandbox boundaries, dangerous operations require approval, and the agent can never modify its own core code.

**Ship the brain, not the body.**

---

*Built with ❤️ and a lot of LLM tokens. Mascot: Chips the wiener dog 🌭*
