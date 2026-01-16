"""
MCP (Model Context Protocol) implementation for Wingman.

This module implements full MCP 2025-11-25 specification support using a hybrid
architecture:
- Direct MCP client for bidirectional protocol features (sampling, elicitation, tasks)
- Integration with Dedalus SDK for LLM API calls

Submodules:
- transport: Streamable HTTP transport layer
- protocol: JSON-RPC 2.0 protocol implementation
- capabilities: Capability negotiation
- features: Roots, sampling, elicitation handlers
- tasks: Task state machine and persistence
- integration: Dedalus SDK bridge
- utilities: Protocol utilities (ping, progress, cancellation, logging, completion, pagination)
"""

# Transport layer
from wingman.mcp.transport import (
    StreamableHTTPTransport,
    TransportConfig,
    Transport,
    TransportError,
    ConnectionError,
    TimeoutError,
    SessionError,
)

# Protocol layer
from wingman.mcp.protocol import (
    MCPClient,
    MCPError,
    ProtocolState,
    ProtocolStateMachine,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCNotification,
)

# Capabilities
from wingman.mcp.capabilities import (
    ClientCapabilities,
    ServerCapabilities,
    CapabilityNegotiator,
    NegotiationResult,
)

# Features
from wingman.mcp.features import (
    Root,
    RootsManager,
    RootsHandler,
    SamplingHandler,
    SamplingRequest,
    SamplingResponse,
    ElicitationHandler,
    ElicitationRequest,
    ElicitationResponse,
)

# Tasks
from wingman.mcp.tasks import (
    Task,
    TaskState,
    TaskManager,
    TaskConfig,
    TasksHandler,
)

# Integration
from wingman.mcp.integration import (
    HybridMCPBridge,
    HybridConfig,
    ServerRegistry,
    ServerInfo,
    DedalusLLMAdapter,
)

# Utilities
from wingman.mcp.utilities import (
    # Types
    LogLevel,
    ProgressInfo,
    LogMessage,
    CancellationInfo,
    CompletionRequest,
    CompletionResponse,
    PaginatedResult,
    # Handlers
    PingHandler,
    ProgressHandler,
    CancellationHandler,
    LoggingHandler,
    LoggingConfig,
    CompletionHandler,
    PaginatedListHelper,
    UtilityHandlers,
    # Functions
    setup_utility_handlers,
    ping_server,
    ping_with_retry,
    cancel_server_request,
    set_server_log_level,
    complete_argument,
    list_all_tools,
    list_all_resources,
    list_all_prompts,
)

__all__ = [
    # Transport
    "StreamableHTTPTransport",
    "TransportConfig",
    "Transport",
    "TransportError",
    "ConnectionError",
    "TimeoutError",
    "SessionError",
    # Protocol
    "MCPClient",
    "MCPError",
    "ProtocolState",
    "ProtocolStateMachine",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCNotification",
    # Capabilities
    "ClientCapabilities",
    "ServerCapabilities",
    "CapabilityNegotiator",
    "NegotiationResult",
    # Features
    "Root",
    "RootsManager",
    "RootsHandler",
    "SamplingHandler",
    "SamplingRequest",
    "SamplingResponse",
    "ElicitationHandler",
    "ElicitationRequest",
    "ElicitationResponse",
    # Tasks
    "Task",
    "TaskState",
    "TaskManager",
    "TaskConfig",
    "TasksHandler",
    # Integration
    "HybridMCPBridge",
    "HybridConfig",
    "ServerRegistry",
    "ServerInfo",
    "DedalusLLMAdapter",
    # Utilities - Types
    "LogLevel",
    "ProgressInfo",
    "LogMessage",
    "CancellationInfo",
    "CompletionRequest",
    "CompletionResponse",
    "PaginatedResult",
    # Utilities - Handlers
    "PingHandler",
    "ProgressHandler",
    "CancellationHandler",
    "LoggingHandler",
    "LoggingConfig",
    "CompletionHandler",
    "PaginatedListHelper",
    "UtilityHandlers",
    # Utilities - Functions
    "setup_utility_handlers",
    "ping_server",
    "ping_with_retry",
    "cancel_server_request",
    "set_server_log_level",
    "complete_argument",
    "list_all_tools",
    "list_all_resources",
    "list_all_prompts",
]
