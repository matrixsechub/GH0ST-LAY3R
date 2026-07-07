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
- **Operator** — the accountable Human-In-The-Loop (HITL) for this system,
  registered as an HQ-level entry (not bound to any single engine). See
  "HITL Governance Layer" below.

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
- **All of the above is subordinate to the HITL Governance Layer below.**
  Where an operator-originated intent is involved, the routing overrides
  in that section take precedence over everything in this section.

## HITL Governance Layer (Operator Office)

> **Status: design specification, technical governance — not lore.**
> This section defines how agents and the future routing layer must
> behave toward the Human-In-The-Loop (HITL) operator. It is policy for
> a system that does not run yet: no runtime code in this repo enforces
> any rule below, there is no throttling mechanism, no dispatch layer,
> and no arbitration logic implemented here. These rules bind future
> design work (this repo and MSHOPS.NET), not current engine behavior.

### Operator identity

The operator is registered as an HQ-level entry — bound to Agent HQ as a
whole, not to any single engine (contrast with `AgentRegistryEntry.engine`,
which always points at one `EngineBinding`). Schema: `OperatorEntry` in
`core/registry.py`; data: the `operators:` list in `agents/registry.yaml`.

The canonical operator entry that exists today:

```yaml
operators:
  - type: operator
    operator_id: lupe
    role: HITL
    authority: root
    priority_lane: operator
    escalation_required: true
    capabilities: [override, arbitration, review, priority]
    binding: HQ-level
```

This is a plain identity record, not a mythic figure — `authority: root`
means "highest authority level in this schema," nothing more. No other
authority levels are defined or implemented; there is exactly one operator
today.

### Governance rules

Every agent — today's four and any future one — is expected to honor these
rules once a real dispatch/arbitration layer exists (MSHOPS.NET). Numbered
for stable reference (`GOV-n`):

| Rule | Condition | Required behavior |
|---|---|---|
| GOV-1 | Agent is uncertain of its own output | Escalate to the operator rather than guessing |
| GOV-2 | Two or more agents produce conflicting outputs | Operator arbitrates; no agent self-resolves the conflict |
| GOV-3 | Intent carries a high-risk tag (`high-risk`, `escalate`, `critical`) | Operator review is required before the result is treated as final |
| GOV-4 | A new agent or engine is being registered | Operator approval is required (extends "Registration protocol" above) |
| GOV-5 | Any safety boundary is touched | Operator is alerted |
| GOV-6 | Intent originates from the operator | Always dispatched in the `operator` priority lane |
| GOV-7 | Operator is present/active in a session | System-wide posture shifts toward: more transparency, more caution, more verbosity, more deference |

GOV-1 through GOV-5 describe *when* to defer to the operator; GOV-6 and
GOV-7 describe how the system behaves differently *because* the operator
is the one acting. None of this is enforced by code in this repo — it is
the behavioral contract future agent/engine implementations (here or in
MSHOPS.NET) must satisfy.

### Routing integration

When an intent is operator-originated, it changes how the (future, not
implemented) routing layer behaves, taking precedence over the base
"Routing model" above. Numbered for stable reference (`ROUTE-n`):

| Rule | Behavior |
|---|---|
| ROUTE-1 | The operator's `priority_lane` (`operator`) overrides any `suggested_lane` any agent proposes |
| ROUTE-2 | Tags on an operator-originated intent supersede tags any agent would otherwise assign |
| ROUTE-3 | Operator requests bypass any throttling the future routing layer implements |
| ROUTE-4 | Operator requests bypass `conditional`-mode gating — a `conditional` agent's `supports()` is not consulted; it runs |
| ROUTE-5 | Operator requests activate all relevant agents regardless of declared `mode`, including `manual`-mode agents that never auto-fire otherwise |

ROUTE-3 through ROUTE-5 describe bypassing mechanisms (throttling, a
dispatch layer with mode gating) that do not exist in this repo — they are
requirements on whatever MSHOPS.NET builds, not a description of
`AgentConstellation.run_all()`, which today runs every agent whose
`supports()` returns `True` with no operator-awareness at all.

### Registry integration

`core/registry.py` adds one dataclass for this layer:

```python
@dataclass
class OperatorEntry:
    operator_id: str
    role: str
    authority: str
    priority_lane: str
    escalation_required: bool
    type: Literal["operator"] = "operator"
    capabilities: List[str] = field(default_factory=list)
    binding: str = "HQ-level"
```

`type: "operator"` exists so a future consumer that reads a mixed list of
registry entries (agents, engines, operators) can discriminate by that
field rather than by which YAML key an entry came from. `agents/registry.yaml`
gains a third top-level list, `operators:`, alongside `engines:` and
`agents:` — populated today with exactly the one entry shown above.

### Ingestion note

Any assistant doing Agent HQ or MSHOPS.NET design work must treat GOV-1
through GOV-7 and ROUTE-1 through ROUTE-5 as binding constraints on any
proposed design — e.g. a design that lets agents auto-resolve conflicting
outputs without operator arbitration (contradicts GOV-2), or that lets a
non-operator request bypass `conditional` gating (contradicts ROUTE-4
being operator-specific), violates this layer and should be flagged rather
than built.

## Non-goals

- No HTTP server, daemon, or deployment config lives in this repo, and
  none should be added here.
- No dynamic/plugin-loading mechanism exists or is planned for this
  repo — the registry is a hand-maintained spec, not a loader.
- No enforcement, dispatch, throttling, or arbitration code implements
  the HITL Governance Layer's `GOV-n`/`ROUTE-n` rules — they are policy
  for future design work, not running behavior.
- This document does not describe or ratify any Ghost Layer mythology;
  see `CLAUDE.md`'s canonical-status note. No lore has been introduced
  here, including in the HITL Governance Layer section — "operator",
  "root", and "HQ-level" are plain technical terms, not narrative ones.
