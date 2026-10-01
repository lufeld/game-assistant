"""Loop control-flow tests for orchestrator.py's run_agent - no live
network/Ollama. chat_fn is a real injected callable (dependency injection),
not a mock object, matching the codebase's "real I/O, no mocks" convention
applied here as "real callables standing in for the network boundary."
"""

from types import SimpleNamespace

import orchestrator


def _response(content=None, tool_calls=None, thinking=None):
    return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls, thinking=thinking))


def _tool_call(name, arguments):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


def test_empty_content_with_no_tool_calls_is_retried_once():
    # Hybrid-thinking models can put everything into `thinking` and leave
    # `content` empty even when "done" - that reads as no reply at all
    # rather than a low-quality one, so it gets one free (non-hop) retry
    # before giving up with an explicit placeholder.
    call_count = 0

    def chat_fn(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _response(content="")
        return _response(content="a real answer the second time")

    result = orchestrator.run_agent("q", chat_fn=chat_fn)

    assert result.answer == "a real answer the second time"
    assert result.hops_used == 0  # the retry isn't a tool call, doesn't cost a hop
    assert call_count == 2


def test_empty_content_twice_in_a_row_gives_an_explicit_placeholder_not_silence():
    def chat_fn(**kwargs):
        return _response(content="")

    result = orchestrator.run_agent("q", chat_fn=chat_fn)

    assert result.answer == "(no answer text was produced)"


def test_loop_returns_immediately_when_no_tool_calls():
    def chat_fn(**kwargs):
        return _response(content="a plain answer")

    result = orchestrator.run_agent("a question", chat_fn=chat_fn)

    assert result.answer == "a plain answer"
    assert result.hops_used == 0
    assert result.trace == []


def test_hops_increment_and_stop_offering_tools_at_budget(monkeypatch):
    monkeypatch.setitem(orchestrator.tools.TOOL_MAP, "dummy_tool", lambda: "dummy result")
    tools_offered_history = []

    def chat_fn(*, tools, **kwargs):
        tools_offered_history.append(tools)
        if tools is None:
            return _response(content="final answer")
        return _response(tool_calls=[_tool_call("dummy_tool", {})])

    result = orchestrator.run_agent("q", chat_fn=chat_fn, max_hops=3)

    assert result.answer == "final answer"
    assert result.hops_used == 3
    assert len(result.trace) == 3
    assert all(step["tool"] == "dummy_tool" for step in result.trace)
    # exactly max_hops calls offered tools, then exactly one forced-answer call with tools=None
    assert all(offered is not None for offered in tools_offered_history[:3])
    assert tools_offered_history[3] is None
    assert len(tools_offered_history) == 4


def test_tool_exception_becomes_error_message_not_a_crash(monkeypatch):
    def boom():
        raise ValueError("kaboom")

    monkeypatch.setitem(orchestrator.tools.TOOL_MAP, "boom_tool", boom)
    call_count = 0

    def chat_fn(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _response(tool_calls=[_tool_call("boom_tool", {})])
        return _response(content="handled it")

    result = orchestrator.run_agent("q", chat_fn=chat_fn, max_hops=5)

    assert result.answer == "handled it"
    assert result.hops_used == 1
    assert "error: kaboom" in result.trace[0]["result"]


def test_unexpected_extra_argument_is_dropped_not_a_typeerror(monkeypatch):
    # Observed live: qwen3:14b called a zero-argument tool with an extra
    # 'term' kwarg (likely pattern-matched from a neighboring tool) - a real
    # TypeError there would waste the hop on a tool that'd otherwise succeed.
    monkeypatch.setitem(orchestrator.tools.TOOL_MAP, "zero_arg_tool", lambda: "real result")
    call_count = 0

    def chat_fn(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _response(tool_calls=[_tool_call("zero_arg_tool", {"term": "hallucinated"})])
        return _response(content="ok")

    result = orchestrator.run_agent("q", chat_fn=chat_fn, max_hops=5)

    assert result.hops_used == 1
    assert result.trace[0]["result"] == '"real result"'
    assert result.trace[0]["arguments"] == {"term": "hallucinated"}  # original call preserved for debugging


def test_thinking_is_captured_per_hop_and_for_the_final_answer(monkeypatch):
    monkeypatch.setitem(orchestrator.tools.TOOL_MAP, "dummy_tool", lambda: "result")
    call_count = 0

    def chat_fn(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _response(tool_calls=[_tool_call("dummy_tool", {})], thinking="reasoning about the tool call")
        return _response(content="final answer", thinking="reasoning about the final answer")

    result = orchestrator.run_agent("q", chat_fn=chat_fn, max_hops=5)

    assert result.trace[0]["thinking"] == "reasoning about the tool call"
    assert result.final_thinking == "reasoning about the final answer"


def test_unknown_tool_name_becomes_error_message_not_a_crash():
    call_count = 0

    def chat_fn(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _response(tool_calls=[_tool_call("not_a_real_tool", {})])
        return _response(content="ok")

    result = orchestrator.run_agent("q", chat_fn=chat_fn, max_hops=5)

    assert result.hops_used == 1
    assert "error" in result.trace[0]["result"]


def test_memory_history_is_folded_into_messages_before_new_question():
    captured_messages = []

    def chat_fn(*, messages, **kwargs):
        captured_messages.append(list(messages))
        return _response(content="answer")

    orchestrator.run_agent(
        "new question",
        history=[("old q1", "old a1"), ("old q2", "old a2")],
        chat_fn=chat_fn,
    )

    first_call_messages = captured_messages[0]
    assert first_call_messages[0]["role"] == "system"
    assert first_call_messages[1] == {"role": "user", "content": "old q1"}
    assert first_call_messages[2] == {"role": "assistant", "content": "old a1"}
    assert first_call_messages[3] == {"role": "user", "content": "old q2"}
    assert first_call_messages[4] == {"role": "assistant", "content": "old a2"}
    assert first_call_messages[5] == {"role": "user", "content": "new question"}
