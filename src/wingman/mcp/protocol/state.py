"""Protocol state machine for MCP lifecycle."""

from enum import Enum, auto
from typing import Callable


class ProtocolState(Enum):
    """
    Protocol lifecycle states.

    State transitions:
        DISCONNECTED -> CONNECTING -> INITIALIZING -> READY -> CLOSING -> CLOSED
                                 \\                    /
                                  -> DISCONNECTED <-

    The DISCONNECTED state can be reached from CONNECTING, INITIALIZING, or READY
    in case of connection errors or unexpected disconnection.
    """

    DISCONNECTED = auto()
    CONNECTING = auto()
    INITIALIZING = auto()
    READY = auto()
    CLOSING = auto()
    CLOSED = auto()

    def __str__(self) -> str:
        return self.name


class InvalidStateTransition(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: ProtocolState, to_state: ProtocolState):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid state transition: {from_state.name} -> {to_state.name}"
        )


# Type for state transition callbacks
StateTransitionCallback = Callable[[ProtocolState, ProtocolState], None]


class ProtocolStateMachine:
    """
    Manages MCP protocol lifecycle state.

    Enforces valid state transitions and notifies listeners
    when transitions occur.
    """

    # Define valid state transitions
    VALID_TRANSITIONS: dict[ProtocolState, list[ProtocolState]] = {
        ProtocolState.DISCONNECTED: [ProtocolState.CONNECTING],
        ProtocolState.CONNECTING: [
            ProtocolState.INITIALIZING,
            ProtocolState.DISCONNECTED,  # Connection failed
        ],
        ProtocolState.INITIALIZING: [
            ProtocolState.READY,
            ProtocolState.DISCONNECTED,  # Initialize failed
        ],
        ProtocolState.READY: [
            ProtocolState.CLOSING,
            ProtocolState.DISCONNECTED,  # Unexpected disconnect (LOG-002 fix)
        ],
        ProtocolState.CLOSING: [
            ProtocolState.CLOSED,
            ProtocolState.DISCONNECTED,  # Close interrupted
        ],
        ProtocolState.CLOSED: [],  # Terminal state
    }

    def __init__(self, initial_state: ProtocolState = ProtocolState.DISCONNECTED):
        self._state = initial_state
        self._listeners: list[StateTransitionCallback] = []

    @property
    def state(self) -> ProtocolState:
        """Current protocol state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if in a connected state (INITIALIZING or READY)."""
        return self._state in (ProtocolState.INITIALIZING, ProtocolState.READY)

    @property
    def is_ready(self) -> bool:
        """Check if fully initialized and ready for requests."""
        return self._state == ProtocolState.READY

    @property
    def is_closed(self) -> bool:
        """Check if connection is closed."""
        return self._state in (ProtocolState.CLOSED, ProtocolState.DISCONNECTED)

    def can_transition_to(self, new_state: ProtocolState) -> bool:
        """Check if transition to new_state is valid."""
        return new_state in self.VALID_TRANSITIONS.get(self._state, [])

    def transition(self, new_state: ProtocolState) -> None:
        """
        Transition to a new state.

        Args:
            new_state: The target state.

        Raises:
            InvalidStateTransition: If the transition is not valid.
        """
        if not self.can_transition_to(new_state):
            raise InvalidStateTransition(self._state, new_state)

        old_state = self._state
        self._state = new_state

        # Notify listeners
        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception:
                # Don't let listener errors affect state machine
                pass

    def force_state(self, new_state: ProtocolState) -> None:
        """
        Force transition to a state without validation.

        USE WITH CAUTION. This bypasses transition rules and should
        only be used for error recovery scenarios.

        Args:
            new_state: The target state.
        """
        old_state = self._state
        self._state = new_state

        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception:
                pass

    def on_transition(self, callback: StateTransitionCallback) -> None:
        """
        Register a callback for state transitions.

        Args:
            callback: Function called with (old_state, new_state) on transitions.
        """
        self._listeners.append(callback)

    def remove_listener(self, callback: StateTransitionCallback) -> None:
        """
        Remove a previously registered callback.

        Args:
            callback: The callback to remove.
        """
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def reset(self) -> None:
        """Reset state machine to initial disconnected state."""
        old_state = self._state
        self._state = ProtocolState.DISCONNECTED

        for listener in self._listeners:
            try:
                listener(old_state, ProtocolState.DISCONNECTED)
            except Exception:
                pass

    def __str__(self) -> str:
        return f"ProtocolStateMachine({self._state.name})"

    def __repr__(self) -> str:
        return f"ProtocolStateMachine(state={self._state!r})"
