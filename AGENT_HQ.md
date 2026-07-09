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
- **Escalation** — a record of a governance rule (`GOV-n`) firing, requiring
  operator attention before an intent's result is treated as final. Schema:
  `EscalationEvent` in `core/registry.py`. See "Escalation Lifecycle" below.
- **Type** — every registry record (`EngineBinding`, `AgentRegistryEntry`,
  `OperatorEntry`, `EscalationEvent`) carries a fixed `type` discriminator
  (`"engine"`, `"agent"`, `"operator"`, `"escalation"`) so a consumer
  reading a mixed list of records can tell them apart without relying on
  which YAML key or list they came from.

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
`agents/registry.yaml` under `engines:`. As of schema v2, `capabilities`
is a real, typed field (`EngineBinding.capabilities: List[str]`), not just
an illustrative idea — populated here with the five real pipeline stages
named in `CLAUDE.md`'s "Runtime data flow":

```yaml
engines:
  - type: engine
    id: ghost-layer-core
    status: active
    entrypoint: core.engine.create_default_engine
    capabilities: [substrate-ingestion, dominion-physics, agent-constellation, oversoul-fusion, output-reactor]
```

A future engine would declare itself the same way. The entry below is
**illustrative only** — it is not a real registry entry and `flywheel`
does not exist in code:

```yaml
# illustrative — not implemented, not in agents/registry.yaml
engines:
  - type: engine
    id: flywheel
    status: planned
    description: "..."
    capabilities: [growth-loop, retention]
```

Declaring capabilities does not imply any dispatch mechanism that matches
intents to engines by capability — no such mechanism exists in this repo;
that is MSHOPS.NET's job, using this field as its input.

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

GOV-1, GOV-2, GOV-3, and GOV-5 are the rules that produce an `EscalationEvent`
— see "Escalation Lifecycle" below for the mapping and severities. GOV-4 is
deliberately *not* modeled as an escalation: approval for a new agent/engine
is represented by the registry's own `status` field staying `planned` or
`experimental` until the operator promotes it to `active`, not by a
separate event record. GOV-6 and GOV-7 never produce escalations — they are
routing/posture rules, not alert conditions.

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
| ROUTE-6 | Any intent with an `EscalationEvent` in `pending` or `acknowledged` status is routed to a reserved `operator-review` lane, overriding any `suggested_lane`, until the escalation reaches `resolved` or `dismissed` |

ROUTE-3 through ROUTE-6 describe bypassing/gating mechanisms (throttling, a
dispatch layer with mode gating, an escalation-aware router) that do not
exist in this repo — they are requirements on whatever MSHOPS.NET builds,
not a description of `AgentConstellation.run_all()`, which today runs
every agent whose `supports()` returns `True` with no operator- or
escalation-awareness at all.

### Registry integration

`core/registry.py` adds `OperatorEntry` for this layer's identity record
(see "Operator identity" above) and `EscalationEvent` for its alerts (see
"Escalation Lifecycle" below):

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

`type: "operator"` (and `"engine"` / `"agent"` / `"escalation"` on the other
three record types) exists so a future consumer that reads a mixed list of
registry records can discriminate by that field rather than by which YAML
key or list an entry came from — formalized as the `RegistryRecord` union
type alias in `core/registry.py`. `agents/registry.yaml` has a third
top-level list, `operators:`, alongside `engines:` and `agents:` —
populated today with exactly the one entry shown above. There is no
`escalations:` list in `agents/registry.yaml`: escalations are runtime
events, not hand-maintained registry entries (see below).

## Escalation Lifecycle

> **Status: design specification, schema only.** No code in this repo
> creates, stores, transitions, or resolves an `EscalationEvent`. This
> section defines the shape and state machine a future dispatch/governance
> layer (MSHOPS.NET) must implement to satisfy GOV-1, GOV-2, GOV-3, and
> GOV-5 above.

### Schema

