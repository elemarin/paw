# PAW Plugin Development Guide

This guide explains how to build production-quality PAW plugins from scratch.

## 1) How plugin loading works

At startup, PAW scans the plugins directory (default: `/home/paw/plugins`).

For each plugin folder, PAW expects:

- `plugin.yaml` (metadata)
- an entry-point Python module (usually `__init__.py`)
- a class that inherits `PawPlugin`
- one or more `Tool` classes registered in `on_load()`

If no `PawPlugin` subclass exists, PAW logs `plugins.no_class` and skips that plugin.

---

## 2) Minimum folder structure

Create a folder named after your plugin:

- `/home/paw/plugins/weatherplugin/plugin.yaml`
- `/home/paw/plugins/weatherplugin/__init__.py`

In repo defaults, place plugins under:

- `plugins/<plugin_name>/...`

---

## 3) Metadata file (`plugin.yaml`)

Example:

```yaml
name: weatherplugin
description: Fetch current weather for a city
version: 0.1.0
author: you
entry_point: __init__
```

Notes:

- `entry_point: __init__` means PAW loads `__init__.py`.
- If `entry_point: weather`, PAW loads `weather.py`.

---

## 4) Python implementation contract

A plugin must implement:

1. a `Tool` subclass (or multiple)
2. a `PawPlugin` subclass
3. `on_load()` that returns tool instances

### Complete example

```python
from __future__ import annotations

from typing import Any

import httpx

from paw.agent.tools import Tool, ToolRegistry
from paw.extensions.base import PawPlugin


class WeatherTool(Tool):
    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "Get current weather for a city"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name, e.g. London",
                }
            },
            "required": ["city"],
        }

    async def execute(self, city: str) -> str:
        # Replace this with your real API endpoint + key handling
        async with httpx.AsyncClient(timeout=15) as client:
            # Dummy example payload pattern
            # resp = await client.get("https://api.example.com/weather", params={"q": city})
            # resp.raise_for_status()
            # data = resp.json()
            # return f"{city}: {data['temp_c']}°C, {data['condition']}"
            return f"{city}: weather lookup not configured yet"


class WeatherPlugin(PawPlugin):
    @property
    def name(self) -> str:
        return "weatherplugin"

    @property
    def description(self) -> str:
        return "Fetch weather information"

    @property
    def version(self) -> str:
        return "0.1.0"

    async def on_load(self, registry: ToolRegistry, db=None) -> list[Tool]:
        return [WeatherTool()]
```

---

## 5) Dependency management

If plugin code imports external libraries (`bs4`, `requests`, etc.), install them in the PAW runtime image.

Recommended: add dependencies to project dependencies in `pyproject.toml` so they persist across rebuilds.

If you install packages manually in a running container, they can be lost after rebuilds.

---

## 6) Local test loop

1. Edit plugin files.
2. Restart PAW container.
3. Check logs for plugin loader messages.
4. Call chat endpoint and ask PAW to use your tool.

Expected successful logs include:

- `plugins.loaded`
- `tool.registered`

Failure logs to interpret:

- `plugins.no_entry`: wrong `entry_point` or missing Python file
- `plugins.no_class`: no class inheriting `PawPlugin`
- `plugins.load_failed`: import/runtime exception in plugin module

---

## 7) Common mistakes and fixes

### Mistake: plain class like `class WeatherPlugin:` without inheriting `PawPlugin`

Fix: `class WeatherPlugin(PawPlugin):` and implement `on_load()`.

### Mistake: helper methods exist but no `Tool` subclass

Fix: create a `Tool` class with `name`, `description`, `parameters`, and `execute()`.

### Mistake: using blocking I/O heavily

Fix: prefer async clients (`httpx.AsyncClient`) inside `execute()`.

### Mistake: missing dependencies (`No module named ...`)

Fix: add dependency to `pyproject.toml`, rebuild container.

---

## 8) Production checklist

- Clear tool name and JSON schema
- Input validation in `execute()`
- Timeouts on network requests
- Safe error messages (no secrets)
- Idempotent behavior where possible
- Version bump in `plugin.yaml` when behavior changes

---

## 9) Reference implementation

See the built-in sample plugin:

- `plugins/hello_world/plugin.yaml`
- `plugins/hello_world/__init__.py`

This is the canonical template for new plugins.
