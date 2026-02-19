# 🐾 PAW — Your Personal Autonomous AI Agent (Cloud-Ready)

PAW is a self-hosted AI agent you can run in the cloud, control from CLI/API/Telegram, and extend with plugins.

Simple to start. Lightweight by default. Flexible when you need more.

---

## Why PAW

Most AI agent products are either too rigid or too heavy to run your way.

PAW gives you a better path:

- **Simple**: get from clone to working agent in minutes
- **Lightweight**: focused core, practical tools, no bloated platform
- **Flexible**: use the model/provider you want via LiteLLM (OpenAI, Anthropic, Google, Ollama, Azure, and more)
- **Personal**: your memory, your plugins, your cloud environment

> PAW is your small autonomous cloud worker — always on, always yours.

---

## What you get

- **Agent runtime** with Think → Act → Observe loop
- **Tooling built in**: shell, files, memory, automation, coder
- **Dual memory**: persistent key-value + markdown memory logs
- **Secure defaults**: filesystem sandboxing, command restrictions, approval patterns, token budgets
- **Multi-channel control**: CLI, HTTP API, Telegram channel runtime, inbound webhooks
- **Plugin architecture**: drop new capabilities into `plugins/`

---

## 60-Second Quick Start

### 1) Configure

```bash
git clone <your-repo-url> paw
cd paw

# create .env and set at least your model API key
# example values are documented below
```

### 2) Run

```bash
docker compose up -d
```

### 3) Talk to PAW

```bash
pip install -e .

paw chat "Hello PAW"
paw status
```

### 4) Use API

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Summarize my current workspace"}],
    "agent_mode": true
  }'
```

---

## Lightweight by design

PAW keeps the core focused and small:

- FastAPI service
- Agent loop
- Tool registry
- Plugin loader
- PostgreSQL-backed state

No mandatory UI, no monolith, no vendor lock-in.

---

## Flexible in production

PAW is built to run where you run:

- Local Docker for development
- Cloud VM/container host
- Azure Container Apps (Bicep + GitHub deployment workflow included)

Deployment assets:

- `infra/azure/main.bicep`
- `.github/workflows/deploy-azure.yml`
- `docs/azure-deployment.md`

---

## Core capabilities

| Capability | What it does |
|---|---|
| **Shell** | Executes commands in PAW's Linux runtime with blocked-command and approval safeguards |
| **Files** | Reads/writes/searches files inside approved directories only |
| **Memory** | Stores and recalls persistent facts across conversations |
| **Automation** | Runs heartbeat checks and scheduled cron-style tasks |
| **Coder** | Scaffolds plugin ideas and implementation proposals |

---

## Automation that actually helps

PAW includes proactive automation out of the box:

- **Heartbeat cadence** (default every 5 minutes)
- **Checklist source**: `heartbeat.md`
- **Scheduled jobs** via automation skill
- **Explicit routing** per job with `output_target` (for example `telegram` or `email`)

Examples:

```bash
paw chat "Check my repo health every hour and send updates to telegram"
paw chat "Summarize open TODOs every 30 minutes and send to email"
```

---

## Built for safe autonomy

PAW is designed to operate with guardrails:

- File access restricted to approved writable zones (`workspace/`, `plugins/`, `data/`, `/tmp`)
- Path traversal blocked
- Dangerous shell patterns rejected unless explicitly approved
- Optional API authentication via `X-API-Key`
- Request/day token budgets
- Output truncation for shell and file reads

---

## Memory that persists

PAW uses two complementary memory layers:

1. **Key-value memory (MemSearch-backed)**
2. **Markdown memory files** (`MEMORY.md` + recent daily logs)

This keeps context durable without letting prompts grow unbounded.

---

## Channels: CLI, API, Telegram, Webhooks

PAW supports multiple ways to interact:

- CLI for fast local/operator workflows
- OpenAI-compatible chat API endpoint
- Telegram polling runtime with per-chat mode controls
- Inbound webhook endpoint for external event ingestion

Useful endpoints:

- `GET /health`
- `GET /v1/channels/status`
- `POST /v1/channels/{channel}/sessions/{session_key}/mode`
- `POST /v1/webhooks/inbound`

---

## Plugin ecosystem

Drop plugins in `plugins/<name>/` with:

- `plugin.yaml` metadata
- `__init__.py` plugin class

Included example: `plugins/brave_search` (adds a `web_search` tool when `PAW_BRAVE_API_KEY` is set).

---

## Minimal config

Set these in `.env`:

```bash
PAW_LLM__API_KEY=sk-...
PAW_LLM__MODEL=openai/gpt-4o-mini
PAW_LLM__SMART_MODEL=openai/gpt-5.2
PAW_DATABASE_URL=postgresql://paw:paw@postgres:5432/paw?sslmode=disable
PAW_API_KEY=change-me-strong-key
```

Optional:

```bash
PAW_BRAVE_API_KEY=...
PAW_TELEGRAM_ENABLED=true
PAW_TELEGRAM_BOT_TOKEN=123456789:your-token
```

See `paw.yaml.example` for full config options.

---

## Development

```bash
pip install -e ".[dev]"
paw serve --reload
pytest
ruff check src/
```

---

## Philosophy

PAW is intentionally **brain-first**:

- small core
- strong tooling
- secure boundaries
- extensibility through plugins

You ship one reliable autonomous agent, then let it grow with your needs.

---

Built with ❤️ and a healthy amount of tokens. Mascot: Chips the wiener dog 🌭# 🐾 PAW — Personal Agent Workspace

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