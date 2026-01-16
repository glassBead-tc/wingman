"""Pagination utility for MCP list operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, AsyncIterator, TypeVar

from wingman.mcp.utilities.types import PaginatedResult

if TYPE_CHECKING:
    from wingman.mcp.protocol.client import MCPClient

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PaginationError(Exception):
    """Error related to pagination operations."""

    pass


class InvalidCursorError(PaginationError):
    """The provided cursor is invalid or expired."""

    pass


class PaginatedListHelper:
    """
    Helper for cursor-based pagination of MCP list operations.

    MCP uses cursor-based pagination for:
    - tools/list
    - resources/list
    - resources/templates/list
    - prompts/list

    Cursors are opaque strings that clients must not parse or modify.
    """

    def __init__(self, client: "MCPClient") -> None:
        """
        Initialize pagination helper.

        Args:
            client: The MCP client to use for requests.
        """
        self.client = client

    async def list_page(
        self,
        method: str,
        items_key: str,
        cursor: str | None = None,
    ) -> PaginatedResult[dict[str, Any]]:
        """
        Fetch a single page of results.

        Args:
            method: RPC method (e.g., "tools/list").
            items_key: Key in response containing items (e.g., "tools").
            cursor: Pagination cursor from previous request.

        Returns:
            PaginatedResult with items and next cursor.

        Raises:
            PaginationError: If request fails.
        """
        params: dict[str, Any] | None = None
        if cursor:
            params = {"cursor": cursor}

        logger.debug(f"Fetching page: method={method}, cursor={cursor}")

        try:
            result = await self.client.request(method, params)
        except Exception as e:
            # Check for invalid cursor error
            if hasattr(e, "code") and e.code == -32602:  # type: ignore
                raise InvalidCursorError(f"Invalid cursor: {cursor}") from e
            raise PaginationError(f"List request failed: {e}") from e

        items = result.get(items_key, [])
        next_cursor = result.get("nextCursor")

        logger.debug(
            f"Page result: {len(items)} items, "
            f"has_more={next_cursor is not None}"
        )

        return PaginatedResult(items=items, next_cursor=next_cursor)

    async def list_all(
        self,
        method: str,
        items_key: str,
        max_pages: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch all pages of results.

        Args:
            method: RPC method.
            items_key: Key in response containing items.
            max_pages: Maximum pages to fetch (safety limit).

        Returns:
            All items concatenated.

        Raises:
            PaginationError: If request fails or max_pages exceeded.
        """
        all_items: list[dict[str, Any]] = []
        cursor: str | None = None

        for page_num in range(max_pages):
            result = await self.list_page(method, items_key, cursor)
            all_items.extend(result.items)

            if not result.has_more:
                logger.debug(f"Fetched all items in {page_num + 1} pages")
                return all_items

            cursor = result.next_cursor

        logger.warning(
            f"Reached max_pages limit ({max_pages}) for {method}, "
            f"there may be more results"
        )
        return all_items

    async def iter_pages(
        self,
        method: str,
        items_key: str,
    ) -> AsyncIterator[PaginatedResult[dict[str, Any]]]:
        """
        Iterate through pages of results.

        Yields pages one at a time, allowing processing between pages.

        Args:
            method: RPC method.
            items_key: Key in response containing items.

        Yields:
            PaginatedResult for each page.
        """
        cursor: str | None = None

        while True:
            result = await self.list_page(method, items_key, cursor)
            yield result

            if not result.has_more:
                break
            cursor = result.next_cursor

    async def iter_items(
        self,
        method: str,
        items_key: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Iterate through all items across pages.

        Flattens pagination, yielding individual items.

        Args:
            method: RPC method.
            items_key: Key in response containing items.

        Yields:
            Individual items from all pages.
        """
        async for page in self.iter_pages(method, items_key):
            for item in page.items:
                yield item


# Convenience functions for common list operations


async def list_tools_paginated(
    client: "MCPClient",
    cursor: str | None = None,
) -> PaginatedResult[dict[str, Any]]:
    """
    List tools with pagination support.

    Args:
        client: The MCP client.
        cursor: Optional cursor for continuation.

    Returns:
        Paginated result with tools.
    """
    helper = PaginatedListHelper(client)
    return await helper.list_page("tools/list", "tools", cursor)


async def list_all_tools(client: "MCPClient") -> list[dict[str, Any]]:
    """
    List all tools, handling pagination automatically.

    Args:
        client: The MCP client.

    Returns:
        All tools from server.
    """
    helper = PaginatedListHelper(client)
    return await helper.list_all("tools/list", "tools")


async def list_resources_paginated(
    client: "MCPClient",
    cursor: str | None = None,
) -> PaginatedResult[dict[str, Any]]:
    """
    List resources with pagination support.

    Args:
        client: The MCP client.
        cursor: Optional cursor for continuation.

    Returns:
        Paginated result with resources.
    """
    helper = PaginatedListHelper(client)
    return await helper.list_page("resources/list", "resources", cursor)


async def list_all_resources(client: "MCPClient") -> list[dict[str, Any]]:
    """
    List all resources, handling pagination automatically.

    Args:
        client: The MCP client.

    Returns:
        All resources from server.
    """
    helper = PaginatedListHelper(client)
    return await helper.list_all("resources/list", "resources")


async def list_prompts_paginated(
    client: "MCPClient",
    cursor: str | None = None,
) -> PaginatedResult[dict[str, Any]]:
    """
    List prompts with pagination support.

    Args:
        client: The MCP client.
        cursor: Optional cursor for continuation.

    Returns:
        Paginated result with prompts.
    """
    helper = PaginatedListHelper(client)
    return await helper.list_page("prompts/list", "prompts", cursor)


async def list_all_prompts(client: "MCPClient") -> list[dict[str, Any]]:
    """
    List all prompts, handling pagination automatically.

    Args:
        client: The MCP client.

    Returns:
        All prompts from server.
    """
    helper = PaginatedListHelper(client)
    return await helper.list_all("prompts/list", "prompts")


async def list_resource_templates_paginated(
    client: "MCPClient",
    cursor: str | None = None,
) -> PaginatedResult[dict[str, Any]]:
    """
    List resource templates with pagination support.

    Args:
        client: The MCP client.
        cursor: Optional cursor for continuation.

    Returns:
        Paginated result with resource templates.
    """
    helper = PaginatedListHelper(client)
    return await helper.list_page(
        "resources/templates/list",
        "resourceTemplates",
        cursor,
    )


async def list_all_resource_templates(client: "MCPClient") -> list[dict[str, Any]]:
    """
    List all resource templates, handling pagination automatically.

    Args:
        client: The MCP client.

    Returns:
        All resource templates from server.
    """
    helper = PaginatedListHelper(client)
    return await helper.list_all("resources/templates/list", "resourceTemplates")