```python
@dataclass
class EscalationEvent:
    id: str
    trigger_rule: str  # e.g. "GOV-3"
    intent_id: str
    severity: EscalationSeverity  # "low" | "medium" | "high" | "critical"
    reason: str
    agent_ids: List[str] = field(default_factory=list)  # empty if not agent-specific
    status: EscalationStatus = "pending"  # "pending" | "acknowledged" | "resolved" | "dismissed"
    created_at: str = ""
    resolved_at: Optional[str] = None
    resolution: str = ""
    type: Literal["escalation"] = "escalation"
```

`agent_ids` is a list, not a single field, because some triggers (GOV-2,
conflicting outputs) inherently involve more than one agent, and others
(GOV-3, GOV-5) may not be tied to any specific agent at all.

### GOV-n -> severity mapping

| Trigger | Produces an `EscalationEvent`? | Default severity |
|---|---|---|
| GOV-1 (agent uncertain) | Yes | `low` |
| GOV-2 (conflicting outputs) | Yes | `medium` |
| GOV-3 (high-risk tag) | Yes | `high` |
| GOV-4 (new agent/engine registration) | No — see registry `status` transition, above | — |
| GOV-5 (safety boundary touched) | Yes | `critical` |
| GOV-6 (operator priority lane) | No — routing rule, not an alert condition | — |
| GOV-7 (operator presence posture shift) | No — behavioral posture, not an alert condition | — |

### State machine

`pending -> acknowledged -> resolved`, or `pending -> dismissed`, or
`acknowledged -> dismissed`. `resolved` means an action was taken;
`dismissed` means the operator determined no action was needed. **Only the
registered operator** (`operator_id` matching the `operators:` entry) may
transition an `EscalationEvent` to `resolved` or `dismissed` — this is what
"operator arbitration" (GOV-2) and "operator review required" (GOV-3) mean
concretely. Any actor may create a `pending` event or move it to
`acknowledged`.

An intent with an escalation in `pending` or `acknowledged` status is not
considered final (GOV-1/GOV-2/GOV-3/GOV-5's point) and is routed per
ROUTE-6 above.

### Illustrative example

The following is **not real data** — nothing in this repo produces or
stores this. It illustrates the shape only:

```json
{
  "id": "esc-example-001",
  "type": "escalation",
  "trigger_rule": "GOV-3",
  "intent_id": "bed7588c-6866-49b9-9a26-9fea22f612ac",
  "agent_ids": ["ContainmentAgent"],
  "severity": "high",
  "reason": "Intent tagged high-risk; operator review required before result is final.",
  "status": "pending",
  "created_at": "2026-07-07T10:09:40Z",
  "resolved_at": null,
  "resolution": ""
}
```

## Agent Lifecycle & Deployment

> **Status: design specification, schema only.** No code in this repo
> creates or transitions `AgentDeploymentRecord`s. This section defines
> the lifecycle a future MSHOPS.NET deployment layer must implement.

### Registry status vs. deployment status

Two orthogonal lifecycle axes track every agent:

- **`AgentStatus`** (field on `AgentRegistryEntry`) — the **registry
  lifecycle**: the human-maintained design-maturity stage of the agent
  spec itself. Transitions: `planned` → `experimental` → `active` →
  `deprecated`. GOV-4 requires operator approval for any promotion.
  This is a spec-level marker, not a runtime signal.

- **`DeploymentStatus`** (field on `AgentDeploymentRecord`) — the
  **runtime lifecycle** of one concrete deployment of an agent into one
  engine instance. Independent of registry status: a registry-`active`
  agent can have a runtime-`failed` deployment; a registry-`planned`
  agent has no deployment record at all.

### Deployment state machine

```
pending ──► deploying ──► healthy
                │              │
                └──► failed ◄──┘
                         │
                         └──► rolled_back
```

`pending`: deployment record created, not yet started.
`deploying`: deployment in progress; agent not yet receiving intents.
`healthy`: deployment succeeded; agent is live.
`failed`: deployment or runtime error; agent is not receiving intents.
`rolled_back`: MSHOPS.NET created a new `AgentDeploymentRecord` targeting
`rollback_to` version; this record is terminal.
`degraded`: healthy but operating below normal capacity (e.g. partial
capability failure); agent still receives intents.

### Rules

- `deployed_by` must be the registered operator's `operator_id` (GOV-4:
  operator approval is required to deploy any agent, including a new
  deployment of an already-`active` agent). A deployment of a `planned`
  or `experimental` agent implicitly constitutes a registry promotion and
  requires operator sign-off.
