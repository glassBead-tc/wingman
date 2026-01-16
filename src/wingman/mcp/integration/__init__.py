"""
MCP SDK Integration.

Bridges the direct MCP client with the Dedalus Labs SDK for hybrid operation.
"""

from wingman.mcp.integration.llm_adapter import LLMInterface, DedalusLLMAdapter
from wingman.mcp.integration.server_registry import ServerRegistry, ServerInfo
from wingman.mcp.integration.bridge import HybridMCPBridge, HybridConfig

__all__ = [
    "LLMInterface",
    "DedalusLLMAdapter",
    "ServerRegistry",
    "ServerInfo",
    "HybridMCPBridge",
    "HybridConfig",
]
