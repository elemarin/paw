"""Weather plugin for PAW.

Provides a `weather` tool that fetches current weather for a city.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from paw.agent.tools import Tool, ToolRegistry
from paw.extensions.base import PawPlugin


class WeatherTool(Tool):
    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "Get current weather for a city."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name, e.g. 'Dubai' or 'London'",
                }
            },
            "required": ["city"],
        }

    async def execute(self, city: str) -> str:
        city = (city or "").strip()
        if not city:
            return "Error: city is required."

        url = f"https://wttr.in/{quote(city)}?format=j1"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return f"Error fetching weather: {type(e).__name__}: {e}"

        try:
            current = data["current_condition"][0]
            temp_c = current.get("temp_C", "?")
            feels_c = current.get("FeelsLikeC", "?")
            humidity = current.get("humidity", "?")
            desc = current.get("weatherDesc", [{}])[0].get("value", "unknown")
            return (
                f"{city}: {desc}, {temp_c}°C (feels {feels_c}°C), "
                f"humidity {humidity}%"
            )
        except Exception as e:
            return f"Error parsing weather data: {type(e).__name__}: {e}"


class WeatherPlugin(PawPlugin):
    @property
    def name(self) -> str:
        return "weatherplugin"

    @property
    def description(self) -> str:
        return "Fetch current weather for a city"

    @property
    def version(self) -> str:
        return "0.1.0"

    async def on_load(self, registry: ToolRegistry, db=None) -> list[Tool]:
        return [WeatherTool()]
