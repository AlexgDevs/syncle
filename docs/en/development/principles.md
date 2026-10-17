# Development Principles

Key concepts and principles of Syncle. This document answers "why it is
set up this way" and "how to make decisions"; checkable rules live in
[standards.md](standards.md); how the principles are implemented — in
[patterns.md](patterns.md).

## Architectural concepts

### Layered architecture

```
interfaces (bot, worker, api)  →  modules (domain)  →  core (infrastructure)
```

- **Modules** (`src/modules/*`) — domain logic: analytics, SEO, legal
  scanner, finance, etc. The heart of the product.
- **Core** (`src/core/*`) — infrastructure that knows nothing about the
  domain: Redis, HTTP, LLM, jobs, documents, DB.
- **Interfaces** — entry points adapting the outside world to the domain:
  - **bot** (aiogram) — the product's primary interface;
  - **worker** (Taskiq) — background job execution;
  - **api** (HTTP) — a scaffold for a future interface.

The domain does not know who calls it. A new interface (the same api)
is therefore added as an adapter, not by editing modules.

### Modularity and ownership

A module is a boundary of responsibility. Each module is self-contained:

- its own schemas (`schemas.py`), errors (`errors.py`), tariffs/constants;
- a public service (`service.py`) — the only channel for neighbours;
- its own background jobs (`jobs.py`) when needed.

The "work inside your module" rule: a feature's changes stay in the
module and its bot adapter; crossing boundaries (editing a neighbour or
core) means a separate agreement is needed, not a "quick fix".
Cross-module interaction goes only through public services and schemas,
never through internal files.

## Principles

### SOLID

- **S — single responsibility.** A module does one domain thing
  (finance ≠ reputation ≠ legal). A file within a module is also one
  reason to change: parser, detector, calculator are separate.
- **O — open/closed.** New behaviour = a new implementation behind a
  port, not editing an existing one. Example: `JobRunner` did not
  change when Taskiq arrived — `TaskiqJobRunner` appeared.
- **L — Liskov substitution.** Port implementations are interchangeable:
  `InlineJobRunner` and `TaskiqJobRunner` honour the same
  `submit/status/wait` contract — bot scenes cannot tell them apart.
- **I — interface segregation.** Ports are narrow: `DocumentParser`
  only does "bytes → text/rows", not "everything about documents".
- **D — dependency inversion.** Dependencies point from the domain to an
  abstraction: a module imports a core protocol; an adapter supplies the
  implementation. Checkable sign — `core` never imports modules;
  modules never import aiogram.

### DRY

Shared things live once, in the right layer:

- one document parser, HTTP clients, LLM gateway, job framework — core,
  not copies in modules;
- a duplicate in two modules is a signal to extract to core or a shared
  module;
- but DRY is not premature abstraction: two similar cases are not a
  reason for a base class (see YAGNI).

### KISS

The simplest solution covering the real need:

- a background job = a light JSON payload; heavy data goes to the stash;
  no "universal" state containers;
- a bot scene is a linear script (request → step → result), not a
  state machine for every contingency;
- schemas are flat pydantic models without inheritance for inheritance's
  sake.

### YAGNI

Do not build what is not needed today. Scaffolds are made exactly the
size of the future, not "for growth":

- `src/api/` — an empty entry-point layer so layers need no rewriting;
- the `ozon` HTTP profile — URLs are recognized, the parser raises
  `UnsupportedMarketplaceError`;
- Ozon tariffs in finance — tables are filled and the calculator knows
  the segments, but a full ozon report parser is not written until real
  exports exist.

Violation sign: "a class/abstraction for the next three cases" with one
real case.

## How this feels in practice

1. A task arrives → identify the owning module (often just one).
2. Feature code lives in the module + a thin bot adapter
   (texts/keyboards).
3. A shared piece is needed → first check whether it is core (the third
   constants rule, a port instead of a copy).
4. Choosing between solutions — pick the one that is easier to close
   and harder to abuse (KISS + YAGNI), leaving extension behind a port
   (SOLID).
