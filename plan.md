# PAW — Personal Agent Workspace
### v3.0 — Launch Tonight Edition (2026-02-08)

> A self-hosted AI agent that lives in its own Linux environment, has its own identity, and builds itself new capabilities. CLI-first. No UI — PAW can build one if it wants to.

---

## Vision

PAW is a **digital worker** you talk to from your terminal. It lives inside a full Linux container it controls — shell access, filesystem, networking, package manager. You interact with it through a CLI (or its API). Everything else — web UI, Telegram bot, email — PAW can build for itself as plugins when you need them.

You don't give PAW your accounts. **PAW gets its own identity.** It has its own email, its own bots, its own workspace. Fully separated from yours.

The core insight: **ship the brain, not the body.** The brain is the agent loop + LiteLLM + tool framework + Coder plugin. The body (UI, integrations, communication channels) is whatever PAW builds for itself. Tonight we ship the brain.

**Multi-user = multi-instance.** One container per person. No shared state.

---

## soul.md — PAW's Identity Document

PAW ships with a `soul.md` file at its root. This is the foundational document that defines **who PAW is** — its identity, values, personality, and behavioral guidelines. It is loaded as the base system prompt on every conversation.

Think of it like Anthropic's soul document for Claude, but yours to customize.

**What `soul.md` contains:**
- **Identity** — PAW's name, role, and self-concept ("I am PAW, a personal agent workspace...")
- **Values** — What PAW prioritizes (user autonomy, transparency, safety, getting things done)
- **Personality** — Tone, communication style (direct, concise, proactive)
- **Capabilities & boundaries** — What PAW knows it can do, and what it should refuse or ask permission for
- **Relationship to user** — PAW is a worker, not a friend. Respectful, professional, efficient
- **Self-building principles** — When PAW writes code for itself: test first, propose before deploying, never modify core
- **Safety commitments** — Never impersonate the user, always disclose when uncertain, ask before destructive actions

**How it works:**
- `soul.md` lives at `/home/paw/soul.md` (persistent volume, survives restarts)
- A default `soul.md` ships with the image, gets copied on first boot
- User can edit it anytime — PAW re-reads it each conversation
- PAW can *propose* changes to its own soul (but never apply them without approval)
- The soul is the one thing that grounds PAW's behavior no matter what plugins are loaded

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  PAW Container (Ubuntu Linux)                               │
│                                                             │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ FastAPI     │  │  Agent Core  │  │  OS Environment     │  │
│  │ + CLI       │←→│  (ReAct)     │←→│  - Shell access     │  │
│  │ Port 8000   │  │              │  │  - File system      │  │
│  └─────┬──────┘  └──────┬───────┘  │  - Package manager  │  │
│        │                │          │  - Network stack     │  │
│        │         ┌──────┴───────┐  └─────────────────────┘  │
│        │         │  LiteLLM     │                           │
│        │         │  Gateway     │  ┌─────────────────────┐  │
│  ┌─────┴──────┐  └──────┬───────┘  │ soul.md             │  │
│  │ SQLite DB   │  ┌──────┴───────┐  │ (identity doc)      │  │
│  │ (persist)   │  │  Any LLM     │  └─────────────────────┘  │
│  └────────────┘  │  Provider    │                           │
│                  └──────────────┘                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Extension System                                    │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐  │   │
│  │  │ Shell    │ │ Coder    │ │ Self-built plugins   │  │   │
│  │  │ + Files  │ │ Plugin   │ │ (UI, email, TG, ...) │  │   │
│  │  └──────────┘ └──────────┘ └──────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

You ──→ Terminal (paw chat "do the thing")
     ──→ API (curl /v1/chat/completions)
     ──→ Whatever PAW builds (Telegram, Web UI, etc.)
