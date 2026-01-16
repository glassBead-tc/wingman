"""Completion utility for MCP argument autocompletion."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from wingman.mcp.utilities.types import (
    CompletionRef,
    CompletionArgument,
    CompletionRequest,
    CompletionResponse,
)

if TYPE_CHECKING:
    from wingman.mcp.protocol.client import MCPClient

logger = logging.getLogger(__name__)


class CompletionError(Exception):
    """Error related to completion operations."""

    pass


class CompletionNotSupportedError(CompletionError):
    """Server does not support completions capability."""

    pass


class CompletionHandler:
    """
    Handles completion requests to MCP server.

    Provides autocompletion for prompt and resource arguments.
    Requires server to advertise 'completions' capability.
    """

    def __init__(self, client: "MCPClient") -> None:
        """
        Initialize completion handler.

        Args:
            client: The MCP client to use for requests.
        """
        self.client = client

    async def complete(
        self,
        ref_type: Literal["ref/prompt", "ref/resource"],
        ref_name: str,
        argument_name: str,
        argument_value: str,
        context: dict[str, Any] | None = None,
    ) -> CompletionResponse:
        """
        Request completions from server.

        Args:
            ref_type: Type of reference (prompt or resource).
            ref_name: Name of the prompt or URI of the resource.
            argument_name: Name of argument being completed.
            argument_value: Current partial value.
            context: Optional context with previously resolved arguments.

        Returns:
            CompletionResponse with suggestions.

        Raises:
            CompletionError: If request fails.
        """
        request = CompletionRequest(
            ref=CompletionRef(type=ref_type, name=ref_name),
            argument=CompletionArgument(name=argument_name, value=argument_value),
            context=context,
        )

        logger.debug(
            f"Requesting completion: ref={ref_type}:{ref_name}, "
            f"arg={argument_name}, value={argument_value!r}"
        )

        try:
            result = await self.client.request(
                "completion/complete",
                request.to_dict(),
            )
            response = CompletionResponse.from_dict(result)
            logger.debug(f"Completion response: {len(response.values)} values")
            return response
        except Exception as e:
            logger.error(f"Completion request failed: {e}")
            raise CompletionError(f"Completion failed: {e}") from e

    async def complete_prompt_argument(
        self,
        prompt_name: str,
        argument_name: str,
        current_value: str,
        context: dict[str, Any] | None = None,
    ) -> list[str]:
        """
        Get completions for a prompt argument.

        Convenience method for prompt argument completion.

        Args:
            prompt_name: Name of the prompt.
            argument_name: Name of the argument.
            current_value: Current partial value.
            context: Optional context with other arguments.

        Returns:
            List of completion suggestions.
        """
        response = await self.complete(
            ref_type="ref/prompt",
            ref_name=prompt_name,
            argument_name=argument_name,
            argument_value=current_value,
            context=context,
        )
        return response.values

    async def complete_resource_argument(
        self,
        resource_uri: str,
        argument_name: str,
        current_value: str,
        context: dict[str, Any] | None = None,
    ) -> list[str]:
        """
        Get completions for a resource argument.

        Convenience method for resource argument completion.

        Args:
            resource_uri: URI of the resource.
            argument_name: Name of the argument.
            current_value: Current partial value.
            context: Optional context with other arguments.

        Returns:
            List of completion suggestions.
        """
        response = await self.complete(
            ref_type="ref/resource",
            ref_name=resource_uri,
            argument_name=argument_name,
            argument_value=current_value,
            context=context,
        )
        return response.values


async def complete_argument(
    client: "MCPClient",
    ref_type: Literal["ref/prompt", "ref/resource"],
    ref_name: str,
    argument_name: str,
    argument_value: str,
    context: dict[str, Any] | None = None,
) -> CompletionResponse:
    """
    Standalone function for argument completion.

    Args:
        client: The MCP client to use.
        ref_type: Type of reference.
        ref_name: Name of the prompt or resource URI.
        argument_name: Name of argument.
        argument_value: Current partial value.
        context: Optional additional context.

    Returns:
        CompletionResponse with suggestions.
    """
    handler = CompletionHandler(client)
    return await handler.complete(
        ref_type=ref_type,
        ref_name=ref_name,
        argument_name=argument_name,
        argument_value=argument_value,
        context=context,
    )
