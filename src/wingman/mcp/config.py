"""MCP server configuration loading."""

from dataclasses import dataclass, field
from pathlib import Path

from wingman.lib import oj

# Config file locations
MCP_CONFIG_FILENAME = "mcp.json"
GLOBAL_MCP_CONFIG = Path.home() / ".wingman" / MCP_CONFIG_FILENAME
LOCAL_MCP_CONFIG_DIR = ".wingman"


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "MCPServerConfig":
        """Create from config dict."""
        return cls(
            name=name,
            url=data.get("url", ""),
            headers=data.get("headers", {}),
        )


def load_mcp_config(working_dir: Path | None = None) -> dict[str, MCPServerConfig]:
    """Load MCP server configs from global and local config files.

    Global config (~/.wingman/mcp.json) is loaded first.
    Local config ({working_dir}/.wingman/mcp.json) overrides global.

    Returns:
        Dict mapping server name to config.
    """
    configs: dict[str, MCPServerConfig] = {}

    # Load global config
    if GLOBAL_MCP_CONFIG.exists():
        try:
            data = oj.loads(GLOBAL_MCP_CONFIG.read_text())
            servers = data.get("mcpServers", {})
            for name, server_data in servers.items():
                if isinstance(server_data, dict) and server_data.get("url"):
                    configs[name] = MCPServerConfig.from_dict(name, server_data)
        except Exception:
            pass

    # Load local config (overrides global)
    if working_dir:
        local_config = working_dir / LOCAL_MCP_CONFIG_DIR / MCP_CONFIG_FILENAME
        if local_config.exists():
            try:
                data = oj.loads(local_config.read_text())
                servers = data.get("mcpServers", {})
                for name, server_data in servers.items():
                    if isinstance(server_data, dict) and server_data.get("url"):
                        configs[name] = MCPServerConfig.from_dict(name, server_data)
            except Exception:
                pass

    return configs