```

---

## Decisions

| # | Decision | Details |
|---|----------|---------|
| 1 | **Python + FastAPI** | Core server |
| 2 | **SQLite** | Single-file DB, persistent volume |
| 3 | **Single API key** | One key per instance. Multi-user = multi-instance |
| 4 | **Full Linux container** | Ubuntu-based. PAW owns its OS |
| 5 | **Own identity** | PAW gets its own email, bots, etc. Never shares user credentials |
| 6 | **Self-building** | PAW writes plugins for itself (with approval). Can build its own UI, integrations, anything |
| 7 | **MCP client** | Connects to MCP servers for external tools |
| 8 | **CLI-first** | No built-in web UI. Talk to PAW from your terminal. PAW can build a UI plugin if needed |
| 9 | **soul.md** | Identity document loaded as base system prompt. Defines who PAW is |
| 10 | **`.env` + `paw.yaml`** | Secrets in `.env`, config in `paw.yaml` |

---

## Launch Tonight — MVP Scope

The goal is to ship something real tonight. Everything below the line, PAW can build for itself later.

### What ships tonight:
- ✅ FastAPI server in a Docker container (Ubuntu)
- ✅ LiteLLM gateway (talk to any model)
- ✅ `soul.md` loaded as system prompt
- ✅ CLI tool (`paw chat "message"`, `paw status`)
- ✅ Agent loop with tool calling (ReAct)
- ✅ Shell tool (PAW can run commands in its own OS)
- ✅ File tool (PAW can read/write files)
- ✅ SQLite persistence (conversations, memory)
- ✅ Coder plugin (PAW can write & propose new plugins)
- ✅ Plugin loader (auto-discover from `/plugins/`)
- ✅ API key auth
- ✅ `paw.yaml` + `.env` config

### What PAW builds for itself (post-launch):
- 🔨 Web UI plugin
- 🔨 Telegram bot plugin
- 🔨 Email integration plugin
- 🔨 MCP client plugin
- 🔨 Scheduled tasks plugin
- 🔨 Whatever else you ask it to build

---

## Step-by-Step Plan

### Phase 0 — Skeleton (Tonight, Hour 1)
> Bootable container with an AI brain.

| # | Task | Details |
|---|------|---------|
| 0.1 | **Project scaffolding** | `pyproject.toml`, `src/paw/` layout, ruff config |
| 0.2 | **Config** | Pydantic Settings: `paw.yaml` + `.env`. Model provider, API keys, agent limits |
| 0.3 | **LiteLLM gateway** | `llm/gateway.py` — async wrapper around `litellm.acompletion()`. Config-driven model selection |
| 0.4 | **FastAPI server** | `main.py` — `/v1/chat/completions`, `/health`. Uvicorn |
| 0.5 | **soul.md** | Default identity document. Loaded on boot, injected as system prompt |
| 0.6 | **Structured logging** | `structlog` — JSON, request IDs |
| 0.7 | **Dockerfile** | Ubuntu 22.04, Python 3.12, git/curl/build-essential. `paw` user with sudo |
| 0.8 | **docker-compose.yml** | Single service, `paw-data` volume, port 8000 |
| 0.9 | **entrypoint.sh** | Init dirs, copy default `soul.md` on first boot, start uvicorn |

**Milestone:** `docker compose up` → `curl /v1/chat/completions` → response with PAW's personality.

---

### Phase 1 — Agent Brain (Tonight, Hour 2-3)
> Tool calling, shell access, file management.

| # | Task | Details |
|---|------|---------|
| 1.1 | **Tool base class** | `Tool`: `name`, `description`, `parameters` (JSON Schema), `async execute()`. `ToolRegistry` |
| 1.2 | **Agent loop** | ReAct: think → act → observe → repeat. Max iterations, token budget. Step log |
| 1.3 | **Shell tool** | Run commands, capture stdout/stderr/exit code. Timeout. Safety: configurable command blocklist |
| 1.4 | **File tool** | Read, write, list, search files in `/home/paw/workspace/` and `/home/paw/plugins/` |
| 1.5 | **Memory tool** | Key-value store (in-memory dict for now, SQLite later). `remember(key, value)`, `recall(key)`, `forget(key)` |
| 1.6 | **Conversation manager** | Multi-turn state. In-memory dict. Create, append, list |

**Milestone:** `curl` a message → PAW runs shell commands and reads files to answer → multi-step reasoning visible in logs.

---

### Phase 2 — CLI + Persistence (Tonight, Hour 3-4)
> Talk to PAW from your terminal. Conversations survive restarts.

| # | Task | Details |
|---|------|---------|
| 2.1 | **CLI tool** | `paw chat "message"` — send a message, get streaming response. `paw chat` (no arg) — interactive REPL mode |
| 2.2 | **CLI commands** | `paw status` — health, model, uptime. `paw conversations` — list. `paw memory` — show memories. `paw plugins` — list loaded plugins |
| 2.3 | **SQLite** | `aiosqlite`. Tables: `conversations`, `messages`, `tool_calls`, `memory`. Auto-migrate on boot |
| 2.4 | **Persist conversations** | Store/restore conversations across restarts |
| 2.5 | **Persist memory** | Long-term memory backed by SQLite |
| 2.6 | **API key auth** | `PAW_API_KEY` in `.env`. Middleware. Disabled if not set |

**Milestone:** `paw chat "what did we talk about yesterday?"` → PAW remembers.

---

### Phase 3 — Self-Building (Tonight, Hour 4-5)
> PAW can extend itself.

| # | Task | Details |
|---|------|---------|
| 3.1 | **Plugin loader** | Auto-discover Python packages in `/home/paw/plugins/`. Each has `plugin.yaml` + `__init__.py`. Loaded on startup |
| 3.2 | **Plugin base class** | `PawPlugin`: `name`, `version`, `description`, `tools[]`, `on_startup()`, `on_shutdown()` |
| 3.3 | **Coder plugin** | PAW's self-building tool. Can: scaffold new plugins, write Python code, run tests in subprocess, create proposals |
| 3.4 | **Proposal system** | When PAW builds something: code + description + test results → saved as proposal. `paw proposals` CLI to list, `paw proposals approve <id>` to activate |
| 3.5 | **Guardrails** | PAW can only write to `/home/paw/plugins/` and `/home/paw/workspace/`. Cannot touch `/app/src/`. Enforced in file tool |
| 3.6 | **Example plugin** | Ship a `hello-world` plugin as a template PAW can reference |

**Milestone:** `paw chat "build me a plugin that checks if a website is up"` → PAW writes it → `paw proposals approve 1` → plugin is live.

---

### Phase 4 — Polish & Launch (Tonight, Hour 5-6)
> Make it solid enough to leave running.

| # | Task | Details |
|---|------|---------|
| 4.1 | **Error handling** | Graceful LLM failures (retry + backoff). Meaningful errors in CLI |
| 4.2 | **`.env.example` + `paw.yaml.example`** | Documented example configs |
| 4.3 | **README.md** | Quick start: clone → configure → `docker compose up` → `paw chat`. 5 minutes |
| 4.4 | **Default soul.md** | Well-crafted identity document. Sets PAW's personality, values, self-building principles |
| 4.5 | **Smoke test** | End-to-end: boot → chat → use tools → build a plugin → approve it → use it. All works |

**Milestone:** Leave it running. Come back tomorrow. Ask PAW to build a Telegram bot plugin. It does.

---

## Post-Launch Roadmap (PAW builds these itself)

Once PAW is running, these become tasks you *ask PAW to do*:

| Priority | Feature | How PAW builds it |
|----------|---------|-------------------|
| 1 | **Web UI** | "Build a web UI plugin with HTMX that serves on port 8000/ui" |
| 2 | **Telegram bot** | "Build a Telegram bot plugin. Here's the bot token: ..." |
| 3 | **Email integration** | "Build an email plugin. IMAP: ..., SMTP: ..." |
| 4 | **MCP client** | "Build a plugin that connects to MCP servers" |
| 5 | **Scheduled tasks** | "Build a cron plugin so you can do things on a schedule" |
| 6 | **GitHub integration** | "Build a plugin that watches my repos for issues" |
| 7 | **Cost dashboard** | "Build a plugin that tracks LLM costs and shows a report" |
| 8 | **Whatever you need** | Just ask. PAW figures it out |

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Language | Python 3.12+ | AI ecosystem, LiteLLM native |
| Framework | FastAPI | Async, auto-docs, Pydantic |
| LLM Gateway | LiteLLM | 100+ models, OpenAI-compatible |
| Database | SQLite (aiosqlite) | Zero-config, single file |
| Config | Pydantic Settings | `.env` + YAML, validated |
| Logging | structlog | Structured JSON |
| Container | Docker (Ubuntu 22.04) | Full Linux OS |
| CLI | click or typer | Clean CLI framework |
| Testing | pytest + httpx | Async-native |
| Linting | Ruff | All-in-one |

---

## Project Structure

```
paw/
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── pyproject.toml
├── paw.yaml.example
├── .env.example
├── README.md
├── soul.md                       # PAW's identity document (default)
│
├── src/paw/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app + lifespan
│   ├── config.py                 # Pydantic settings
│   │
│   ├── llm/
│   │   └── gateway.py            # LiteLLM async wrapper
│   │
│   ├── agent/
│   │   ├── loop.py               # ReAct agent loop
│   │   ├── tools.py              # Tool base class + registry
│   │   ├── memory.py             # Key-value memory (tool)
│   │   ├── conversation.py       # Conversation state
│   │   └── soul.py               # soul.md loader & injector
│   │
│   ├── tools/
│   │   ├── shell.py              # Shell command execution
│   │   └── files.py              # File read/write/list
│   │
│   ├── extensions/
│   │   ├── base.py               # PawPlugin base class
│   │   ├── loader.py             # Plugin auto-discovery
│   │   └── registry.py           # Central tool registry
│   │
│   ├── coder/
│   │   ├── engine.py             # Code writing + execution
│   │   ├── scaffold.py           # Plugin boilerplate generator
│   │   └── proposals.py          # Proposal workflow
│   │
│   ├── db/
│   │   ├── engine.py             # SQLite async
│   │   └── models.py             # Schemas
│   │
│   ├── api/
│   │   ├── routes/
│   │   │   ├── chat.py           # /v1/chat/completions
│   │   │   └── health.py         # /health
│   │   └── middleware/
│   │       └── auth.py           # API key
│   │
│   └── cli/
│       └── main.py               # paw chat, paw status, etc.
│
├── plugins/                      # User & self-built plugins
│   └── hello_world/
│       ├── plugin.yaml
│       └── __init__.py
│
└── tests/
    ├── test_agent.py
    ├── test_tools.py
    └── test_coder.py
