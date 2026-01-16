"""Pytest configuration and fixtures."""

import json
from pathlib import Path

import pytest

# Enable async tests without marking each one
pytest_plugins = ["pytest_asyncio"]


@pytest.fixture
def mcp_config():
    """Load MCP server configuration from .mcp.json."""
    config_path = Path(__file__).parent.parent / ".mcp.json"
    if not config_path.exists():
        pytest.skip("No .mcp.json found")
    with open(config_path) as f:
        return json.load(f)


@pytest.fixture
def thoughtbox_config(mcp_config):
    """Get Thoughtbox server configuration."""
    servers = mcp_config.get("mcpServers", {})
    if "thoughtbox" not in servers:
        pytest.skip("Thoughtbox not configured in .mcp.json")
    return servers["thoughtbox"]


@pytest.fixture
def banner_yaml():
    """Sample banner YAML content."""
    return """
version: 1
messages:
  - id: test-banner
    type: banner
    content: "[bold]Test banner[/]"
    priority: 10
    dismissible: true
"""


@pytest.fixture
def tip_yaml():
    """Sample tip YAML content."""
    return """
version: 1
messages:
  - id: tip-1
    type: tip
    content: "Press Ctrl+M to switch models"
  - id: tip-2
    type: tip
    content: "Use /help for commands"
"""


@pytest.fixture
def conditional_yaml():
    """YAML with time-based conditions."""
    return """
version: 1
messages:
  - id: expired
    type: notice
    content: "This is expired"
    conditions:
      until: "2020-01-01T00:00:00Z"
  - id: future
    type: notice
    content: "This is future"
    conditions:
      from: "2099-01-01T00:00:00Z"
  - id: active
    type: notice
    content: "This is active"
"""
