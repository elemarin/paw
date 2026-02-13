"""Brave web search plugin for PAW."""

from __future__ import annotations

import os
from typing import Any

import httpx

from paw.agent.tools import Tool, ToolRegistry
from paw.extensions.base import PawPlugin


class WebSearchTool(Tool):
    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the public web and return top results with titles, links, and snippets."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. 'latest Python 3.13 features'",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of results to return (1-10). Default: 5",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, count: int = 5) -> str:
        query = (query or "").strip()
        if not query:
            return "Error: query is required."

        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 5
        count = max(1, min(10, count))

        api_key = os.getenv("PAW_BRAVE_API_KEY", "").strip() or os.getenv("BRAVE_API_KEY", "").strip()
        if not api_key:
            return (
                "Error: Brave API key is missing. "
                "Set PAW_BRAVE_API_KEY (or BRAVE_API_KEY) in your environment."
            )

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        }
        params = {
            "q": query,
            "count": count,
            "text_decorations": False,
            "search_lang": "en",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPStatusError as e:
            return f"Error: Brave Search API request failed with status {e.response.status_code}."
        except Exception as e:
            return f"Error fetching search results: {type(e).__name__}: {e}"

        results = (payload.get("web") or {}).get("results") or []
        if not results:
            return f"No web results found for: {query}"

        lines = [f"Top {min(len(results), count)} web results for: {query}"]
        for idx, item in enumerate(results[:count], start=1):
            title = (item.get("title") or "(no title)").strip()
            url = (item.get("url") or "").strip()
            snippet = (item.get("description") or "").strip()
            lines.append(f"{idx}. {title}")
            if url:
                lines.append(f"   URL: {url}")
            if snippet:
                lines.append(f"   Snippet: {snippet}")

        return "\n".join(lines)


class BraveSearchPlugin(PawPlugin):
    @property
    def name(self) -> str:
        return "brave_search"

    @property
    def description(self) -> str:
        return "Search the web using Brave Search API"

    @property
    def version(self) -> str:
        return "0.1.0"

    async def on_load(self, registry: ToolRegistry, db=None) -> list[Tool]:
        return [WebSearchTool()]