```

---

## Multi-User Model

```
You    ──→ terminal ──→ [ PAW Container (yours) ]
Alice  ──→ terminal ──→ [ PAW Container (hers)  ]
Bob    ──→ terminal ──→ [ PAW Container (his)   ]
```

Each is fully isolated. One container = one PAW = one person.

---

## Safety Model

| Layer | Protection |
|-------|-----------|
| **Core code** | Read-only `/app/src/`. PAW cannot self-modify core. Upgrades = new image |
| **Plugins** | PAW writes to `/home/paw/plugins/` only. All new code goes through proposals |
| **Shell** | Configurable blocklist. Optional approval mode for dangerous commands |
| **Files** | Whitelist of writable directories. Core + system dirs are off-limits |
| **Identity** | PAW uses its own accounts only. Never impersonates user |
| **Costs** | Per-request and daily token budgets. Configurable in `paw.yaml` |
| **soul.md** | PAW can propose changes to its soul, never apply without approval |

---

## Tonight's Timeline

| Hour | What | Milestone |
|------|------|-----------|
| 1 | Phase 0 — Skeleton | Container boots, LLM responds, soul.md loaded |
| 2-3 | Phase 1 — Brain | Agent loop, shell + file tools, memory |
| 3-4 | Phase 2 — CLI + DB | `paw chat` works, conversations persist |
| 4-5 | Phase 3 — Self-building | Coder plugin, proposal system, plugin loader |
| 5-6 | Phase 4 — Polish | Error handling, README, smoke test |
| 🚀 | **Launch** | PAW is alive. Leave it running. Come back tomorrow and ask it to build a web UI |

**Let's go.** 🐾
