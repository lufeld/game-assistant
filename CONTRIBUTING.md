# Contributing

This started as a university project and is published so it can be picked up
and continued by others. A few notes to get oriented quickly.

## Where to start

- [`README.md`](README.md) - overall architecture, setup, how to run it.
- [`src/modules/agent/README.md`](src/modules/agent/README.md) - the
  experimental ReAct agent orchestrator, including a documented list of what
  was tried and what actually worked. Good first read if you want to pick up
  where that comparison left off.
- [`mod/README.md`](mod/README.md) - the Fabric mod side, including real
  troubleshooting for the Java/Gradle toolchain.
- [`documentation/presentation.md`](documentation/presentation.md) - a Marp
  slide deck covering the whole project; the "Drawbacks & Known Issues" and
  "Future Work" sections are a good source of concrete next tasks.

## Branches

`main` is the stable branch, `develop` is where ongoing work integrates.
Branch off `develop`, open pull requests back into `develop`.

## Before opening a pull request

```
pytest
```

The suite (wiki pipeline, player-state pipeline, agent orchestrator loop)
runs against real I/O - a tmp SQLite DB, a real WebSocket connection, an
injected `chat_fn` standing in for the Ollama network boundary - rather than
mocks. Keep new tests in that style rather than mocking internals.

`orchestrator.py` (the router) and the voice loop aren't covered by the
automated suite - they're exercised manually via
`src/modules/orchestrator_prompts.txt` and
`src/modules/agent/prompts.txt` (`python <orchestrator file> --batch
<prompts file>`). If you touch either orchestrator, run its batch file and
read through the output before and after your change.

## Code conventions already in place

- **Minimal comments.** Code should explain *what* it does by being
  readable; comments are reserved for *why* - a non-obvious constraint, a
  workaround, a reason a simpler approach doesn't work. If you're adding a
  comment that restates the code, it probably isn't needed.
- **No speculative abstraction.** Several modules note explicitly where a
  more general design was considered and rejected (e.g. the Graph RAG
  attempt documented in the presentation). Prefer the direct solution to the
  problem in front of you over one that anticipates future requirements.
- **Reuse over duplication, especially between the two orchestrators.** The
  agent orchestrator imports the router's `ensure_page()` rather than
  reimplementing it; the one new function it needed in a shared module
  (`resolve.search_candidates`) was added additively, without changing any
  existing function's behavior. If you're changing a module both
  orchestrators depend on, check `git log` / the relevant README for why it
  was built the way it was, and run both orchestrators' batch files
  afterward to confirm neither regressed.
- **Everything runs locally, by design.** No cloud API keys, no telemetry.
  If a contribution would require one, that's a design discussion to have
  first, not an implementation detail.

## Reporting a bad answer

If you find a question the assistant answers wrong, the most useful report
includes: the exact question, which orchestrator (router or agent), and
`--show-routing` (router) or `--show-trace --show-thinking` (agent) output
if you can reproduce it. See `documentation/trace/` for the format this
project already uses to capture and document these.
