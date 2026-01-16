"""Sampling feature implementation for MCP."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from dedalus_labs import AsyncDedalus

logger = logging.getLogger(__name__)


class SamplingDeniedError(Exception):
    """User denied sampling request."""

    pass


class SamplingTimeoutError(Exception):
    """Sampling request timed out."""

    pass


# Content types
@dataclass
class TextContent:
    """Text content in sampling."""

    type: Literal["text"] = "text"
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "text": self.text}


@dataclass
class ImageContent:
    """Image content in sampling."""

    type: Literal["image"] = "image"
    data: str = ""  # Base64 encoded
    mime_type: str = "image/png"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "data": self.data,
            "mimeType": self.mime_type,
        }


Content = TextContent | ImageContent


@dataclass
class SamplingMessage:
    """Message in sampling request."""

    role: Literal["user", "assistant"]
    content: Content

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SamplingMessage":
        content_data = data.get("content", {})
        if isinstance(content_data, str):
            content = TextContent(text=content_data)
        elif content_data.get("type") == "image":
            content = ImageContent(
                data=content_data.get("data", ""),
                mime_type=content_data.get("mimeType", "image/png"),
            )
        else:
            content = TextContent(text=content_data.get("text", ""))

        return cls(role=data.get("role", "user"), content=content)


@dataclass
class ModelPreferences:
    """Server hints for model selection."""

    hints: list[dict[str, str]] | None = None
    cost_priority: float | None = None  # 0.0-1.0
    speed_priority: float | None = None  # 0.0-1.0
    intelligence_priority: float | None = None  # 0.0-1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ModelPreferences | None":
        if not data:
            return None
        return cls(
            hints=data.get("hints"),
            cost_priority=data.get("costPriority"),
            speed_priority=data.get("speedPriority"),
            intelligence_priority=data.get("intelligencePriority"),
        )


@dataclass
class SamplingRequest:
    """Server request for LLM completion."""

    messages: list[SamplingMessage]
    model_preferences: ModelPreferences | None = None
    system_prompt: str | None = None
    include_context: Literal["none", "thisServer", "allServers"] = "none"
    temperature: float | None = None
    max_tokens: int = 1024
    stop_sequences: list[str] | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, params: dict[str, Any]) -> "SamplingRequest":
        """Parse from MCP request params."""
        messages = [
            SamplingMessage.from_dict(msg) for msg in params.get("messages", [])
        ]
        return cls(
            messages=messages,
            model_preferences=ModelPreferences.from_dict(
                params.get("modelPreferences")
            ),
            system_prompt=params.get("systemPrompt"),
            include_context=params.get("includeContext", "none"),
            temperature=params.get("temperature"),
            max_tokens=params.get("maxTokens", 1024),
            stop_sequences=params.get("stopSequences"),
            metadata=params.get("_meta"),
        )


@dataclass
class SamplingResponse:
    """Response to sampling request."""

    role: Literal["assistant"] = "assistant"
    content: Content = field(default_factory=lambda: TextContent())
    model: str = ""
    stop_reason: Literal["endTurn", "stopSequence", "maxTokens"] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content.to_dict(),
            "model": self.model,
            "stopReason": self.stop_reason,
        }


# Type for approval callback
ApprovalCallback = Callable[
    ["SamplingRequest"], Awaitable[tuple[bool, "SamplingRequest | None"]]
]


@dataclass
class SamplingConfig:
    """Configuration for sampling handler."""

    default_model: str = "anthropic/claude-sonnet-4-5-20250929"
    """Default model to use if no preference specified."""

    timeout: float = 120.0
    """Timeout for LLM completion in seconds."""

    require_approval: bool = True
    """Whether to require user approval before sampling."""

    allow_editing: bool = True
    """Whether to allow user to edit request before approval."""

    log_requests: bool = True
    """Whether to log sampling requests for audit."""


class SamplingHandler:
    """
    Handles server-initiated sampling requests.

    Implements the MCP sampling/createMessage request handler,
    obtaining user approval and executing LLM completions.
    """

    def __init__(
        self,
        dedalus_client: "AsyncDedalus | None" = None,
        config: SamplingConfig | None = None,
        approval_callback: ApprovalCallback | None = None,
    ):
        """
        Initialize sampling handler.

        Args:
            dedalus_client: Dedalus SDK client for LLM calls.
            config: Sampling configuration.
            approval_callback: Async callback for user approval.
        """
        self.client = dedalus_client
        self.config = config or SamplingConfig()
        self._approval_callback = approval_callback
        self._pending_request: SamplingRequest | None = None

    @property
    def has_pending_request(self) -> bool:
        """Check if there's a pending sampling request."""
        return self._pending_request is not None

    def set_approval_callback(self, callback: ApprovalCallback) -> None:
        """Set the approval callback."""
        self._approval_callback = callback

    async def handle_request(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Handle sampling/createMessage request from server.

        Args:
            params: Request parameters from MCP.

        Returns:
            Sampling response for MCP.

        Raises:
            SamplingDeniedError: If user denies request.
            SamplingTimeoutError: If LLM call times out.
        """
        # Parse request
        request = SamplingRequest.from_dict(params)
        self._pending_request = request

        if self.config.log_requests:
            logger.info(f"Received sampling request with {len(request.messages)} messages")

        try:
            # Request user approval if required
            if self.config.require_approval:
                request = await self._get_approval(request)

            # Check for LLM client
            if not self.client:
                raise ValueError("No LLM client configured for sampling")

            # Select model based on preferences
            model = self._select_model(request.model_preferences)

            # Build messages for Dedalus
            messages = self._build_messages(request)

            # Execute via Dedalus SDK
            try:
                response = await asyncio.wait_for(
                    self._execute_sampling(model, messages, request),
                    timeout=self.config.timeout,
                )
            except asyncio.TimeoutError:
                raise SamplingTimeoutError(
                    f"Sampling timed out after {self.config.timeout}s"
                )

            return self._format_response(response, model)

        finally:
            self._pending_request = None

    async def _get_approval(self, request: SamplingRequest) -> SamplingRequest:
        """Get user approval for sampling request."""
        if not self._approval_callback:
            # No callback - auto-approve
            logger.warning("No approval callback configured, auto-approving")
            return request

        approved, modified_request = await self._approval_callback(request)

        if not approved:
            logger.info("Sampling request denied by user")
            raise SamplingDeniedError("User denied sampling request")

        if modified_request:
            logger.info("Sampling request modified by user")
            return modified_request

        return request

    def _select_model(self, preferences: ModelPreferences | None) -> str:
        """
        Select model based on server preferences.

        Args:
            preferences: Server's model preferences.

        Returns:
            Model identifier string.
        """
        if not preferences:
            return self.config.default_model

        # Check hints for specific model requests
        if preferences.hints:
            for hint in preferences.hints:
                if "name" in hint:
                    hint_name = hint["name"].lower()
                    if "claude" in hint_name:
                        if "opus" in hint_name:
                            return "anthropic/claude-opus-4-5-20251001"
                        if "haiku" in hint_name:
                            return "anthropic/claude-haiku-4-5-20251001"
                        return self.config.default_model
                    if "gpt" in hint_name:
                        if "4o" in hint_name:
                            return "openai/gpt-4o"
                        return "openai/gpt-4"

        # Balance priorities if specified
        if preferences.speed_priority and preferences.speed_priority > 0.7:
            return "anthropic/claude-haiku-4-5-20251001"
        if preferences.intelligence_priority and preferences.intelligence_priority > 0.7:
            return "anthropic/claude-opus-4-5-20251001"

        return self.config.default_model

    def _build_messages(self, request: SamplingRequest) -> list[dict[str, Any]]:
        """Build Dedalus-compatible messages from sampling request."""
        messages: list[dict[str, Any]] = []

        # Add system prompt if provided
        if request.system_prompt:
            messages.append({
                "role": "system",
                "content": request.system_prompt,
            })

        # Convert sampling messages
        for msg in request.messages:
            if isinstance(msg.content, TextContent):
                messages.append({
                    "role": msg.role,
                    "content": msg.content.text,
                })
            elif isinstance(msg.content, ImageContent):
                # Format for vision models
                messages.append({
                    "role": msg.role,
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{msg.content.mime_type};base64,{msg.content.data}"
                            },
                        }
                    ],
                })

        return messages

    async def _execute_sampling(
        self,
        model: str,
        messages: list[dict[str, Any]],
        request: SamplingRequest,
    ) -> Any:
        """Execute sampling via Dedalus SDK."""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
        }

        if request.temperature is not None:
            kwargs["temperature"] = request.temperature

        if request.stop_sequences:
            kwargs["stop"] = request.stop_sequences

        logger.debug(f"Executing sampling with model {model}")
        response = await self.client.chat.completions.create(**kwargs)
        return response

    def _format_response(self, response: Any, model: str) -> dict[str, Any]:
        """Format Dedalus response for MCP."""
        # Handle different response formats
        if hasattr(response, "choices"):
            choices = response.choices
        elif isinstance(response, dict):
            choices = response.get("choices", [])
        else:
            choices = []

        if not choices:
            return {
                "role": "assistant",
                "content": {"type": "text", "text": ""},
                "model": model,
                "stopReason": "endTurn",
            }

        choice = choices[0]

        # Extract message content
        if hasattr(choice, "message"):
            message = choice.message
            content = getattr(message, "content", "") or ""
            finish_reason = getattr(choice, "finish_reason", "stop")
        elif isinstance(choice, dict):
            message = choice.get("message", {})
            content = message.get("content", "")
            finish_reason = choice.get("finish_reason", "stop")
        else:
            content = ""
            finish_reason = "stop"

        return {
            "role": "assistant",
            "content": {"type": "text", "text": content},
            "model": model,
            "stopReason": self._map_stop_reason(finish_reason),
        }

    def _map_stop_reason(
        self, finish_reason: str | None
    ) -> Literal["endTurn", "stopSequence", "maxTokens"]:
        """Map Dedalus finish reason to MCP stop reason."""
        mapping: dict[str, Literal["endTurn", "stopSequence", "maxTokens"]] = {
            "stop": "endTurn",
            "length": "maxTokens",
            "max_tokens": "maxTokens",
            "tool_calls": "endTurn",
            "content_filter": "endTurn",
        }
        return mapping.get(finish_reason or "stop", "endTurn")
