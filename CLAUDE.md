# CLAUDE.md

Guidance for Claude Code (and other AI assistants) working in this repository.

**Status: canonical.** This file is the authoritative technical reference
for this repo. Any AI assistant (Claude Code or otherwise) must read it
before planning or writing code here. Where it conflicts with `README.md`,
`ABOUT.txt`, `GHOST_LAYER.txt`, `RELEASE_ANNOUNCEMENT.txt`, or
`REPO_STRUCTURE_COMPLETE.txt` on anything code-related — architecture,
what exists, how to run it — this file wins; those are narrative/marketing
text, not specs (see below). This file does not extend to or ratify the
mythic "Ghost Layer Cosmology" content of those docs; it documents only the
real Python engine and how to work on it.

## What this repo actually is

GH0ST-LAY3R ("Ghost Layer Studio") is a **small, single-file-per-concern Python
demo package** with heavy cinematic/marketing framing in its prose docs. Read
the code in `core/`, `agents/`, and `scripts/` to understand actual behavior —
do not take the README, `ABOUT.txt`, `GHOST_LAYER.txt`,
`RELEASE_ANNOUNCEMENT.txt`, or `REPO_STRUCTURE_COMPLETE.txt` literally.

**Important gap between docs and reality:**
- `README.md` describes a `glce` Python package with kernels, AMR grids, MPI
  ghost-layer physics, a CLI (`glce run`), PyPI packaging, tests, and configs
  under `glce/`, `configs/`, `tests/`, `examples/` — **none of this exists in
  the repo.** It's a leftover scaffold/pitch from a cosmology-simulator concept
  that was never built here.
- `REPO_STRUCTURE_COMPLETE.txt` describes a completely different **TypeScript
  / Vercel / n8n** project (`core/engine/`, `modules/mythos/`, `api/routes/`,
  `automations/n8n/`, `package.json`, `tsconfig.json`, GitHub Actions
  CI/deploy). **None of this exists either.**
- The actual code that exists is the plain Python engine described below.

When asked to "add a feature" or "fix a bug," check whether the request is
about the real Python engine (`core/`, `agents/`, `scripts/`) or about one of
the aspirational systems described in the prose docs, and clarify with the
user if ambiguous rather than trying to build out the fictional scaffolding.

## Repository layout

```
GH0ST-LAY3R/
├── core/
│   ├── types.py           # IntentVector + OperatorAxis: shared, dependency-free data models
│   ├── substrate.py      # SubstrateState + SubstrateIngestion: turns raw input into metrics
│   ├── physics.py        # DefaultDominionPhysics: mutates SubstrateState based on intent tags
│   ├── engine.py         # GhostLayerEngine + create_default_engine(): main orchestrator
│   ├── oversoul.py       # Oversoul / DefaultOversoul: fuses agent outputs, does bounded recursion
│   ├── output.py         # OutputReactor / OutputEnvelope: final output shaping
│   └── registry.py       # Agent HQ registry schema (dataclasses only, no I/O) — see AGENT_HQ.md
├── agents/
│   ├── constellation.py  # Agent protocol, AgentConstellation registry, 4 example agents
│   └── registry.yaml     # Hand-maintained Agent HQ registry data (real agents/engine/operator only)
├── scripts/
│   ├── run_demo.py       # CLI-style entrypoint that boots the engine and prints JSON output
│   └── serve.py          # HQ HTTP server (dev-grade, stdlib only) — see "Running things"
├── IMAGES/                # Diagram/banner assets referenced by README.md
├── README.md              # Aspirational "Ghost Layer Cosmology Engine" pitch (see gap note above)
├── AGENT_HQ.md            # Agent HQ protocol + routing model (design spec, not implemented)
├── API_CONTRACT.md        # Draft REST contract for the future MSHOPS.NET backend (spec only)
├── ABOUT.txt, GHOST_LAYER.txt, RELEASE_ANNOUNCEMENT.txt  # Narrative/marketing text
├── REPO_STRUCTURE_COMPLETE.txt  # Aspirational TS/Vercel scaffold description (not implemented)
└── LICENSE.txt            # MIT, Copyright Guadalupe Gallegos (MatrixSecHub)
```

There is no `pyproject.toml`, `setup.py`, `requirements.txt`, test suite, or
CI configuration in this repo. There are no `__init__.py` files — `core` and
`agents` work as implicit namespace packages only when the repo root is on
`sys.path`.

## Runtime data flow

`scripts/run_demo.py` → `core.engine.create_default_engine()` wires up:

