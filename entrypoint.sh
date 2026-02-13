#!/bin/bash
set -e

echo "🐾 PAW — Personal Agent Workspace"
echo "=================================="

# Initialize data directories
mkdir -p /home/paw/data /home/paw/plugins /home/paw/workspace

# Copy default soul.md on first boot
if [ ! -f /home/paw/soul.md ]; then
    echo "📜 First boot — installing default soul.md"
    cp /app/soul.md /home/paw/soul.md
fi

# Copy default plugins on first boot
if [ ! -f /home/paw/plugins/.initialized ]; then
    echo "🔌 First boot — installing default plugins"
    cp -r /app/default-plugins/* /home/paw/plugins/ 2>/dev/null || true
    touch /home/paw/plugins/.initialized
fi

# Copy example config if none exists
if [ ! -f /home/paw/paw.yaml ]; then
    echo "⚙️  No paw.yaml found — using defaults (configure via env vars)"
fi

echo ""
echo "🧠 Model: ${PAW_LLM__MODEL:-openai/gpt-4o-mini}"
echo "📁 Data:  /home/paw/data"
echo "🔌 Plugins: /home/paw/plugins"
echo "💼 Workspace: /home/paw/workspace"
echo "📜 Soul: /home/paw/soul.md"
echo ""
echo "🚀 Starting PAW server on port ${PAW_PORT:-8000}..."
echo ""

# Start the server
exec python -m uvicorn paw.main:app \
    --host "${PAW_HOST:-0.0.0.0}" \
    --port "${PAW_PORT:-8000}" \
    --log-level warning
