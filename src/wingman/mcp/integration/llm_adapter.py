"""Shared LLM interface for MCP features."""

from __future__ import annotations

from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from dedalus_labs import AsyncDedalus


class LLMInterface(Protocol):
    """
    Protocol for LLM operations.

    Defines the interface for chat completions that can be implemented
    by different LLM providers.
    """

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float | None = None,
        stop: list[str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a chat completion.

        Args:
            model: Model identifier.
            messages: Conversation messages.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
            stop: Stop sequences.
            tools: Tool definitions for function calling.
            tool_choice: Tool selection strategy.

        Returns:
            Chat completion response.
        """
        ...


class DedalusLLMAdapter:
    """
    Adapts Dedalus SDK for shared LLM operations.

    Provides a consistent interface for LLM calls that can be
    used by both SDK-based and direct MCP features.
    """

    def __init__(self, client: "AsyncDedalus"):
        """
        Initialize adapter.

        Args:
            client: Dedalus SDK async client instance.
        """
        self.client = client

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float | None = None,
        stop: list[str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute chat completion via Dedalus SDK.

        Args:
            model: Model identifier (e.g., "anthropic/claude-sonnet-4-5-20250929").
            messages: Conversation messages in OpenAI format.
            max_tokens: Maximum tokens in response.
            temperature: Optional sampling temperature.
            stop: Optional stop sequences.
            tools: Optional tool definitions.
            tool_choice: Optional tool selection strategy.

        Returns:
            Chat completion response.
        """
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        if temperature is not None:
            kwargs["temperature"] = temperature
        if stop:
            kwargs["stop"] = stop
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        # Call Dedalus SDK
        response = await self.client.chat.completions.create(**kwargs)

        # Convert to dict if necessary
        if hasattr(response, "model_dump"):
            return response.model_dump()
        elif hasattr(response, "dict"):
            return response.dict()
        else:
            return dict(response)

    async def stream_chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float | None = None,
        stop: list[str] | None = None,
    ):
        """
        Stream a chat completion via Dedalus SDK.

        Args:
            model: Model identifier.
            messages: Conversation messages.
            max_tokens: Maximum tokens.
            temperature: Optional temperature.
            stop: Optional stop sequences.

        Yields:
            Chat completion chunks.
        """
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if temperature is not None:
            kwargs["temperature"] = temperature
        if stop:
            kwargs["stop"] = stop

        response = await self.client.chat.completions.create(**kwargs)

        async for chunk in response:
            if hasattr(chunk, "model_dump"):
                yield chunk.model_dump()
            elif hasattr(chunk, "dict"):
                yield chunk.dict()
            else:
                yield dict(chunk)


class MockLLMAdapter:
    """
    Mock LLM adapter for testing.

    Returns canned responses for testing MCP features
    without requiring a real LLM backend.
    """

    def __init__(self, responses: list[dict[str, Any]] | None = None):
        """
        Initialize mock adapter.

        Args:
            responses: List of responses to return in order.
        """
        self.responses = responses or []
        self.call_history: list[dict[str, Any]] = []
        self._response_index = 0

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float | None = None,
        stop: list[str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record call and return mock response."""
        self.call_history.append({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stop": stop,
            "tools": tools,
            "tool_choice": tool_choice,
        })

        if self.responses and self._response_index < len(self.responses):
            response = self.responses[self._response_index]
            self._response_index += 1
            return response

        # Default mock response
        return {
            "id": "mock-completion-id",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Mock response for testing.",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