1. **`SubstrateIngestion`** (`core/substrate.py`) — normalizes raw input
   (str/dict/list/other) into a `SubstrateState` with computed
   `spectral_density` (token-uniqueness ratio) and `volatility`
   (punctuation/caps heuristic via `tanh`).
2. **`DefaultDominionPhysics`** (`core/physics.py`) — adjusts
   `state.volatility`/`spectral_density` based on `IntentVector.tags`
   (e.g. `"high-risk"`, `"escalate"`, `"critical"` boost volatility;
   `"focus"`/`"diffuse"` shift density).
3. **`AgentConstellation`** (`agents/constellation.py`) — runs each agent
   whose `supports()` predicate is true against the current
   intent/state, catching and recording per-agent exceptions rather than
   raising. Ships four example agents: `AdversarialIntelAgent`,
   `ContainmentAgent`, `OperatorDoctrineAgent`, and `RouteAdvisoryAgent`
   (advisory-only — suggests a generic routing "lane" via tag/volatility
   heuristics, without any real subsystem behind it; see "Extension point"
   below).
4. **`DefaultOversoul`** (`core/oversoul.py`) — `absorb()` fuses agent
   outputs into one dict; `recurse()` recursively refines
   `spectral_density` up to `EngineConfig.max_recursion` (default 3).
5. **`OutputReactor`** (`core/output.py`) — wraps everything into a final
   `OutputEnvelope` dict (`intent_id`, `source`, `operator_axis`,
   `spectral_density`, `volatility`, `payload`, `timestamp`, `meta`).

`GhostLayerEngine.run(raw, source=...)` in `core/engine.py` executes this
pipeline in one call and returns the final envelope as a `dict`.

## Circular import (fixed) + extension point

`IntentVector` and `OperatorAxis` used to live in `core/engine.py`, while
`core/physics.py`, `core/oversoul.py`, `core/output.py`, and
`agents/constellation.py` all imported `IntentVector` back from
`core.engine` — a circular import that made the demo unrunnable. Both
dataclasses now live in `core/types.py`, which has no dependency on
`core.engine`; the four modules above import `IntentVector` from
`core.types` instead. `core/engine.py` re-imports both names from
`core.types` for its own use (`EngineConfig.operator_axis`,
`IntentVector` construction in `_build_intent`). `PYTHONPATH=. python3
scripts/run_demo.py` now runs successfully.

(A second, previously-masked bug was uncovered by this fix and fixed at the
same time: `DefaultOversoul.config` used a mutable dataclass instance —
`OversoulConfig()` — as a field default, which Python's dataclass machinery
rejects. It now uses `field(default_factory=OversoulConfig)`.)

**Extension point for future subsystems:** a pluggable "module" — for any
future engine (the planned MSHOPS.NET-hosted agent layer, a flywheel, a bug
bounty HQ, a TTX engine, marketplace modules, Cloudflare Workers, etc.) — is
simply a class implementing the `Agent` Protocol in
`agents/constellation.py`: `name: str`, `supports(intent, state) -> bool`,
`run(intent, state) -> dict`, registered into `AgentConstellation`. There is
no separate `Module` type or registry-of-registries — `Agent` *is* the
module interface. None of those future subsystems exist in this repo; only
this interface does. `RouteAdvisoryAgent` (in `agents/constellation.py`) is
a minimal worked example: it always activates and returns a generic
`suggested_lane` string based on intent tags/volatility, without performing
any real routing or referencing any real subsystem — demonstrating the
pattern without building ahead of need. This extension point is formalized
into a registry and protocol in "Agent HQ design spec" below.

## Running things

There's no packaging, so the repo root must be on `PYTHONPATH`:

```bash
PYTHONPATH=. python3 scripts/run_demo.py              # one-shot demo, prints JSON
PYTHONPATH=. python3 scripts/serve.py [--port 8000]   # HQ HTTP server (see below)
```

`scripts/serve.py` starts a single-process, dev-grade HTTP server that wraps
`GhostLayerEngine` and exposes a subset of `API_CONTRACT.md` v2 endpoints:
`POST /intents`, `GET /hq/health`, `GET /audit`, `GET /escalations`,
`GET /agents`, `GET /engines`, `GET /operators`, `GET /agent-pools`. Default
bind is `127.0.0.1:8000`; pass `--host 0.0.0.0` to expose on LAN. All state
is in-memory and clears on restart. Optionally `pip install pyyaml` to parse
`agents/registry.yaml` at startup; without it a hardcoded fallback is used.

**GOV-4 gate:** `scripts/serve.py` is a bounded, operator-approved relaxation
of this repo's no-HTTP-server convention. It is not a production daemon — no
systemd unit, Docker image, or process manager is defined here. Any expansion
of its scope or a separate deployment configuration requires operator
sign-off per GOV-4 before being merged.

