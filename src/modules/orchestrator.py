"""Route a player's question to wiki knowledge and answer it - the synchronous v1.

Four steps, each a plain function so this is testable the same way as the
wiki/ modules (call it with text, read what comes back):

    ROUTE    - one constrained-JSON Ollama call: which entities is this
               about, does answering need the player's own state.
    ENSURE   - per entity, make sure wiki_prose is actually current for it
               (resolve -> compare against what's *stored*, not just
               cached -> fetch/parse/store only if missing or stale).
    RETRIEVE - semantic search within each resolved page's own chunks,
               not the whole corpus - narrows an easy problem (which
               chunk, on a page we already know is the right one) instead
               of a hard one (which page, from raw keyword/vector search
               across everything).
    ANSWER   - one Ollama call reads the retrieved chunks directly; no
               separate query-paraphrase step. Widening RETRIEVE's top-k
               and letting the answering model read multiple candidates is
               cheaper (one fewer LLM call per turn) than a paraphrase step,
               and this session's own testing showed raw natural-phrasing
               queries already land the right chunk within a small top-k.

need_player_state is threaded through now so the router is already asking
the right question, but there's no Player DB yet - _player_state_context()
is a stub, not a placeholder that will need restructuring once one exists.

Deliberately synchronous, not the asyncio audio_in/dialog/game_ingest/
audio_out task design from the original blueprint - that's for wrapping
real concurrency (always-on STT, the Fabric mod) around this once it's
needed, not for solving routing and concurrency at the same time.
"""

from __future__ import annotations

import json
from pathlib import Path

import ollama

try:
    from modules.wiki.fetch import get_page, peek_cached_revid
    from modules.wiki.parse import parse_page
    from modules.wiki.resolve import PageNotFound, ResolvedTitle, resolve_title
    from modules.wiki.store import peek_stored_revid, query_prose, store_page
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from modules.wiki.fetch import get_page, peek_cached_revid
    from modules.wiki.parse import parse_page
    from modules.wiki.resolve import PageNotFound, ResolvedTitle, resolve_title
    from modules.wiki.store import peek_stored_revid, query_prose, store_page

MODEL_NAME = "qwen3:4b-instruct"
N_RESULTS = 5

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {"type": "array", "items": {"type": "string"}},
        "need_player_state": {"type": "boolean"},
    },
    "required": ["entities", "need_player_state"],
}

# Few-shot, not zero-shot: a bare instruction misclassified "How do I make a
# beacon?" as needing player state with no entity extracted at all (verified
# against qwen3:4b-instruct before this was added). These five examples
# fixed that and a similar general-knowledge-vs-"I"/"my" case.
ROUTE_SYSTEM_PROMPT = """You are a routing step for a Minecraft voice assistant. Given the player's question, extract:
- entities: Minecraft item/block/mob/mechanic names being asked about, as they'd appear as a wiki page title (e.g. "Diamond Sword", "Beacon"). Empty list if none.
- need_player_state: true ONLY if answering requires this specific player's own current inventory, position, or world state - not general game knowledge, even if phrased with "I"/"my".

Examples:
Q: How do I make a beacon?
A: {"entities": ["Beacon"], "need_player_state": false}

Q: How many diamonds do I have?
A: {"entities": [], "need_player_state": true}

Q: Where did I put my torches?
A: {"entities": [], "need_player_state": true}

Q: What does a wither skeleton drop?
A: {"entities": ["Wither Skeleton"], "need_player_state": false}

Q: Hey how is it going?
A: {"entities": [], "need_player_state": false}
"""

ANSWER_SYSTEM_PROMPT = (
    "You are a helpful Minecraft assistant. Answer using ONLY the provided context. "
    "If the context does not cover the question, say you don't know rather than guessing. "
    "Keep answers short, concise, and spoken-friendly. Only use Java Edition mechanics and names, not Bedrock Edition. "
    "Omit any unnecessary text or numerical values unless they are directly relevant to the question. "
    "Do not use emoji."
)


