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
| Scalar, integer and enum editing | Current scope |
| Activity-bar shell and Issues drawer | Current scope |
| SearchPopup navigation | Current scope |
| Save vs Export split and dirty tracking | Current scope |
| DocumentSession / AppState split | Current scope |
| Function/table editing | Planned |
| Inspector analysis / visualisation section | Planned |
| Actionable validation and remediation | Planned |
| Create-from-template workflows | Planned |
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

### Current Scope

- Activity-bar shell with Editor and Validation views.
- Top context/mode bar and bottom status bar.
- Collapsible right Issues drawer.
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

### Current Scope

- Enter-to-commit editing workflow.
- Inline reset and draft revert behaviour.
- Dirty/backing-file tracking.
- Save writes back to the current file; Export writes a copy.

### Planned

- Function expression editor.
- Editable table grid.
- Section add/remove controls.
- Unknown/raw fallback editor.
- Compact quick inputs in parameter lists where they genuinely improve repeated
  editing.
- Model-switch handling for structural model changes.

## Validation

### Current

- BPX schema validation delegated to the official `bpx` package.
- Normalised `ValidationIssue` records with path, message and severity.
- Best-effort mapping from validation paths to visible objects/parameters.

### Current Scope

- Issues drawer as the single full-text issue surface.
- Activity-bar Validation view listing document issues.
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

- New BPX files from incomplete templates/scaffolds for SPM, SPMe, DFN and
  Partial models.
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

## Creation And Templates

### Current

- `document_factory.py` can create incomplete structural scaffolds without
  inventing scientific values.

### Planned

- UI workflows for creating BPX files from templates.
- Model-aware scaffolding for required sections.

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
