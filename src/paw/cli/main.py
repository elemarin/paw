"""PAW CLI — command-line interface for interacting with the agent."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="paw",
    help="PAW — Personal Agent Workspace",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()

DEFAULT_URL = "http://localhost:8000"

# File to persist the last conversation ID for --last
_LAST_CONV_FILE = ".paw_last_conversation"

_WIZARD_SECRET_MAP = {
    "PAW_LLM_API_KEY": "PAW_LLM__API_KEY",
    "PAW_API_KEY": "PAW_API_KEY",
    "PAW_TELEGRAM_BOT_TOKEN": "PAW_TELEGRAM_BOT_TOKEN",
}

_WIZARD_VAR_MAP = {
    "PAW_TELEGRAM_DM_POLICY": "PAW_TELEGRAM_DM_POLICY",
    "PAW_TELEGRAM_ALLOW_FROM": "PAW_TELEGRAM_ALLOW_FROM",
    "AZURE_RESOURCE_GROUP": "AZURE_RESOURCE_GROUP",
    "AZURE_LOCATION": "AZURE_LOCATION",
    "AZURE_NAME_PREFIX": "AZURE_NAME_PREFIX",
    "AZURE_VM_ADMIN_USERNAME": "AZURE_VM_ADMIN_USERNAME",
}


def _get_client(base_url: str, api_key: str | None) -> httpx.Client:
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    return httpx.Client(base_url=base_url, headers=headers, timeout=120.0)


def _save_last_conversation(conv_id: str) -> None:
    """Persist the last conversation ID so --last can resume it."""
    try:
        from pathlib import Path
        Path(_LAST_CONV_FILE).write_text(conv_id, encoding="utf-8")
    except Exception:
        pass


def _load_last_conversation() -> str | None:
    """Load the last conversation ID."""
    try:
        from pathlib import Path
        p = Path(_LAST_CONV_FILE)
        if p.exists():
            return p.read_text(encoding="utf-8").strip() or None
    except Exception:
        pass
    return None


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _merge_template_env(template_lines: list[str], values: dict[str, str]) -> str:
    output: list[str] = []
    for raw in template_lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key, _, current = line.partition("=")
        env_key = key.strip()
        if env_key in values and values[env_key] != "":
            output.append(f"{env_key}={values[env_key]}")
        else:
            output.append(f"{env_key}={current}")
    return "\n".join(output).rstrip() + "\n"


@app.command()
def chat(
    message: str | None = typer.Argument(None, help="Message to send to PAW (omit for interactive mode)"),
    base_url: str = typer.Option(DEFAULT_URL, "--url", "-u", envvar="PAW_URL"),
    api_key: str = typer.Option("", "--api-key", "-k", envvar="PAW_API_KEY"),
    conversation_id: str = typer.Option("", "--conversation", "-c", help="Resume a conversation by ID"),
    last: bool = typer.Option(False, "--last", "-l", help="Continue the last conversation"),
    new: bool = typer.Option(False, "--new", help="Start a new conversation (ignore last conversation)"),
    no_agent: bool = typer.Option(False, "--no-agent", help="Simple proxy mode (no tools)"),
    model: str = typer.Option("", "--model", "-m", help="Override model"),
    smart: bool = typer.Option(
        False,
        "--smart",
        help="Use configured smart model",
    ),
    raw: bool = typer.Option(False, "--raw", help="Output raw JSON response"),
) -> None:
    """Send a message to PAW and get a response."""
    client = _get_client(base_url, api_key or None)

    # Resolve conversation ID:
    # - default behavior continues last conversation if available
    if not conversation_id and not new:
        conversation_id = _load_last_conversation() or ""
        if last and not conversation_id:
            console.print("[yellow]No previous conversation found. Starting new one.[/yellow]")

    def _send(message_text: str, current_conversation_id: str) -> dict:
        payload: dict = {
            "messages": [{"role": "user", "content": message_text}],
            "agent_mode": not no_agent,
            "smart_mode": smart,
        }
        if current_conversation_id:
            payload["conversation_id"] = current_conversation_id
        if model:
            payload["model"] = model

        try:
            resp = client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
        except httpx.ConnectError:
            console.print(f"[red]Error:[/red] Cannot connect to PAW at {base_url}")
            console.print("Is the server running? Start it with: docker compose up -d")
            raise typer.Exit(1)
        except httpx.HTTPStatusError as e:
            console.print(f"[red]Error {e.response.status_code}:[/red] {e.response.text}")
            raise typer.Exit(1)

        return resp.json()

    def _render_response(data: dict) -> str:
        if raw:
            console.print_json(json.dumps(data, indent=2))
        else:
            content = data["choices"][0]["message"]["content"]
            tools = data.get("tool_calls_made", 0)
            conv_id = data.get("conversation_id", "")

            console.print()
            console.print(Markdown(content))
            console.print()

            meta_parts = []
            if conv_id:
                meta_parts.append(f"conversation: {conv_id[:8]}")
            if tools:
                meta_parts.append(f"tool calls: {tools}")
            if data.get("usage"):
                meta_parts.append(f"tokens: {data['usage'].get('total_tokens', '?')}")
            if meta_parts:
                console.print(f"[dim]{'  │  '.join(meta_parts)}[/dim]")

        return data.get("conversation_id", "")

    # One-shot mode
    if message is not None:
        data = _send(message, conversation_id)
        conv_id = _render_response(data)
        if conv_id:
            _save_last_conversation(conv_id)
        return

    # Interactive mode
    console.print("[bold cyan]PAW interactive chat[/bold cyan]  [dim](type /exit to quit, /new to start fresh)[/dim]")
    while True:
        try:
            prompt = "[bold green]you[/bold green]"
            if conversation_id:
                prompt += f" [dim]{conversation_id[:8]}[/dim]"
            user_input = console.input(f"{prompt}> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in {"/exit", "/quit", "exit", "quit"}:
            console.print("[dim]bye[/dim]")
            break
        if user_input.lower() == "/new":
            conversation_id = ""
            console.print("[yellow]Started a new conversation.[/yellow]")
            continue

        data = _send(user_input, conversation_id)
        conv_id = _render_response(data)
        if conv_id:
            conversation_id = conv_id
            _save_last_conversation(conv_id)


@app.command()
def status(
    base_url: str = typer.Option(DEFAULT_URL, "--url", "-u", envvar="PAW_URL"),
    api_key: str = typer.Option("", "--api-key", "-k", envvar="PAW_API_KEY"),
) -> None:
    """Check PAW's status."""
    client = _get_client(base_url, api_key or None)

    try:
        resp = client.get("/health")
        resp.raise_for_status()
    except httpx.ConnectError:
        console.print(f"[red]✗[/red] PAW is not running at {base_url}")
        raise typer.Exit(1)

    data = resp.json()

    table = Table(title="🐾 PAW Status", show_header=False, border_style="blue")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Status", f"[green]{data['status']}[/green]")
    table.add_row("Version", data.get("version", "?"))
    table.add_row("Uptime", data.get("uptime", "?"))
    table.add_row("Model", data.get("model", "?"))

    if "llm_stats" in data:
        stats = data["llm_stats"]
        table.add_row("Requests", str(stats.get("request_count", 0)))
        table.add_row("Tokens Used", str(stats.get("total_tokens", 0)))
        table.add_row("Cost", stats.get("total_cost", "$0"))

    if "plugin_count" in data:
        table.add_row("Plugins", str(data["plugin_count"]))

    console.print()
    console.print(table)
    console.print()