def route(question: str, *, model: str = MODEL_NAME) -> dict:
    """One constrained-JSON call: which entities, does this need player state."""
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": ROUTE_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        format=ROUTE_SCHEMA,
        options={"temperature": 0.1, "num_predict": 200},
    )
    return json.loads(response["message"]["content"])


def ensure_page(term: str) -> ResolvedTitle | None:
    """Resolve a term to a page and make sure wiki_prose is current for it.

    None if the term doesn't resolve to any page - the caller skips it
    rather than failing the whole turn over one bad entity.
    """
    try:
        resolved = resolve_title(term)
    except PageNotFound:
        return None

    if peek_stored_revid(resolved.title) != resolved.lastrevid:
        stale_cache = peek_cached_revid(resolved.title) != resolved.lastrevid
        raw = get_page(resolved.title, force_refresh=stale_cache)
        parsed = parse_page(raw.wikitext)
        store_page(title=resolved.title, pageid=resolved.pageid, revid=resolved.lastrevid, url=raw.url, page=parsed)

    return resolved


def _player_state_context() -> str | None:
    """Stub - no Player DB exists yet. A real seam, not a TODO to restructure later."""
    return "Player state is not available yet."


def gather_context(question: str, routed: dict, *, n_results: int = N_RESULTS) -> list[str]:
    """Turn a routing decision into retrieved context chunks."""
    chunks: list[str] = []

    for term in routed.get("entities", []):
        try:
            resolved = ensure_page(term)
        except Exception as exc:  # noqa: BLE001 - one bad entity (network hiccup, etc.)
            print(f"orchestrator: couldn't resolve/ingest {term!r}: {exc}")  # shouldn't sink the whole turn
            continue
        if resolved is None:
            continue
        chunks.extend(query_prose(resolved.title, question, n_results=n_results))

    if routed.get("need_player_state"):
        player_context = _player_state_context()
        if player_context:
            chunks.append(player_context)

    return chunks


def ask(question: str, *, model: str = MODEL_NAME, n_results: int = N_RESULTS) -> str:
    """Route, ensure, retrieve, answer - the whole synchronous pipeline for one turn."""
    routed = route(question, model=model)
    chunks = gather_context(question, routed, n_results=n_results)
    context = "\n\n---\n\n".join(chunks) if chunks else "No specific game information was found for this question."

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
    )
    return response["message"]["content"]


def _load_prompts(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def _run_one(question: str, *, show_routing: bool) -> None:
    routed = route(question)
    if show_routing:
        print(f"routed: {routed}")

    chunks = gather_context(question, routed)
    print(f"retrieved {len(chunks)} chunk(s)")

    context = "\n\n---\n\n".join(chunks) if chunks else "No specific game information was found for this question."
    response = ollama.chat(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
    )
    print(f"\n{response['message']['content']}")


if __name__ == "__main__":
    import argparse
    import sys

    # Windows consoles often aren't UTF-8 by default; a model response with
    # any non-ASCII character (an emoji, despite the system prompt saying
    # not to use one - confirmed happens) would otherwise crash print()
    # entirely instead of just looking slightly off.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Ask the wiki-backed assistant one question, or a batch from a file")
    parser.add_argument("question", nargs="?", help="A single question to ask")
    parser.add_argument("--batch", type=Path, help="Text file with one prompt per line (# lines are comments)")
    parser.add_argument("--show-routing", action="store_true", help="Print the router's decision first")
    args = parser.parse_args()

    if args.batch:
        prompts = _load_prompts(args.batch)
        for i, question in enumerate(prompts, 1):
            print(f"\n{'=' * 70}\n[{i}/{len(prompts)}] {question}\n{'=' * 70}")
            try:
                _run_one(question, show_routing=args.show_routing)
            except Exception as exc:  # noqa: BLE001 - one bad prompt shouldn't kill the batch
                print(f"ERROR: {exc}")
    elif args.question:
        _run_one(args.question, show_routing=args.show_routing)
    else:
        parser.error("provide a question, or --batch <file>")
