# Explore_BPX — Project

This is the first document in the Explore_BPX specification. It establishes the
vision, philosophy, accepted product principles, scope and non-goals. Everything
that follows — architecture, UI, features and roadmap — serves the intent
described here.

Read the specification in order:

1. **00-project.md** — vision, philosophy, principles, scope (this document).
2. [01-architecture.md](01-architecture.md) — domain model, architecture, state, seams.
3. [02-ui.md](02-ui.md) — application-wide UI framework.
4. [03-features.md](03-features.md) — authoritative specification of every feature.
5. [04-roadmap.md](04-roadmap.md) — remaining implementation work and acceptance criteria.
6. [05-future.md](05-future.md) — speculative ideas not yet accepted as design.

## Vision

Explore_BPX is a human interface to the BPX (Battery Parameter eXchange) format.

BPX files are machine-readable but hard to work with by hand: they grow large,
express model-specific structure, and mix scalars, enumerations, function
expressions and interpolated tables. Explore_BPX makes these files easy to
**explore, edit, validate and author** through a focused desktop application,
without asking the user to read or hand-edit raw JSON or YAML.

The long-term vision is a standalone, dashboard-like application at the centre of
the BPX ecosystem: connecting parameter sources to simulators, supporting
create/edit/visualise workflows, and validating beyond syntax. Version 1 is the
PySide6 desktop foundation on which later capabilities build without restarting
the application architecture.

Explore_BPX does not reimplement BPX. Parsing, schema definitions and validation
are delegated entirely to the official `bpx` package. The product question is
**how people interact with BPX files**, not how BPX itself is defined.

## Philosophy

Explore_BPX should feel like a focused professional desktop tool: familiar,
predictable and closer to a code editor than to a wizard or a dashboard. The
guiding beliefs are:

- **Meet the real document, not an idealised one.** Users open files that are
  incomplete, invalid or work-in-progress. The tool must represent and repair
  those files, not refuse them.
- **Structure stays visible.** BPX objects and parameters remain a stable
  hierarchy. Search and validation navigate to locations; they never filter or
  replace the structure.
- **Guide without taking control.** Validation and, later, completion inform the
  user without locking the editor or forcing a workflow.
- **Honesty over convenience.** The tool never invents scientific values to make
  a document look finished or valid. Nothing is fabricated for a user-authored
  custom parameter either: the key and value are user-supplied, and the BPX
  validator — not Explore_BPX — is the source of truth for whether it is legal.
- **Delegate what BPX owns.** Schema and validation semantics belong to the
  `bpx` package and are not duplicated.
- **Open documents, not modes.** The application edits a *Workspace* — one
  Primary document and optionally one Reference document — rather than an
  isolated file. Whether one or two documents are present is data, not an
  application mode, so comparison is a capability of the one editor rather than a
  separate mode. Today a Workspace holds exactly one document; multi-document
  support is an additive evolution, not a different application.

## Accepted Product Principles

These principles are accepted product-level commitments. They constrain every
architectural, UI and feature decision in the documents that follow.

1. **Four core activities.** Explore_BPX exists to explore, edit, validate and
   author BPX documents. All four are first-class; none is an optional add-on.

2. **Editing is foundational; authoring is a priority.** Editing individual
   values is the base capability. Authoring — creating, completing and
   maintaining whole documents — is a first-class workflow and a major
   implementation priority, designed alongside editing rather than deferred to a
   distant future.

3. **Completion is distinct from validation.** Validation answers whether BPX
   data satisfies BPX/schema rules. Completion answers whether a document is
   finished for an authoring workflow. A work-in-progress document is not the
   same product state as an incorrect one, and the two must not be conflated.

4. **Never invent scientific values.** Explore_BPX must never write fake or
   placeholder scientific values into a document merely to satisfy the editor or
   to make a document appear complete or valid. Exported BPX represents only the
   data the user is prepared to claim.

5. **The raw document is the source of truth.** The editable state is the raw BPX
   dictionary, so invalid and partially edited documents remain fully
   representable. Views and validation are derived from it.

6. **Validation ownership.** Explore_BPX owns presentation only. Validation semantics, messages, and meaning are owned entirely by the official BPX package. Explore_BPX must faithfully surface validator output without modification.

7. **The unit of work is a Workspace.** Explore_BPX edits a Workspace — one
   Primary document and optionally one Reference document — not an isolated file.
   Components render the Workspace they are given; the number of documents is
   data, not an application mode, and comparison is therefore a capability of the
   editor rather than a separate compare mode. The current single-document
   application is the degenerate one-document Workspace, so multi-document
   support is additive rather than a new architecture. This is an accepted
   direction; the current implementation remains single-document (see
   [01-architecture.md](01-architecture.md)).

## Scope

### In scope

Explore_BPX is a desktop BPX explorer, editor, validator and authoring
environment. Its accepted scope — spanning implemented and planned work — is:

- open JSON/YAML BPX files, including invalid and incomplete files;
- present a derived object tree and per-object parameter list;
- inspect parameters with schema metadata such as units and descriptions;
- validate the raw working document continuously;
- edit parameters by kind (scalar, integer, enum, function, table);
- navigate to any object or parameter through search and validation;
- save to the current file and export copies in JSON or YAML;
- author documents from model skeletons and templates, with completion state
  tracked separately from validation;
- visualise function and table parameters within the parameter workspace.

The precise implemented/planned status of each capability is defined in
[03-features.md](03-features.md); the implementation order is defined in
[04-roadmap.md](04-roadmap.md).

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
