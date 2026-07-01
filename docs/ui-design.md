# Explore_BPX UI Design

This document describes how users interact with Explore_BPX. It is the primary
reference for implementing the Qt frontend. Architectural boundaries and backend
module responsibilities live in [architecture.md](architecture.md); capability
status and planned work live in [roadmap.md](roadmap.md).

## UI Philosophy

Explore_BPX should feel like a focused professional desktop tool: familiar and
predictable. It should be closer to
an editor such as VS Code than to a wizard or dashboard. The interface keeps
context visible, avoids hidden modes, and lets users inspect, edit and validate a
BPX document without losing their place.

The central interaction principles are:

- BPX objects and parameters remain visible as a stable hierarchy.
- Search and validation navigate to document locations; they do not filter or
  replace the document structure.
- Validation guides the user without taking control away from them.
- Secondary information is available on demand without permanently occupying
  workspace.
- Editing works against the raw working document, so invalid work-in-progress
  data can be represented and corrected.

## Workspace Layout

The workspace uses a fixed multi-pane shell with familiar editor conventions:

```text
[top context / mode bar spans the main content area]
[activity bar] | Tree | Parameter list | Inspector | [Issues drawer]
[bottom status bar]
```

The editor uses a three-pane master-detail-detail layout:

- **Tree**: navigable BPX objects.
- **Parameter list**: direct parameters of the selected object.
- **Inspector**: the selected parameter's active workspace for viewing and editing.

The three panes remain visible while editing so sibling context is preserved. A
selected object does not replace the tree, and a selected parameter does not
replace the parameter list.

The **Issues drawer** is a collapsible right-edge drawer for validation issues.
It remains collapsed most of the time, visible as a thin strip that always shows
the current issue count, such as `Issues (0)` or `Issues (2)`.

## Activity Bar

The activity bar switches the full content area between top-level views. The
current views are:

- **Editor**: the main tree/list/inspector workspace.
- **Validation**: a full issue list for the active document.

The Validation icon shows a count badge when issues exist. The activity bar
is reserved for major workspaces that replace the main content area, such as
Editor, Validation, future Database and future Compare. It should show only
shipped views; disabled placeholders for future views should be avoided.
Parameter analysis, documentation, graphs, statistics and similar secondary
tools are not activity-bar views.

## Top Context / Mode Bar

The top bar communicates the current context or active workflow:

- In normal editing it shows the file name and current location.
- During validation review it becomes the review cursor: Previous, issue count,
  current path and Finish Review.

The top bar is a context/mode surface, not a duplicate clickable breadcrumb. The
always-visible tree and parameter list already provide structural navigation.

## Editor Layout

### Tree

The tree contains BPX objects only, never individual parameters. Selecting an
object updates the parameter list.

### Parameter List

The parameter list shows the direct parameters of the selected object. Selecting
a parameter updates the Inspector.

### Inspector

The Inspector is the selected parameter's work surface. In the current scope it
hosts **Edit** controls. Future parameter-centric workflows, such as Analysis,
Documentation and References, should be added as expandable/collapsible
Inspector sections over the same selected `ParameterItem`, rather than as
separate pages or major workspaces. The intended interaction is click Analysis
to expand its graph, then click Analysis again to collapse it.

## Navigation Model

All navigation is coordinated by the single `NavigationService` described in
[architecture.md](architecture.md). UI consumers such as Search and Validation
Review request navigation by target path; individual views react to navigation
notifications by revealing their part of the target.

Navigation should consistently:

- expand the tree to the destination object;
- select the object;
- select the parameter when the target is parameter-level;
- update the context bar;
- scroll the relevant destination into view;
- apply a temporary highlight to the destination.

No component should implement its own competing navigation behaviour.

## Search

Search is navigation, not filtering. It should not hide tree nodes or parameter
rows.

The search box lives in the toolbar and is focused by both `Ctrl+F` and
`Ctrl+P`. Focusing search selects the existing text so the user can immediately
replace it. Results are shown in a custom SearchPopup rather than a generic
`QCompleter`.

SearchPopup behaviour:

- indexes both navigable objects and parameters;
- displays each result as a name over its full path;
- scrolls after approximately eight visible results;
- supports Up/Down, Enter and Escape;
- Enter navigates to the highlighted result via `NavigationService`;
- Escape is staged: close popup, then clear search, then return focus to the
  editor.

