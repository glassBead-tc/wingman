"""
MCP Feature Handlers.

Implements MCP client features: Roots, Sampling, and Elicitation.
"""

from wingman.mcp.features.types import Root
from wingman.mcp.features.roots import (
    RootsManager,
    RootsConfig,
    RootsHandler,
    RootsLockedError,
)
from wingman.mcp.features.sampling import (
    SamplingHandler,
    SamplingConfig,
    SamplingRequest,
    SamplingResponse,
    SamplingMessage,
    TextContent,
    ImageContent,
    ModelPreferences,
    SamplingDeniedError,
    SamplingTimeoutError,
)
from wingman.mcp.features.elicitation import (
    ElicitationHandler,
    ElicitationConfig,
    ElicitationRequest,
    ElicitationResponse,
    ElicitationError,
    ElicitationTimeoutError,
    InvalidURLSchemeError,
    OAuthCallbackServer,
)

__all__ = [
    # Types
    "Root",
    # Roots
    "RootsManager",
    "RootsConfig",
    "RootsHandler",
    "RootsLockedError",
    # Sampling
    "SamplingHandler",
    "SamplingConfig",
    "SamplingRequest",
    "SamplingResponse",
    "SamplingMessage",
    "TextContent",
    "ImageContent",
    "ModelPreferences",
    "SamplingDeniedError",
    "SamplingTimeoutError",
    # Elicitation
    "ElicitationHandler",
    "ElicitationConfig",
    "ElicitationRequest",
    "ElicitationResponse",
    "ElicitationError",
    "ElicitationTimeoutError",
    "InvalidURLSchemeError",
    "OAuthCallbackServer",
]