@app.command()
def conversations(
    base_url: str = typer.Option(DEFAULT_URL, "--url", "-u", envvar="PAW_URL"),
    api_key: str = typer.Option("", "--api-key", "-k", envvar="PAW_API_KEY"),
) -> None:
    """List all conversations."""
    client = _get_client(base_url, api_key or None)

    try:
        resp = client.get("/v1/conversations")
        resp.raise_for_status()
    except httpx.ConnectError:
        console.print(f"[red]✗[/red] PAW is not running at {base_url}")
        raise typer.Exit(1)
    except httpx.HTTPStatusError:
        console.print("[yellow]No conversations endpoint available yet.[/yellow]")
        raise typer.Exit(0)

    data = resp.json()

    if not data:
        console.print("[dim]No conversations yet.[/dim]")
        return

    table = Table(title="Conversations", border_style="blue")
    table.add_column("ID", style="cyan", max_width=10)
    table.add_column("Title")
    table.add_column("Messages", justify="right")
    table.add_column("Created")

    for conv in data:
        table.add_row(
            conv["id"][:8] + "...",
            conv.get("title", "Untitled")[:50],
            str(conv.get("message_count", 0)),
            conv.get("created_at", "")[:16],
        )

    console.print()
    console.print(table)
    console.print()


@app.command()
def memory(
    action: str = typer.Argument("list", help="Action: list, get, set, delete"),
    key: str = typer.Argument("", help="Memory key"),
    value: str = typer.Argument("", help="Value (for 'set' action)"),
    base_url: str = typer.Option(DEFAULT_URL, "--url", "-u", envvar="PAW_URL"),
    api_key: str = typer.Option("", "--api-key", "-k", envvar="PAW_API_KEY"),
) -> None:
    """Manage PAW's persistent memory."""
    client = _get_client(base_url, api_key or None)

    try:
        if action == "list":
            resp = client.get("/v1/memory")
            resp.raise_for_status()
            data = resp.json()

            if not data:
                console.print("[dim]No memories stored.[/dim]")
                return

            table = Table(title="🧠 Stored Memories", border_style="blue")
            table.add_column("Key", style="cyan")
            table.add_column("Value")

            for item in data:
                table.add_row(item["key"], item["value"])

            console.print()
            console.print(table)
            console.print()

        elif action == "get":
            if not key:
                console.print("[red]Usage: paw memory get <key>[/red]")
                raise typer.Exit(1)
            resp = client.get(f"/v1/memory/{key}")
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                console.print(f"[yellow]No memory found for key '{key}'[/yellow]")
            else:
                console.print(f"[cyan]{data['key']}[/cyan] = {data['value']}")

        elif action == "set":
            if not key or not value:
                console.print("[red]Usage: paw memory set <key> <value>[/red]")
                raise typer.Exit(1)
            resp = client.put("/v1/memory", json={"key": key, "value": value})
            resp.raise_for_status()
            console.print(f"[green]✓[/green] Remembered: {key} = {value}")

        elif action == "delete":
            if not key:
                console.print("[red]Usage: paw memory delete <key>[/red]")
                raise typer.Exit(1)
            resp = client.delete(f"/v1/memory/{key}")
            resp.raise_for_status()
            console.print(f"[green]✓[/green] Forgot: {key}")

        else:
            console.print("[red]Unknown action. Use: list, get, set, delete[/red]")
            raise typer.Exit(1)

    except httpx.ConnectError:
        console.print(f"[red]✗[/red] PAW is not running at {base_url}")
        raise typer.Exit(1)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Start the PAW server (for development)."""
    import uvicorn
    console.print(Panel("🐾 Starting PAW server...", border_style="blue"))
    uvicorn.run(
        "paw.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def version() -> None:
    """Show PAW version."""
    from paw import __version__
    console.print(f"🐾 PAW v{__version__}")


@app.command()
def wizard(
    env_file: str = typer.Option(".env", "--env-file", help="Target env file"),
    template_file: str = typer.Option(".env.example", "--template", help="Template env file"),
    force: bool = typer.Option(False, "--force", help="Overwrite target env file without prompt"),
    github_script: str = typer.Option(
        "workspace/setup/apply-github-config.ps1",
        "--github-script",
        help="Path to generated GitHub bootstrap script",
    ),
) -> None:
    """Bootstrap .env and generate GitHub secrets/variables helper script."""
    template_path = Path(template_file)
    target_path = Path(env_file)

    if not template_path.exists():
        console.print(f"[red]Template not found:[/red] {template_path}")
        raise typer.Exit(1)

    if target_path.exists() and not force:
        proceed = typer.confirm(f"{target_path} exists. Update it from template and keep existing values?")
        if not proceed:
            raise typer.Exit(0)

    template_lines = template_path.read_text(encoding="utf-8").splitlines()
    values = _parse_env_file(target_path)

    prompts = [
        "PAW_LLM__API_KEY",
        "PAW_LLM__MODEL",
        "PAW_LLM__SMART_MODEL",
        "PAW_API_KEY",
        "PAW_TELEGRAM_BOT_TOKEN",
        "PAW_TELEGRAM_DEFAULT_CHAT_ID",
        "AZURE_RESOURCE_GROUP",
        "AZURE_LOCATION",
        "AZURE_NAME_PREFIX",
        "AZURE_VM_ADMIN_USERNAME",
    ]
    for key in prompts:
        existing = values.get(key, "")
        entered = typer.prompt(f"{key}", default=existing, show_default=bool(existing))
        values[key] = entered.strip()

    rendered = _merge_template_env(template_lines, values)
    target_path.write_text(rendered, encoding="utf-8")
    console.print(f"[green]✓[/green] Wrote {target_path}")

    script_path = Path(github_script)
    script_path.parent.mkdir(parents=True, exist_ok=True)

    script_lines = [
        "$ErrorActionPreference = 'Stop'",
        "if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }",
        "",
    ]
    for gh_name, env_name in _WIZARD_SECRET_MAP.items():
        value = values.get(env_name, "").strip()
        if value:
            escaped = value.replace("`", "``").replace('"', '`"')
            script_lines.append(f'gh secret set {gh_name} --body "{escaped}"')
    for gh_name, env_name in _WIZARD_VAR_MAP.items():
        value = values.get(env_name, "").strip()
        if value:
            escaped = value.replace("`", "``").replace('"', '`"')
            script_lines.append(f'gh variable set {gh_name} --body "{escaped}"')

    script_path.write_text("\n".join(script_lines).rstrip() + "\n", encoding="utf-8")
    console.print(f"[green]✓[/green] Wrote {script_path}")
    console.print("Run the script to push env-derived values to GitHub repo vars/secrets.")


def main() -> None:
    """Entrypoint."""
    app()


if __name__ == "__main__":
    main()