The first implementation should remain deliberately simple: no ranking, icons,
recent searches or grouping until there is a concrete need.

## Editing Workflow

Editing is performed in per-kind cards in the Inspector. Cards are selected by
`ParameterKind`, not by individual parameter name.

The commit model is:

- **Enter commits** the current raw input to the working document, valid or
  invalid.
- Invalid data is not silently accepted by the validated BPX model; it is
  surfaced as validation issues after revalidation.
- Cards emit raw user input and do not gatekeep invalid values.
- A small inline Reset beside the input restores the last committed value.
- Escape reverts the uncommitted draft.
- Blur does not commit.
- Detached footer Apply/Reset buttons are not used.

This keeps controls close to the input and preserves the ability to work with
invalid BPX files.

## Validation Workflow

Validation is continuous. Issues are visible in two places:

- the **Validation view**, which lists all issues for the active document;
- the **Issues drawer**, which is the single home for full issue text for the
  current context.

Clicking an issue in the Validation view navigates to the affected object or
parameter and activates the non-modal review cursor. Object-level issues are also
shown in the Issues drawer rather than requiring a special banner elsewhere.

## Review Cursor

Validation review is non-modal. The review cursor appears in the top context /
mode bar, but the editor remains interactive. Users may edit, search, navigate
and inspect while review is active.

The cursor provides:

- Previous;
- current issue number and total;
- current issue path;
- Next;
- Finish Review.

When an edit resolves the current issue, the cursor stays on that issue and
shows a clear resolved state, such as a tick or "Issue resolved". It does not
auto-advance. The user explicitly chooses Next or Finish Review. If all issues
are resolved, the UI presents a clear Finish Review action rather than exiting
automatically.

Resolved state and counts track the committed document state after Enter, not
the live preview while typing.

## Issues Drawer

The Issues drawer is a collapsible right-side tool window for validation
context. It should behave like a collapsible IDE tool window, not a permanently
visible side panel.

The Issues drawer:

- contains all full issue text;
- handles both parameter-level and object-level issues;
- stays collapsed most of the time;
- remains visible as a thin strip when collapsed;
- always displays the current issue count, such as `Issues (0)` or `Issues (2)`;
- expands when clicked and collapses when clicked again;
- auto-opens when validation produces a new error or warning unless explicitly
  dismissed;
- updates live during preview validation;
- remains available during normal editing and validation review.

The Issues drawer should not become a dumping ground for secondary workflows.
In-depth parameter analysis belongs in the Inspector as an expandable section.

## Toolbar

The toolbar remains minimal:

- **Import**: a menu. Current scope exposes Open File only.
- **Save**: writes back to the current backing file and clears Modified.
- **Export**: writes a copy to a chosen path/format and does not change Modified.
- **Search**: global object/parameter navigation.

Unimplemented future actions should not appear as disabled buttons.

## Status Bar

The bottom status bar communicates document-level state such as source and
modified/saved status. This keeps persistent file state out of the top context
bar, whose role is location and mode.

## Interaction Rules

- Search and validation navigation must use `NavigationService`.
- Search navigates; it does not filter.
- Review guides; it does not lock the editor.
- Invalid edits may be committed to the raw working document.
- The Issues drawer is the single home for full issue text.
- Future analysis is an expandable Inspector section, not an activity-bar view
  or Issues drawer tenant.
- Future UI controls should appear when their workflows exist, not as disabled
  placeholders.

## Accessibility And Keyboard Behaviour

Keyboard behaviour should follow common desktop conventions:

- `Ctrl+F` and `Ctrl+P` focus search and select existing text.
- Search results support Up/Down and Enter.
- Escape closes transient UI before clearing state or returning focus.
- Enter commits the active editor card.
- Escape reverts the uncommitted editor-card draft.

As the UI matures, focus order and screen-reader naming should be checked for
the activity bar, SearchPopup, review cursor, Issues drawer and editor cards.

## Design Decisions

### DD-001 — Workspace Shell

- **Decision:** Fixed three-pane master-detail Editor (`Tree | Parameter list |
  Inspector`), a left activity bar, a top context/mode bar, a collapsible right
  Issues drawer, and a bottom status bar.
- **Reasoning:** Keeps object -> parameter -> editor context visible at once;
  matches familiar IDE conventions; each band has one clear job.
- **Alternatives considered:** A two-pane body-swap; a dockable inspector; a
  floating document-info card.
