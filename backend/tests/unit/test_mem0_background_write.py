from __future__ import annotations

from unittest.mock import MagicMock
from services.mem0_service import Mem0WriteDispatcher, MemoryIdentity


def test_background_write_submits_to_executor_and_calls_add_turn():
    mock_service = MagicMock()
    executor = MagicMock()
    dispatcher = Mem0WriteDispatcher(service=mock_service, executor=executor)

    identity = MemoryIdentity(user_id="u1", agent_id="merchant-advisor:m1", run_id="s1")
    dispatcher.submit("user message", "assistant answer", identity, origin_trace_id="t1")

    executor.submit.assert_called_once()
    fn, *args = executor.submit.call_args[0]
    # Execute the submitted function synchronously to verify
    fn(*args)
    mock_service.add_turn.assert_called_once_with("user message", "assistant answer", identity)


def test_background_write_handles_exception_without_propagating():
    mock_service = MagicMock()
    mock_service.add_turn.side_effect = RuntimeError("Mem0 connection lost")
    executor = MagicMock()
    dispatcher = Mem0WriteDispatcher(service=mock_service, executor=executor)

    identity = MemoryIdentity(user_id="u1", agent_id="merchant-advisor:m1", run_id="s1")
    dispatcher.submit("user message", "assistant answer", identity)

    fn, *args = executor.submit.call_args[0]
    # Must not raise
    fn(*args)