- Rollback is executed by creating a new `AgentDeploymentRecord` with the
  target `version` (taken from `rollback_to` on the failed record) — not
  by mutating the existing record. The failed record's `ended_at` is set
  and its `status` transitions to `rolled_back`.
- Every `DeploymentStatus` transition must produce an
  `AuditEvent(event_type="deployment.status_changed")`.

---

## Multi-Engine Coordination

> **Status: design specification.** The only real engine today is
> `ghost-layer-core`. All dispatch, capability indexing, and health-check
> behavior described here is MSHOPS.NET's responsibility to implement.
> Nothing in this repo implements routing, dispatch, or health checks.

### Capability-based dispatch

A `RoutingTableEntry` maps an intent pattern (tag set and/or capability
string) to a target engine. MSHOPS.NET's dispatch layer evaluates entries
in ascending `priority` order (lower number = evaluated first); ties are
broken by `id` in lexicographic order. It dispatches to the first matching
`active` entry whose `target_engine_id` resolves to a `healthy` engine.

**All `RoutingTableEntry` logic is subordinate to ROUTE-1 through ROUTE-6.**
In particular, ROUTE-6 routes any intent with an open escalation to
`operator-review`, overriding any routing table entry regardless of
priority. ROUTE-1 overrides `suggested_lane` for operator-originated
intents.

### `CapabilityIndex`

Pre-built by MSHOPS.NET from `EngineBinding.capabilities` and
`AgentRegistryEntry.capabilities` at registration time. One
`CapabilityIndex` record per named capability string. Enables
capability-based dispatch without scanning the full registry on every
intent. MSHOPS.NET must rebuild the index (trigger:
`POST /capabilities/rebuild`, which produces
`AuditEvent(event_type="capability_index.rebuilt")`) whenever an engine
or agent is registered, updated, or deregistered.

### `EngineHealthRecord`

Written by MSHOPS.NET's health-check layer on a schedule. The dispatch
layer must not route intents to an engine whose most recent
`EngineHealthRecord.status` is `unavailable`. A `degraded` engine may
still receive traffic — at lower priority or behind a circuit-breaker;
MSHOPS.NET defines the policy, this repo only defines the status values.

### Cross-engine conflict resolution

If two engines match a routing table query with equal priority and both
are `healthy`, GOV-2 applies: the conflict is surfaced to the operator
via an `EscalationEvent` rather than resolved automatically. No agent
or system component may self-resolve a multi-engine tie without operator
arbitration.

### Single-engine state today

`ghost-layer-core` is the only real engine. The routing table is empty
in this repo; MSHOPS.NET populates it as additional engines are added.

---

## Operator Surfaces

> **Status: design specification.** The surfaces described here are
> operator-facing read/write access patterns defined by the API contract
> (`API_CONTRACT.md`). No implementation exists in this repo.

### Audit trail (`AuditEvent`)

Every significant state transition must produce an append-only
`AuditEvent`. The following transitions are mandatory:

| Transition | `event_type` |
|---|---|
| Escalation created | `escalation.created` |
| Escalation status changed | `escalation.status_changed` |
| Deployment status changed | `deployment.status_changed` |
| Operator session opened | `operator.session_opened` |
| Operator session closed | `operator.session_closed` |
| GOV-n rule fired | `gov_rule.fired` |
| Routing table entry added/changed/deleted | `routing_table.updated` |
| Capability index rebuilt | `capability_index.rebuilt` |