- **Advantages:** Sibling context preserved while editing; scalable activity-bar
  seam; secondary issue context available on demand.
- **Disadvantages:** Three columns pressure horizontal space; the top bar is
  location-only, not clickable navigation.
- **Future implications:** Activity bar absorbs future major workspaces; the
  Inspector can host future parameter-centric sections; multi-document fits as
  activity/tab additions.
- **Status:** Accepted.

### DD-002 — Non-Modal Validation Issue Cursor

- **Decision:** Validation review is a non-modal issue cursor pinned into the top
  context/mode bar; the editor stays fully interactive. The Validation list has
  no Previous/Next.
- **Reasoning:** The purpose of review is to fix issues, which means editing; a
  modal review would force users to leave it to edit.
- **Alternatives considered:** A true modal review; jump-only from the list with
  no cursor.
- **Advantages:** Fix-in-place; search/tree/edit stay available; matches
  Find-Next and spellcheck conventions.
- **Disadvantages:** Less forced focus, mitigated by the visually distinct bar.
- **Future implications:** Generalises to a remediation walker when `IssueKind`
  actions arrive.
- **Status:** Accepted.

### DD-003 — Activity-Bar View Switching

- **Decision:** A left activity bar switches the full content area between
  top-level views (currently Editor and Validation), replacing top tabs; the
  Validation icon shows a count badge; no disabled placeholders for unshipped
  views.
- **Reasoning:** Most future views are full-area pages; a vertical rail scales
  better than top tabs and gives validation state a badge home.
- **Alternatives considered:** Top tabs; VS Code-exact sidebar-only switching;
  menu-driven switching.
- **Advantages:** Scales cleanly; honest; clear badge.
- **Disadvantages:** Heavy chrome for two current views; needs an icon set.
- **Future implications:** Compare and database workspaces can be added without
  layout rework.
- **Status:** Accepted.

### DD-004 — SearchPopup

- **Decision:** Replace generic completion with a custom SearchPopup navigation
  component indexing parameters and navigable objects. It is focused by both
  `Ctrl+F` and `Ctrl+P`, supports keyboard navigation, and calls
  `NavigationService` for selection.
- **Reasoning:** Search has become navigation, not autocomplete; a flat-string
  completer fights the interaction design.
- **Alternatives considered:** Extend `QCompleter`; defer custom popup; index
  parameters only; use a single shortcut.
- **Advantages:** One owned navigation surface; objects reachable; no future
  rip-and-replace.
- **Disadvantages:** More current-scope work; mixed object/parameter results need
  a type marker.
- **Future implications:** Same popup can later host ranking, icons, recents,
  issue, compare and database results.
- **Status:** Accepted.

### DD-005 — Toolbar And File Actions

- **Decision:** Minimal fixed toolbar: Import, Save, Export and Search. Import
  currently exposes Open File only. Save writes back to the current file. Export
  writes a copy. Disabled future buttons are omitted.
- **Reasoning:** Save and Export are distinct operations; conflating them makes
  Modified/Saved meaningless.
- **Alternatives considered:** Save equals Export; disabled future buttons;
  Export-only.
- **Advantages:** Honest controls; meaningful status; Import is the future-source
  hub seam.
- **Disadvantages:** Requires backing-file and dirty state in `DocumentSession`.
- **Future implications:** Import can absorb templates, databases and recent
  files; Export can generalise to simulator hand-off.
- **Status:** Accepted.

### DD-006 — Issues Drawer And Inspector-Hosted Analysis

- **Decision:** A right Issues drawer hosts full issue text in the current scope.
  Editing cards carry no issue text. Analysis is not a drawer tenant or a
  pre-built registry; it is added later as an expandable Inspector section over
  the selected `ParameterItem`.
- **Reasoning:** Editing and analysis are distinct; a thin rail cannot host deep
  analysis; defining an analyzer registry before analyzers exist is premature.
- **Alternatives considered:** Floating pop-ups; analysis inside editing cards;
  a parallel analyzer registry now; full issues inline on cards.
- **Advantages:** One issue surface; uncluttered cards; live feedback retained
  through drawer auto-open; future analysis gets full inspector width.
- **Disadvantages:** Drawer auto-open behaviour must avoid distraction.
- **Future implications:** A maximize option can later give analysis more width.
- **Status:** Accepted.

### DD-007 — DocumentSession / AppState Split

