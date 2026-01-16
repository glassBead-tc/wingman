"""
MCP UI Components.

Textual-based UI components for MCP feature interactions:
- Sampling approval modals
- Elicitation forms
- Task progress displays
- Roots management
"""

from wingman.ui.mcp.sampling import (
    SamplingApprovalModal,
    SamplingApprovalResult,
)
from wingman.ui.mcp.elicitation import (
    FormElicitationModal,
    URLElicitationModal,
    FormResult,
)
from wingman.ui.mcp.tasks import (
    TaskProgressWidget,
    TaskListPanel,
    TaskCancelRequest,
    TaskRefreshRequest,
)
from wingman.ui.mcp.roots import RootsPanel
from wingman.ui.mcp.common import (
    LoadingIndicator,
    ErrorDisplay,
)

__all__ = [
    # Sampling
    "SamplingApprovalModal",
    "SamplingApprovalResult",
    # Elicitation
    "FormElicitationModal",
    "URLElicitationModal",
    "FormResult",
    # Tasks
    "TaskProgressWidget",
    "TaskListPanel",
    "TaskCancelRequest",
    "TaskRefreshRequest",
    # Roots
    "RootsPanel",
    # Common
    "LoadingIndicator",
    "ErrorDisplay",
]