There are no tests and no linter configuration in this repo. If you add
tests, there's no existing convention to follow — pick something standard
(`pytest`, files under a `tests/` directory) and mention the choice.

## Conventions actually used in the code

- Python 3.10+ style: `from __future__ import annotations`, dataclasses,
  `typing.Protocol` for structural interfaces (`Agent`, `DominionPhysics`).
- Modules open with a docstring block titled `Ghost Layer Studio — <Module
  Name>` followed by a short responsibilities list — match this style if
  adding new `core/`/`agents/` modules.
- Agents are plain dataclasses implementing `supports()` + `run()`; add new
  agents by following that shape and registering them in
  `create_default_engine()`'s `AgentConstellation(agents=[...])` list.
- Shared, dependency-free data models (plain dataclasses with no logic used
  by more than one module) belong in `core/types.py`, not in whichever
  module happens to use them first — that's what caused the circular
  import documented above. `core/types.py` must never import from
  `core.engine` or anything that transitively does.
- The `Agent` Protocol (`agents/constellation.py`) is the intended plug-in
  point for future subsystems — see "Extension point for future
  subsystems" above. There is deliberately no separate `Module` name in
  code; "module" and "agent" refer to the same thing here.
- Logging goes through the module-level `logger` in `core/engine.py`
  (`logging.getLogger("ghost_layer_engine")`), not `print` (except in
  `scripts/run_demo.py`, which is a user-facing CLI script).
- No error handling for things that "can't happen"; the one deliberate
  try/except is in `AgentConstellation.run_all`, which isolates a failing
  agent so one bad agent doesn't kill the whole run.

## Agent HQ design spec (for MSHOPS.NET)

This repo is also the design source of truth for **Agent HQ** — the
registry, protocol, and routing model that a future external system,
MSHOPS.NET, will run in production. This section is a summary; the actual
specs live in dedicated files so this document stays scannable:

- **`core/registry.py`** (schema v3) — the full HQ schema: `EngineBinding`,
  `AgentRegistryEntry`, `OperatorEntry`, `EscalationEvent`,
  `AgentDeploymentRecord`, `EngineHealthRecord`, `RoutingTableEntry`,
  `CapabilityIndex`, `AuditEvent`, `OperatorSessionRecord`, `AgentPool`,
  `HQHealthRecord`, and a `RegistryRecord` union type; no logic, no I/O.
  Every record type carries a `type` discriminator field.
- **`agents/registry.yaml`** (schema v3) — the registry populated with what
  actually exists today: one engine (`ghost-layer-core`, with real
  `capabilities`), its four agents (each with real `capabilities`), and
  one HITL operator entry (`operators:`). No runtime-event data lives here —
  all v3 record types (`AgentDeploymentRecord`, `AuditEvent`, etc.) are
  managed by MSHOPS.NET. Hand-maintained; nothing in this repo parses it.
- **`AGENT_HQ.md`** — the full protocol: how agents register, how engines
  declare capabilities, the routing model (lanes, modes, statuses), the
  HITL Governance Layer (see below), the Escalation Lifecycle, Agent
  Lifecycle & Deployment, Multi-Engine Coordination, Operator Surfaces,
  HQ Health & Observability, Agent Pools, and a schema-versioning changelog.
- **`API_CONTRACT.md`** (draft v2) — a draft REST contract for the future
  MSHOPS.NET backend: intents, agents, engines, operators, escalations,
  deployments, engine health, routing table, capability index, audit trail,
  operator sessions, agent pools, and HQ health (`POST /intents`,
  `GET /agents`, `GET /operators`, `POST /escalations`,
  `PATCH /escalations/:id`, `POST /deployments`, `PATCH /deployments/:id`,
  `GET /audit`, `POST /operator/sessions`, `GET /hq/health`, etc.).

**The spec is not wired into the engine — with one bounded exception.**
`create_default_engine()` in `core/engine.py` is unchanged. `scripts/serve.py`
(see "Running things") is the sole integration layer: a dev-grade HTTP server
that wraps the engine and exposes a subset of `API_CONTRACT.md` v2 endpoints
for local development and integration testing. It does not add persistence,
enforcement, or routing logic — it is a thin HTTP skin, operator-approved per
GOV-4. The registry/protocol/API docs remain parallel design artifacts
describing a system that does not exist yet — do not wire additional spec
behavior into the engine unless explicitly asked; that would conflate
"documented plan" with "shipped behavior," which is exactly the gap this file
exists to prevent (see "What this repo actually is" above).

**Canonical ingestion order for anyone doing Agent HQ / MSHOPS.NET work:**

