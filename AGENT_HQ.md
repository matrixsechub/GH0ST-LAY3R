# Agent HQ — Protocol & Routing Model

> **Status: design specification.** Nothing in this document is
> implemented as a server, daemon, or deployment in this repo. It
> describes the architecture a future MSHOPS.NET backend will
> implement, and it formalizes the extension point that already exists
> in this repo's code (the `Agent` Protocol in `agents/constellation.py`).
> `CLAUDE.md` is canonical — if anything here conflicts with the actual
> code, `CLAUDE.md` and the code win.

## Concepts

- **Engine** — a runtime that can process an `IntentVector` and produce
  structured output. Exactly one engine exists today: `ghost-layer-core`,
  the Python pipeline in this repo (`core.engine.create_default_engine`).
  Any other engine name in the examples below (flywheel, bug-bounty-hq,
  ttx, marketplace) is **illustrative only** — none of them exist in code.
- **Agent (= Module)** — a class implementing the `Agent` Protocol
  (`agents/constellation.py`): `name: str`, `supports(intent, state) ->
  bool`, `run(intent, state) -> dict`. This is the only pluggable-unit
  abstraction in the codebase; "module" and "agent" are the same thing
  (see `CLAUDE.md`'s Conventions section).
- **Registry** — the catalog of known agents and engines, described by
  the schema in `core/registry.py` and populated, for what actually
  exists today, in `agents/registry.yaml`. The registry is a hand-
  maintained spec artifact; nothing in this repo parses or enforces it
  at runtime.
- **Intent** — an `IntentVector` (`core/types.py`): `id`, `source`,
  `description`, `tags`.
- **Lane** — a free-form string an agent may *suggest* as a routing
  target for an intent (e.g. `"containment-review"`). Lanes are
  advisory only — see "Routing model" below.
- **Mode** — declares the trigger behavior expected of an agent's
  `supports()`: `always-on`, `conditional`, or `manual`.
- **Status** — the registry's lifecycle marker for an agent or engine:
  `active`, `experimental`, `deprecated`, or `planned`.

## Registration protocol

**Today (real, in this repo):**

1. Implement the `Agent` Protocol as a plain dataclass in
   `agents/constellation.py` (or a new module under `agents/`), matching
   the style of `AdversarialIntelAgent` / `RouteAdvisoryAgent`.
2. Add a matching entry to `agents/registry.yaml` under `agents:`,
   following the `AgentRegistryEntry` schema in `core/registry.py`.
3. If the agent should be live in the one real engine, add it to
   `create_default_engine()`'s `AgentConstellation(agents=[...])` list
   in `core/engine.py`. Registry membership and engine wiring are
   deliberately separate steps — an agent can be documented in the
   registry (e.g. `status: experimental`) without being wired in yet.

**Future (MSHOPS.NET, not implemented here):** dynamic registration over
HTTP (`POST /agents` — see `API_CONTRACT.md`), with the hand-maintained
YAML file replaced by a live registry service. `core/registry.py`'s field
names are chosen so a future JSON/YAML-over-HTTP registry can reuse them
without a redesign.

## Engine capability declaration

Today there is exactly one engine, declared once in
`agents/registry.yaml` under `engines:`:

```yaml
engines:
  - id: ghost-layer-core
    status: active
    entrypoint: core.engine.create_default_engine
```

A future engine would declare itself the same way, plus a `capabilities`
list of tags it can handle. The entry below is **illustrative only** —
it is not a real registry entry and `flywheel` does not exist in code:

```yaml
# illustrative — not implemented, not in agents/registry.yaml
engines:
  - id: flywheel
    status: planned
    description: "..."
    capabilities: [growth-loop, retention]
```

## Routing model

- Any agent's `run()` output *may* include a routing suggestion using
  this reserved shape (already used by `RouteAdvisoryAgent`):

  ```json
  {"suggested_lane": "containment-review", "confidence": "heuristic", "basis": {...}}
  ```

- **Modes** describe the trigger behavior a reader should expect from
  `supports()`:
  - `always-on` — `supports()` unconditionally returns `True`
    (`OperatorDoctrineAgent`, `RouteAdvisoryAgent`).
  - `conditional` — `supports()` inspects intent tags / substrate state
    (`AdversarialIntelAgent`, `ContainmentAgent`).
  - `manual` — reserved for agents that should *never* auto-fire via
    `AgentConstellation.run_all()`; invoked only on direct request (the
    future `POST /agents/:id/run`). No agent in this repo uses this mode
    yet.
- **This repo's engine does not act on `suggested_lane`.**
  `GhostLayerEngine.run()` only collects whatever agents fired into
  `payload.agents` in the output envelope. Interpreting `suggested_lane`
  and deciding what happens next (dispatching to a different engine,
  etc.) is a downstream concern — MSHOPS.NET's job, not this repo's.
- Precedence between multiple simultaneous lane suggestions (once more
  than one routing agent exists) is undefined here and left to whatever
  downstream router MSHOPS.NET implements.

## Non-goals

- No HTTP server, daemon, or deployment config lives in this repo, and
  none should be added here.
- No dynamic/plugin-loading mechanism exists or is planned for this
  repo — the registry is a hand-maintained spec, not a loader.
- This document does not describe or ratify any Ghost Layer mythology;
  see `CLAUDE.md`'s canonical-status note. No lore has been introduced
  here.
