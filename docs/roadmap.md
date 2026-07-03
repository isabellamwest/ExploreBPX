# Roadmap

This roadmap is organised by capability rather than release number. It describes
what Explore_BPX can do now, what is in the current implementation scope, and
what is planned for later. Architectural rationale lives in
[architecture.md](architecture.md); detailed interaction behaviour lives in
[ui-design.md](ui-design.md).

## Capability Status Summary

| Capability | Status |
|---|---|
| Open JSON/YAML BPX files, including invalid files | Current |
| Derived BPX object tree and parameter list | Current |
| Continuous BPX validation | Current |
| Export / round-trip JSON or YAML | Current |
| Scalar, integer and enum editing | Current |
| Activity-bar shell and Issues drawer | Current |
| SearchPopup navigation | Current scope |
| Save vs Export split and dirty tracking | Current |
| DocumentSession / AppState split | Current |
| Authoring lifecycle: skeletons, templates and completion state | Planned |
| Function/table editing | Planned |
| Inspector analysis / visualisation section | Planned |
| Actionable validation and remediation | Planned |
| Raw JSON view | Planned |
| External database import | Future |
| Simulator hand-off | Future |
| File comparison | Future |
| Multi-document workspace UI | Future |
| Plausibility / sanity validation | Future |

## Current Scope

Current scope is the useful desktop foundation: a Qt BPX explorer/editor that can
open, navigate, validate, edit simple values and export BPX files while keeping
strict architectural boundaries.

Included in current scope:

- open JSON/YAML BPX files, including invalid files;
- show a derived BPX object tree and per-object parameter list;
- inspect parameters with schema metadata such as units and descriptions;
- continuously validate the raw working document;
- edit scalar, integer and enum parameters;
- commit raw editing input, including invalid work-in-progress values;
- save back to the current file and export copies;
- maintain dirty/backing-file state;
- route navigation through a single NavigationService;
- keep `core/` and `state/` frontend-agnostic.

Out of current scope:

- full function/table editors;
- in-depth analysis and plotting;
- authoring completion workflows;
- raw JSON editing;
- external database import;
- simulator hand-off;
- comparison;
- multi-document workspace UI;
- plausibility validation based on reference datasets.

## Workspace And Navigation

### Current

- Derived object tree built from the raw BPX data.
- Parameter list for the selected object.
- Two-tier selection: object path and optional parameter path.
- Activity-bar shell with Editor and Validation workspace views.
- Collapsible right-edge Issues drawer; auto-opens on first error; thin handle always shows the current issue count.
- Bottom status bar showing file name and save state.

### Current Scope

- Top context/mode bar showing current location.
- SearchPopup for object and parameter navigation.
- `NavigationService` as the single navigation coordinator.

### Future

- Multi-document workspace UI over multiple `DocumentSession` objects.
- Comparison navigation between documents.
- Documentation links, Inspector analysis sections and database references using
  the same navigation service.

## Editing

### Current

- Per-kind editing architecture for scalar, integer and enum values.
- Command foundation for document operations:
  `core/commands.py`, `core/command_service.py`, `core/structure.py` and
  `core/document_factory.py`.
- Raw-dict editing primitives in `core/editing.py`.
- State-level undo support.
- Dirty/backing-file tracking.
- Save writes back to the current file; Export writes a copy.
- Enter-to-commit editing workflow with per-kind cards.
- Escape reverts the uncommitted draft.

### Current Scope

### Planned

- Function expression editor.
- Editable table grid.
- Section add/remove controls.
- Unknown/raw fallback editor.
- Compact quick inputs in parameter lists where they genuinely improve repeated
  editing.
- Model-switch handling for structural model changes.

## Authoring

Authoring covers the lifecycle of creating, completing, validating and
maintaining BPX documents. It is broader than editing individual values: it owns
the distinction between Complete BPX, Incomplete BPX, Skeletons and Templates,
and keeps completion state separate from validation state.

### Current

- Raw-dict document model supports invalid and partially edited BPX files.
- `document_factory.py` can create incomplete structural scaffolds without
  inventing scientific values.
- Continuous validation supports work-in-progress editing without requiring the
  document to be valid before it can be explored.

### Planned

- New BPX from built-in model skeletons for SPM, SPMe, DFN and Partial.
- Completion status distinct from validation status.
- Completion view for unfinished required authoring work.
- Expected-but-missing parameter rows in the editing workflow.
- Upload/open skeleton workflows.
- Save as Template and New from Template workflows.

### Future

- Organisation-, lab-, chemistry- or workflow-specific templates.
- Parameter authoring states beyond present/missing values.
- Provenance and confidence tracking.
- Review/confirmation workflows for template-derived values.
- Reusable parameter packs.

## Validation

### Current

- BPX schema validation delegated to the official `bpx` package.
- Normalised `ValidationIssue` records with path, message and severity.
- Best-effort mapping from validation paths to visible objects/parameters.
- Validation workspace in the activity bar listing all document issues.
- Issues drawer surfaces all issues in context; collapses to a thin handle when not needed.

### Current Scope

- Non-modal review cursor for stepping through issues in context.
- Resolved issue behaviour: stay in place, show resolved state, explicit Next or
  Finish Review.

### Planned

- `IssueKind` classification for actionable remediation.
- Pure remediation functions for operations such as edit value, move misplaced
  value, choose model, map materials and add missing section.
- Restore usable field paths for warnings that currently land at the document
  root.
- Optional warning hide/ignore workflow for intentional modelling decisions.

### Future

- Plausibility / sanity validation against known or typical cell parameter
  ranges, implemented as a separate validation layer with its own reference
  dataset.

## Search

### Current Scope

- SearchPopup replacing generic autocomplete.
- Object and parameter results.
- Keyboard navigation with `Ctrl+F`, `Ctrl+P`, Up/Down, Enter and staged Escape.
- All result activation flows through `NavigationService`.

### Future

- Ranking.
- Icons or type markers.
- Recent searches.
- Searching validation issues, comparison results or database references through
  the same navigation surface.

## Analysis And Visualisation

### Planned

- Analysis as an expandable Inspector section for the selected parameter.
- Function and interpolated-table visualisation, such as OCP plots, using BPX
  functions exposed through `bpx_gateway.py`.

### Future

- Parameter-centric plausibility displays using reference datasets.
- Optional maximised Inspector section if plots need more space.
- Comparison overlays for related files or known cells.

## Data Sources And Import

### Current Scope

- Import menu with Open File.

### Planned

- Recent documents.

### Future

- LIIONDB import.
- Other BPX database sources.
- Additional source adapters implemented as anti-corruption layers that return
  raw BPX dictionaries.

## Export And Simulator Integration

### Current

- Export / round-trip JSON or YAML from the raw working document.

### Current Scope

- Distinct Save and Export semantics.

### Future

- Simulator hand-off targets such as PyBOP and PyProBE.
- Target-specific writers behind the export layer.
- Simulator compatibility checks where appropriate.

## Workspace And Multi-Document Support

### Current Scope

- `DocumentSession` separates per-document state from app-global state.
- `AppState.active` gives the UI a stable active-document access pattern.

### Future

- Multiple open document sessions.
- Workspace/library management.
- Comparison between documents.
- Active-document switcher UI.

## Non-Goals

- Reimplementing BPX schema or validation semantics already owned by `bpx`.
- Adding plausibility/domain validation to the core BPX gateway.
- Shipping disabled controls for workflows that do not exist yet.
- Building speculative analysis registries before concrete analysis widgets are
  implemented.