MSHOPS.NET owns the write path. The HQ provides `GET /audit` (filterable
by `actor_id`, `actor_type`, `target_id`, `target_type`, `event_type`,
and `since`/`until` range) and `GET /audit/:id` for the operator to read.
Audit records are append-only — no `POST`, `PATCH`, or `DELETE` for
`AuditEvent` records.

### Operator session (`OperatorSessionRecord`)

The **single authoritative signal** for GOV-7 posture activation. A
session is "active" when `ended_at` is `None`. Systems that need to know
whether the operator is online must read the most recent
`OperatorSessionRecord` for each registered `operator_id`; no secondary
mechanism (heartbeat, login state, etc.) is defined or recognized.

Only the registered operator may open or close their own session.
Opening a session produces `AuditEvent(event_type="operator.session_opened")`;
closing produces `AuditEvent(event_type="operator.session_closed")`.

### Active escalation queue

The operator's primary work queue is derived from
`GET /escalations?status=pending,acknowledged`. No separate queue schema
is needed — the filtered escalation list *is* the queue. ROUTE-6 ensures
any intent associated with a `pending` or `acknowledged` escalation is
routed to the reserved `operator-review` lane until the escalation
reaches `resolved` or `dismissed`.

### Read/write authority table

| Resource | Operator can read? | Operator can write? | Others can write? |
|---|---|---|---|
| `AuditEvent` | Yes | No (append-only, system-written) | No |
| `EscalationEvent` | Yes | `resolved`/`dismissed` only | `pending`/`acknowledged` (any actor) |
| `OperatorSessionRecord` | Yes | Open/close own session only | No |
| `AgentDeploymentRecord` | Yes | Create + status transitions | No (GOV-4) |
| `RoutingTableEntry` | Yes | Create/update/delete | No (operator auth required) |
| `HQHealthRecord` | Yes | No (health-check layer only) | Health-check layer only |

---

## HQ Health & Observability

> **Status: design specification.** No health-check layer exists in this
> repo. `HQHealthRecord` is a schema; MSHOPS.NET implements the writer.

`HQHealthRecord` is a point-in-time snapshot of HQ-wide health. MSHOPS.NET's
health-check layer computes and writes it on a regular schedule (recommended:
at least once per minute) by aggregating the most recent `EngineHealthRecord`
for each registered engine, counting open escalations, and checking
`OperatorSessionRecord` for active sessions.

**Field semantics:**

- `active_engine_ids`: engines with `EngineHealthRecord.status == "healthy"`.
- `degraded_engine_ids`: engines with `status == "degraded"`. Disjoint from
  `unavailable_engine_ids`.
- `unavailable_engine_ids`: engines with `status == "unavailable"`. The
  routing layer must not dispatch to these engines.
- `active_agent_ids`: agents with at least one `AgentDeploymentRecord` in
  `status == "healthy"` or `"degraded"` (i.e. currently receiving intents).
- `open_escalation_count`: count of `EscalationEvent` records where
  `status` is `"pending"` or `"acknowledged"`.
- `operator_online`: `True` if and only if there is at least one
  `OperatorSessionRecord` with `ended_at == None` for any registered
  `operator_id`. This is the single authoritative source for GOV-7
  posture activation.

`GET /hq/health` returns the most recent `HQHealthRecord`. Callers that
need current state must not cache this response beyond the health-check
write interval.

---

## Agent Pools

> **Status: design specification.** `AgentConstellation.run_all()` in
> this repo has no pool awareness. Pool semantics are for MSHOPS.NET's
> routing and governance layer to implement.

An `AgentPool` is a named, ordered grouping of agents bound to one engine.
It enables routing decisions at the group level — a `RoutingTableEntry`
may target a pool by matching on its `tags`, dispatching all member agents
rather than the engine's full constellation.

### `run_mode`

