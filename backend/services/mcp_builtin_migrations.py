"""Narrow migrations for untouched built-in launch commands.

Do not replace customized launchers, profiles, environments or source URLs.
Each migration runs only when BOTH the stored legacy command and the new
declared command exactly match the known shipped defaults.
"""
from __future__ import annotations

import json

_LAUNCHERS = {
    "playwright": ("npx", ["-y", "@playwright/mcp@0.0.75", "--headless"],
                   ["-y", "@playwright/mcp@0.0.75", "--headless", "--isolated"]),
    "yahoo-finance": ("uv", ["tool", "run", "yahoo-finance-mcp"],
                      ["tool", "run", "--with", "mcp<2", "yahoo-finance-mcp"]),
    "google-news": ("uv", ["tool", "run", "google-news-trends-mcp"],
                    ["tool", "run", "--with", "mcp<2", "--with", "selectolax<1", "google-news-trends-mcp"]),
}


def migrate_launchers(db, declared: dict, now: float) -> int:
    from core.database import McpServerModel
    changed = 0
    for name, (command, old, new) in _LAUNCHERS.items():
        row = db.get(McpServerModel, name)
        cfg = declared.get(name) or {}
        if (row is not None and row.is_builtin and row.transport == "stdio"
                and row.command == command and json.loads(row.args_json or "[]") == old
                and cfg.get("command") == command and cfg.get("args") == new):
            row.args_json = json.dumps(new)
            row.updated_at = now
            changed += 1
    return changed
