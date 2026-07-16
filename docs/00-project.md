# Explore_BPX — Project

This is the first document in the Explore_BPX specification: accepted product
principles, scope and non-goals. Everything that follows — architecture, UI,
features and roadmap — serves the intent described here.

Read the specification in order:

1. **00-project.md** — principles, scope (this document).
2. [01-architecture.md](01-architecture.md) — domain model, architecture, state, seams.
3. [02-ui.md](02-ui.md) — application-wide UI framework.
4. [03-features.md](03-features.md) — authoritative specification of every feature.
5. [04-roadmap.md](04-roadmap.md) — remaining implementation work and acceptance criteria.
6. [05-future.md](05-future.md) — speculative ideas not yet accepted as design.

## Workspace philosophy

The application edits a *Workspace* — one Primary document and optionally one
Reference document — rather than an isolated file. Whether one or two documents
are present is data, not an application mode, so comparison is a capability of
the one editor rather than a separate mode. Today a Workspace holds exactly one
document; multi-document support is an additive evolution, not a different
application.

## Accepted Product Principles

These principles are accepted product-level commitments. They constrain every
architectural, UI and feature decision in the documents that follow.

1. **Four core activities.** Explore_BPX exists to explore, edit, validate and
   author BPX documents. All four are first-class; none is an optional add-on.

2. **Editing is foundational; authoring is a priority.** Editing individual
   values is the base capability. Authoring — creating, completing and
   maintaining whole documents — is first-class, designed alongside editing
   rather than deferred.

3. **Completion is distinct from validation.** Validation answers whether BPX
   data satisfies BPX/schema rules; completion answers whether a document is
   finished for an authoring workflow. A work-in-progress document is not the
   same product state as an incorrect one — the two must not be conflated.

4. **Never invent scientific values.** Explore_BPX must never write fake or
   placeholder scientific values to make a document appear complete or valid;
   exported BPX represents only data the user is prepared to claim. This also
   covers user-authored custom parameters: the key and value are user-supplied,
   and the BPX validator — not Explore_BPX — is the source of truth for legality.

5. **The raw document is the source of truth.** The editable state is the raw
   BPX dictionary, so invalid and partially edited documents remain fully
   representable. Views and validation are derived from it.

6. **Validation ownership.** Explore_BPX owns presentation only; validation
   semantics, messages and meaning are owned entirely by the official BPX
   package and must be surfaced faithfully, without modification.

7. **The unit of work is a Workspace.** Components render the Workspace they are
   given; the number of documents is data, not an application mode. The current
   single-document application is the degenerate one-document Workspace, so
   multi-document support is additive, not a new architecture (see
   [01-architecture.md](01-architecture.md)).

## Scope

### In scope

Explore_BPX is a desktop BPX explorer, editor, validator and authoring
environment. Its accepted scope (implemented and planned) is: open JSON/YAML
files including invalid/incomplete ones; a derived object tree and per-object
parameter list; schema-metadata inspection (units, descriptions); continuous
validation of the raw working document; editing by parameter kind (scalar,
integer, enum, function, table); navigation via search and validation; save and
JSON/YAML export; authoring from model skeletons and templates with completion —
a stateless read of what the schema still expects, never a persisted status,
kept separate from validation; and visualisation of function/table parameters.

Precise per-capability status is in [03-features.md](03-features.md);
implementation order is in [04-roadmap.md](04-roadmap.md).

### Non-goals

- **Reimplementing BPX.** Schema, parsing and validation semantics stay with the
  `bpx` package.
- **Adding domain plausibility checks to the BPX gateway.** Plausibility or
  sanity validation against reference datasets is a separate concern from schema
  validation and must never contaminate the BPX integration layer.
- **Shipping disabled controls.** UI for workflows that do not yet exist is not
  displayed as greyed-out placeholders.
- **Speculative abstractions.** The architecture defines stable extension seams
  rather than building unused frameworks ahead of a concrete need.

Speculative ideas that are not yet accepted design live only in
[05-future.md](05-future.md) and must never be treated as implementation
requirements until promoted into this specification.