- `"sequential"` (default): member agents run in the listed order. A
  per-agent exception does not block subsequent agents — matching
  `AgentConstellation`'s existing exception-isolating behavior in
  `run_all()`.
- `"parallel"`: MSHOPS.NET runs all member agents concurrently and merges
  outputs. Applicable only when agents do not depend on each other's
  outputs for the same intent.

### Governance interaction

GOV-2 (conflicting outputs) applies across agents within the same pool —
if two agents in the pool produce conflicting outputs, the operator
arbitrates; the pool does not self-resolve the conflict.

ROUTE-5 (operator-originated intents activate all relevant agents) applies
per pool: if an operator-originated intent matches a pool's tags, all
agents in that pool run regardless of declared `mode`, including
`manual`-mode agents.

### Relationship to `AgentConstellation`

`AgentPool` is a registry/routing concept only. The running
`AgentConstellation` in this repo does not read pool definitions — it runs
every agent whose `supports()` returns `True` with no pool awareness. A
future MSHOPS.NET routing layer would use pool definitions to selectively
dispatch subsets of agents.

---

## Schema versioning

`agents/registry.yaml`'s `schema_version` field tracks the shape of
`core/registry.py`. History:

- **v1** — initial schema: `EngineBinding`, `AgentRegistryEntry`,
  `OperatorEntry`.
- **v2** — adds a `type` discriminator to `EngineBinding` and
  `AgentRegistryEntry` (matching `OperatorEntry`'s existing pattern);
  promotes `capabilities` on `EngineBinding` and `AgentRegistryEntry` from
  an illustrated idea to a real, populated field; adds the
  `EscalationEvent` schema and its lifecycle; adds the `RegistryRecord`
  union type alias.
- **v3** — adds runtime-event schemas: `AgentDeploymentRecord` (deployment
  lifecycle), `EngineHealthRecord` (per-engine health snapshot),
  `RoutingTableEntry` (capability/tag-based dispatch table),
  `CapabilityIndex` (pre-built capability lookup), `AuditEvent` (immutable
  governance audit trail), `OperatorSessionRecord` (GOV-7 presence signal),
  `AgentPool` (agent grouping for routing), `HQHealthRecord` (HQ-wide
  health snapshot); expands `RegistryRecord` union to include all new
  types; adds `DeploymentStatus`, `EngineHealthStatus`, and
  `AuditActorType` type aliases; adds `Any` to the `typing` import.

Bumping `schema_version` is a documentation signal only — nothing in this
repo validates data against it automatically.

## Ingestion note

Any assistant doing Agent HQ or MSHOPS.NET design work must treat GOV-1
through GOV-7 and ROUTE-1 through ROUTE-6 as binding constraints on any
proposed design — e.g. a design that lets agents auto-resolve conflicting
outputs without operator arbitration (contradicts GOV-2), that lets a
non-operator request bypass `conditional` gating (contradicts ROUTE-4
being operator-specific), or that lets any actor other than the operator
resolve or dismiss an escalation (contradicts the Escalation Lifecycle's
state machine), violates this layer and should be flagged rather than
built.

## Non-goals

- No HTTP server, daemon, or deployment config lives in this repo, and
  none should be added here.
- No dynamic/plugin-loading mechanism exists or is planned for this
  repo — the registry is a hand-maintained spec, not a loader.
- No enforcement, dispatch, throttling, or arbitration code implements
  the HITL Governance Layer's `GOV-n`/`ROUTE-n` rules or the Escalation
  Lifecycle's state machine — they are policy for future design work, not
  running behavior. `EscalationEvent` is a schema, not a queue, database,
  or event bus.
- This document does not describe or ratify any Ghost Layer mythology;
  see `CLAUDE.md`'s canonical-status note. No lore has been introduced
  here, including in the HITL Governance Layer and Escalation Lifecycle
  sections — "operator", "root", "HQ-level", "escalation", and "severity"
  are plain technical terms, not narrative ones.