1. `CLAUDE.md` (this file) — canonical; wins on any conflict.
2. `AGENT_HQ.md` — protocol, routing model, HITL Governance Layer,
   Escalation Lifecycle, Agent Lifecycle & Deployment, Multi-Engine
   Coordination, Operator Surfaces, HQ Health & Observability, Agent Pools.
3. `API_CONTRACT.md` — draft REST contract built on the above.
4. `core/registry.py` — the typed schema backing all of the above.
5. `agents/registry.yaml` — the real, populated registry data.

Read in this order before writing any MSHOPS.NET-side code, which belongs
in a different repo/service, not here.

No lore or mythology has been introduced in this section or its linked
docs; it is written entirely in the technical register, consistent with
this file's canonical status.

## HITL Governance Layer

Agent HQ includes a governance layer defining how agents and the future
routing layer must behave toward the accountable Human-In-The-Loop (HITL)
operator. Full detail (rule tables, schema, YAML) lives in `AGENT_HQ.md`'s
"HITL Governance Layer (Operator Office)" section — this is a summary.

- **What HITL means:** there is one accountable human operator for this
  system (`operator_id: lupe`, registered HQ-level — not bound to any
  single engine — in `agents/registry.yaml`'s `operators:` list, schema
  `OperatorEntry` in `core/registry.py`). "HITL" and "operator" are plain
  technical terms here, not narrative ones.
- **How agents must behave (`GOV-1`–`GOV-7` in `AGENT_HQ.md`):** escalate
  on uncertainty; defer conflicting outputs to operator arbitration;
  require operator review on high-risk-tagged intents; require operator
  approval to register a new agent or engine; alert the operator when a
  safety boundary is touched; always run operator-originated intents in
  the `operator` priority lane; and shift the whole system toward more
  transparency, caution, verbosity, and deference whenever the operator
  is present.
- **How routing changes (`ROUTE-1`–`ROUTE-6` in `AGENT_HQ.md`):** for
  operator-originated intents, the operator's lane overrides any agent-
  suggested lane, operator tags supersede agent tags, and operator
  requests bypass throttling, `conditional`-mode gating, and `manual`-mode
  gating in the future routing layer. Separately (`ROUTE-6`), any intent
  with an open escalation is routed to a reserved `operator-review` lane
  regardless of who originated it.
- **The Escalation Lifecycle** (new in schema v2, full detail in
  `AGENT_HQ.md`): `GOV-1`, `GOV-2`, `GOV-3`, and `GOV-5` each produce an
  `EscalationEvent` (schema in `core/registry.py`) with a default severity
  (`low`/`medium`/`high`/`critical`) and a `pending -> acknowledged ->
  resolved` (or `dismissed`) state machine. **Only the registered operator
  may resolve or dismiss an escalation** — this is the concrete meaning of
  "operator arbitration" and "operator review required." `GOV-4` (new
  agent/engine approval) is deliberately *not* an escalation — it's
  represented by the registry's own `status` field instead.
- **How assistants must ingest and respect this layer:** treat `GOV-n` and
  `ROUTE-n` as binding constraints on any Agent HQ / MSHOPS.NET design
  work — a design that lets agents self-resolve conflicts without operator
  arbitration, lets non-operator requests bypass gating meant to be
  operator-exclusive, or lets any actor besides the operator resolve/
  dismiss an escalation, violates this layer and should be flagged, not
  built. Additionally, `AuditEvent` and `OperatorSessionRecord` are the
  observable surfaces through which GOV-7 and escalation lifecycle
  compliance is verified: a design that does not produce `AuditEvent`
  records for governance transitions, or that determines operator presence
  through any mechanism other than `OperatorSessionRecord.ended_at`,
  violates the spec.

**Same non-goals as the rest of Agent HQ:** no enforcement, dispatch, or
arbitration code exists in this repo implementing these rules or the
escalation state machine — `EscalationEvent` is a schema, not a queue or
database. No lore has been introduced; if narrative framing of "Operator
Office" or anything else is ever wanted, it belongs in a separate,
explicitly-labeled document (e.g. `GHOSTLAYERLORE.md`), never in this file.

## Working in this repo

- Treat the prose `.txt` files and `README.md` as narrative/marketing
  content, not specs — don't try to reconcile new code with their
  architecture diagrams (glce kernels, TypeScript modules, Vercel API
  routes, etc.) unless the user explicitly wants to build those out.
- The `IMAGES/` folder is large binary diagram assets used purely by
  `README.md`'s narrative sections; there's no need to touch these for code
  changes.
- Keep changes scoped to the actual Python engine unless told otherwise.
