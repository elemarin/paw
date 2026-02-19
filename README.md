# 🐾 PAW — Personal Agent Workspace

```
                            __
     ,                    ," e`--o
    ((                   (  | __,'
     \~----------------' \_;/
     (                      /
     /) ._______________.  )
    (( (               (( (
     ``-'               ``-'
```

**Your self-hosted AI agent. Always on. Always yours. Built different.** 🐾

PAW is an autonomous AI agent you deploy once and talk to forever — via Telegram, CLI, API, or webhooks. It has memory, can run code, build its own plugins, and actually gets stuff done. Think less "AI chatbot" and more "overcaffeinated tech-savvy dog that never sleeps."

Open source. Self-hosted. No subscriptions. No data leaving your infra unless *you* say so.

---

## why PAW hits different

Most AI agent platforms are either locked down SaaS or a 40-file framework nightmare to self-host. PAW is neither.

- **Clone to running in under 5 minutes** — seriously, it's just Docker
- **Bring your own model** — OpenAI, Anthropic, Gemini, Ollama, Azure, whatever. LiteLLM handles it.
- **Your memory, your plugins, your rules** — nothing phoning home
- **Grows with you** — PAW can literally build its own new capabilities as plugins

> PAW is the personal AI agent for people who want power without the platform tax.

---

## what's in the box

| What | Why it slaps |
|---|---|
| **Shell** | Runs commands in PAW's Linux env with guardrails so it doesn't nuke your stuff |
| **Files** | Reads/writes inside approved dirs only — no path traversal nonsense |
| **Memory** | Remembers things across conversations. Actually. For real. |
| **Automation** | Heartbeat tasks, cron jobs, proactive check-ins — set it and forget it |
| **Coder** | Scaffolds new plugins. PAW can teach itself new tricks. |
| **Channels** | CLI, HTTP API, Telegram, webhooks — talk to it however you want |

---

## quick start (for real, it's quick)

```bash
git clone <your-repo-url> paw && cd paw
# drop your API key in .env
docker compose up -d
```

That's it. PAW is running.

**Talk to it:**

```bash
pip install -e .
paw chat "hey what can you do"
```

**Or hit the API:**

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "summarize my workspace"}], "agent_mode": true}'
```

---

## memory that actually works

PAW uses two layers so it never forgets the important stuff — without letting the prompt balloon into a novel:

1. **Key-value memory** — fast retrieval of facts, preferences, context
2. **Markdown memory logs** — `MEMORY.md` + rolling daily logs

---

## automation that runs while you sleep

```bash
paw chat "check repo health every hour, bark at me on telegram if something's off"
paw chat "summarize open TODOs every morning at 9am"
```

- Heartbeat cadence (default: every 5 min)
- Cron-style scheduled jobs
- Output routing per job (`telegram`, `email`, wherever)

---

## guardrails, not a leash

PAW operates autonomously but isn't reckless:

- File access locked to approved zones (`workspace/`, `plugins/`, `data/`, `/tmp`)
- Dangerous shell patterns flagged and blocked unless you explicitly approve
- Optional API key auth (`X-API-Key`)
- Token budgets per request and per day
- Approval step before any plugin ships

---

## plugin system — PAW learns new tricks

Drop a folder in `plugins/<name>/` with `plugin.yaml` + `__init__.py` and PAW picks it up automatically.

Or just ask PAW to build one:

```bash
paw chat "build me a plugin that checks HackerNews top stories"
```

It'll scaffold, test, and propose it for approval. You ship it, it's live.

Included starter: `plugins/brave_search` — web search when `PAW_BRAVE_API_KEY` is set.

---

## deploy anywhere

- **Local**: Docker Compose, works immediately
- **Cloud**: Azure Container Apps with included Bicep + GitHub Actions workflow
  - `infra/azure/main.bicep`
  - `docs/azure-deployment.md`

---

## minimal `.env` to get going

```bash
PAW_LLM__API_KEY=sk-...
PAW_LLM__MODEL=openai/gpt-4o-mini
PAW_DATABASE_URL=postgresql://paw:pawssword@postgres:5432/paw?sslmode=disable
PAW_API_KEY=change-me-strong-key
```

Optional extras:

```bash
PAW_BRAVE_API_KEY=...          # web search
PAW_TELEGRAM_ENABLED=true      # telegram channel
PAW_TELEGRAM_BOT_TOKEN=...     # your bot token
PAW_LLM__SMART_MODEL=...       # bigger model for heavy tasks
```

Full options: see `paw.yaml.example`.

---

## dev setup

```bash
pip install -e ".[dev]"
paw serve --reload
pytest
ruff check src/
```

---

## the vibe

PAW is **brain-first**: tiny core, strong tooling, hard boundaries, and infinite extensibility via plugins. No bloated platform. No vendor lock-in. No subscription.

---

* built with ❤️ and an irresponsible number of tokens*