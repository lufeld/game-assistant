"""A reactive tool-calling ("ReAct") orchestrator - a proof-of-concept
comparison to modules/orchestrator.py's single-pass router.

Where the router does exactly one routing call, one deterministic retrieval
pass, and one answer call, this lets a bigger model (AGENT_MODEL) call the
same underlying wiki/player primitives - exposed as tools in
modules/agent/tools.py - multiple times per turn, deciding what to look up
next based on what it already found. Text-to-text only, not wired into the
voice loop; latency is not a constraint here the way it is for the router.

Stateful across turns within one CLI session (unlike the router): a capped
list of prior (question, answer) pairs is replayed into each new turn.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path

import ollama

try:
    from modules.agent import tools
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from modules.agent import tools

AGENT_MODEL = "qwen3:14b"

MAX_HOPS = 10

MEMORY_TURNS = 3

AGENT_SYSTEM_PROMPT = (
    "You are a Minecraft (game) assistant. Do not guess, but ground your answers."
    "Grounding you answers means you must use the available tools to find the information you need, and cite your sources. "
    "You can call tools, more than once if needed, to gather information before answering. "
    "Use available skills to guide your search and reasoning. "
    "Call wiki tools for game mechanics/knowledge questions, this is also useful before or after calling player tools. "
    "Call player tools for questions about the player's own current state (inventory, position, health, ...). "
    "For a broad 'what X exist' question, reading a wiki overview page such as "
    f"{', '.join(tools.SEED_PAGES)} is often a good first step. "
    "Several skill_* tools are available describing strategies for specific kinds of questions (crafting chains, giving directions, resolving "
    "vague wiki terms) - consult one when its description matches what you're doing. "
    "Once you have enough to answer, answer directly in plain spoken sentences, without calling another tool. "
    "Do not provide any additional context or explanation beyond the answer itself. "
    "Keep answers short, concise, and say plainly when something is still unknown rather than guessing."
)

_BUDGET_EXHAUSTED_NUDGE = (
    "You've used all available lookups. Answer now with what you've found "
    "so far; say plainly if something is still unknown rather than guessing."
)


@dataclass(slots=True)
class AgentResult:
    answer: str
    hops_used: int
    trace: list[dict] = field(default_factory=list)
    final_thinking: str | None = None  # the reasoning behind the answer itself, not a tool call


def run_agent(
    question: str,
    *,
    history: list[tuple[str, str]] | None = None,
    model: str = AGENT_MODEL,
    max_hops: int = MAX_HOPS,
    temperature: float = 0.3,
    chat_fn=ollama.chat,
) -> AgentResult:
    """Route+retrieve+answer for one turn, reactively - one tool call at a
    time, each informed by the previous result, up to max_hops."""
    messages: list[dict] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    for prior_question, prior_answer in (history or []):
        messages.append({"role": "user", "content": prior_question})
        messages.append({"role": "assistant", "content": prior_answer})
    messages.append({"role": "user", "content": question})

    trace: list[dict] = []
    hops = 0
    empty_content_retried = False

    while True:
        offer_tools = hops < max_hops
        response = chat_fn(
            model=model, messages=messages, tools=tools.TOOLS if offer_tools else None,
            think='high', options={"temperature": temperature},
        )
        message = response.message
        messages.append(message)

        tool_calls = message.tool_calls
        if not tool_calls:
            if message.content and message.content.strip():
                return AgentResult(answer=message.content, hops_used=hops, trace=trace, final_thinking=message.thinking)
            # Hybrid-thinking models sometimes put everything into
            # `thinking` and leave `content` empty even when "done" - that
            # reads as no reply at all rather than a low-quality one. Nudge
            # once for visible answer text (free - not a tool call, doesn't
            # cost a hop) before giving up with an explicit placeholder
            # instead of silently returning empty content.
            if empty_content_retried:
                return AgentResult(
                    answer="(no answer text was produced)", hops_used=hops, trace=trace, final_thinking=message.thinking,
                )
            empty_content_retried = True
            messages.append({"role": "user", "content": "Your last response had no visible answer text. Answer now in your response content."})
            continue

        for call in tool_calls:
            name = call.function.name
            arguments = call.function.arguments

            if hops >= max_hops:
                result_text = "hop budget reached, not executed"
            else:
                try:
                    fn = tools.TOOL_MAP[name]
                    valid_params = set(inspect.signature(fn).parameters)
                    result = fn(**{k: v for k, v in arguments.items() if k in valid_params})
                    result_text = json.dumps(result, default=str)
                except Exception as exc:  # one bad call must not sink the turn
                    result_text = f"error: {exc}"
                hops += 1

            trace.append({"tool": name, "arguments": dict(arguments), "result": result_text, "thinking": message.thinking})
            messages.append({"role": "tool", "tool_name": name, "content": result_text})

        if hops >= max_hops:
            messages.append({"role": "user", "content": _BUDGET_EXHAUSTED_NUDGE})


def _load_prompts(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def _print_trace(trace: list[dict], *, show_thinking: bool) -> None:
    for step in trace:
        if show_thinking and step.get("thinking"):
            print(f"  [thinking] {step['thinking']}")
        print(f"  -> {step['tool']}({step['arguments']}) = {step['result'][:200]}")


def _run_one(
    question: str, *, history: list[tuple[str, str]] | None, show_trace: bool, show_thinking: bool = False,
) -> AgentResult:
    result = run_agent(question, history=history)
    if show_trace:
        _print_trace(result.trace, show_thinking=show_thinking)
    if show_thinking and result.final_thinking:
        print(f"  [thinking] {result.final_thinking}")
    print(f"\n{result.answer}  [{result.hops_used} hop(s)]")
    return result


_EXIT_PHRASES = ("exit", "quit")


def _run_repl(*, show_trace: bool, show_thinking: bool, memory_turns: int) -> None:
    print(f"Agent REPL ({AGENT_MODEL}). Type 'exit' or 'quit' to leave.")
    history: list[tuple[str, str]] = []
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            continue
        if question.lower() in _EXIT_PHRASES:
            break
        try:
            result = _run_one(
                question, history=history[-memory_turns:] if memory_turns else None,
                show_trace=show_trace, show_thinking=show_thinking,
            )
        except Exception as exc:  # one bad turn shouldn't kill the session
            print(f"ERROR: {exc}")
            continue
        if memory_turns:
            history.append((question, result.answer))


if __name__ == "__main__":
    import argparse
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Ask the agentic assistant one question, a batch, or start a REPL")
    parser.add_argument("question", nargs="?", help="A single question to ask (memory off)")
    parser.add_argument("--batch", type=Path, help="Text file with one prompt per line, run independently (# lines are comments)")
    parser.add_argument("--show-trace", action="store_true", help="Print each tool call + result")
    parser.add_argument("--show-thinking", action="store_true", help="Print the model's reasoning before each tool call and the final answer (implies --show-trace)")
    parser.add_argument("--no-memory", action="store_true", help="Disable cross-turn memory in the REPL")
    args = parser.parse_args()
    show_trace = args.show_trace or args.show_thinking

    if args.batch:
        prompts = _load_prompts(args.batch)
        for i, question in enumerate(prompts, 1):
            print(f"\n{'=' * 70}\n[{i}/{len(prompts)}] {question}\n{'=' * 70}")
            try:
                _run_one(question, history=None, show_trace=show_trace, show_thinking=args.show_thinking)
            except Exception as exc:  # bad prompt shouldn't kill the batch
                print(f"ERROR: {exc}")
    elif args.question:
        _run_one(args.question, history=None, show_trace=show_trace, show_thinking=args.show_thinking)
    else:
        _run_repl(show_trace=show_trace, show_thinking=args.show_thinking, memory_turns=0 if args.no_memory else MEMORY_TURNS)