- **Decision:** Split state into `DocumentSession` (document, selection, undo,
  dirty/backing-file) and `AppState` (single active session plus app-global view
  state). No document collection or switcher UI yet.
- **Reasoning:** Undo, selection and dirty state are per-document; one `active`
  indirection makes future multi-document additive.
- **Alternatives considered:** Keep singular `AppState`; introduce a full session
  collection immediately.
- **Advantages:** Correct ownership; non-breaking multi-document later; no
  premature collection.
- **Disadvantages:** Requires call-site updates.
- **Future implications:** Multi-document adds sessions and a selector while
  preserving `state.active.*`.
- **Status:** Accepted.

### DD-008 — Editing Commit Model

- **Decision:** Enter commits raw input to the raw editing state, valid or
  invalid. Cards always emit raw input and never gatekeep. Inline Reset restores
  the last committed value; Escape reverts the draft; blur does not commit.
- **Reasoning:** Detached buttons were far from input, and blocking invalid
  commits contradicted support for invalid BPX files.
- **Alternatives considered:** Footer Apply/Reset; block invalid commits; commit
  live per keystroke; commit on blur.
- **Advantages:** Co-located controls; invalid edits allowed; fewer widgets;
  integrates with Issues auto-open.
- **Disadvantages:** Enter-to-commit is implicit.
- **Future implications:** The same emit-raw contract serves function/table cards
  and remediation auto-fixes.
- **Status:** Accepted.

### DD-009 — Navigation Ownership

- **Decision:** One `NavigationService` owns all navigation. It coordinates and
  notifies rather than driving widgets: resolve target path, update
  `state.active`, emit target identity. Subscribing views own their reveal.
- **Reasoning:** A single owner prevents duplicated navigation while avoiding a
  service coupled to concrete widgets.
- **Alternatives considered:** Each consumer implements navigation; one service
  imperatively drives every widget.
- **Advantages:** DRY navigation; testable; boundary tests stay green; panels are
  plug-in subscribers.
- **Disadvantages:** Requires a small notification contract.
- **Future implications:** Compare, Inspector documentation links, Inspector
  analysis sections and database references can navigate without new navigation
  logic.
- **Status:** Accepted.

### DD-010 — Issue Resolution During Review

- **Decision:** When an edit resolves the issue under the review cursor, the
  cursor stays put, shows resolved state and decrements the count. The user
  chooses Next or Finish Review. Newly introduced issues join the set but do not
  steal the cursor. Resolved state tracks committed document state.
- **Reasoning:** Auto-advance fights the non-modal, user-controlled model and can
  reshuffle indices while editing.
- **Alternatives considered:** Auto-advance to the next issue.
- **Advantages:** Predictable; preserves context; confirms changes applied.
- **Disadvantages:** Slightly slower for bulk triage than auto-advance.
- **Future implications:** Same cursor can become the remediation walker.
- **Status:** Accepted.

### DD-011 — Secondary Workspace Surfaces

- **Decision:** The Activity Bar is reserved for major application workspaces
  that replace the main content area, such as Editor, Validation, future
  Database and future Compare. Parameter analysis, documentation, graphs,
  statistics and similar tools are secondary surfaces, not Activity Bar views.
  The Inspector remains the primary parameter work surface: Edit, Analysis,
  Documentation and References appear as expandable/collapsible sections over
  the selected `ParameterItem`. Issues use a collapsible right-edge drawer that
  remains visible as a thin strip with the current count, opens and closes on
  click, auto-opens for new validation issues unless explicitly dismissed, and
  remains available during validation review.
- **Reasoning:** Secondary information should be available on demand without
  permanently occupying workspace. This keeps editing primary while making rich
  analysis and validation detail reachable when needed.
- **Alternatives considered:** Activity Bar entries for every feature; separate
  Edit and Analysis Inspector pages; a permanently visible auxiliary side panel.
- **Advantages:** Prevents activity-bar sprawl; preserves horizontal editing
  space; keeps parameter-centric tools close to the selected parameter; keeps
  validation issues continuously reachable.
- **Disadvantages:** Expand/collapse state and auto-open dismissal need clear
  ownership in the UI shell.
- **Future implications:** Parameter-centric features compose inside the
  Inspector; major future workspaces must justify replacing the main content
  area; the former general-purpose auxiliary panel concept should not return.
- **Status:** Accepted.
