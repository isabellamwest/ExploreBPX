# PLAN: Diagnostics page -- "One stream"

Approved design 2026-08-04 (Bella). Wireframes and the rejected alternatives:
(internal design archive)

This plan is speculative in the usual sense: the decisions below are settled,
the phase boundaries are not sacred. If the code says a decision is wrong, say
so and stop rather than working around it.

---

## 1. Why

Traced from real screenshots of the running app (`nmc_pouch_cell.json`, and
`invalid_blended_state_mismatch.json` with Cell selected):

1. **The same count appears four times** -- strip chip, rail badge, fold-header
   badge, pane header sentence.
2. **The rail bills a fixed 190px** to list sections that are, on a typical
   file, empty destinations. On `nmc_pouch_cell.json`, 8 of 10 are empty.
3. **Selecting a clean section is a dead end** -- two bordered boxes whose only
   content is "No issues" and "Nothing outstanding".
4. **Two renderers for one dataset** (`_AllSectionsView` and
   `_SectionDetailView`), which is why a reconciliation test exists to stop them
   drifting.
5. **The chips read as readouts, not filters.** Nothing about them says
   clickable, and a zero chip filters nothing.
6. **Content stops around 40% of page height** on every file.

The fix is not more chrome. It is to make the page's length track the amount of
work rather than the size of the schema.

## 2. What we are building

One scrolling column. No rail. Only sections that have something in them
render. Clean sections collapse into a single foldable line at the bottom. A
`Group by` control switches the stream between grouping by **Section** (default)
and grouping by **Type**.

```
+--------------------------------------------------------------------------+
| (o) 1 error   (o) 3 warnings   ( ) 6 outstanding      Group by [Section|Type] |
+--------------------------------------------------------------------------+
| Document   3 warnings                                        <- band       |
|   * The 'bpx' field now expects the BPX semantic version ...     Go to >   |
|   * The maximum voltage computed from the STO limits ...         Go to >   |
+--------------------------------------------------------------------------+
| State   1 error . 2 of 5 remaining                                         |
|   * Initial conditions -> Blended electrode State values ...     Go to >   |
|   o Initial temperature [K]  REQUIRED                            Go to >   |
|   ( Initial SoC . added, no value yet                            Go to >   |
+--------------------------------------------------------------------------+
| Separator   section absent                                                 |
|   o Separator  REQUIRED                                      + Add section |
+--------------------------------------------------------------------------+
| > . 7 sections clear                                                       |
+--------------------------------------------------------------------------+
```

Scope note: **this is a `ui_qt`-only change.** `core.page_buckets` is the
derivation point and stays untouched, as does `core.completion`, `state/`, and
`MainWindow`'s call signature. If an implementation step seems to need a new
field on `SectionBucket` or `PageBuckets`, stop and ask.

## 3. Decisions

**D1 -- The rail is deleted.** `_RailList`, `_RailDelegate`,
`_add_rail_entry_all`, `_add_rail_separator`, `_add_rail_entry_section`,
`_RAIL_*` roles, and `QListWidget#DiagnosticsRail` QSS all go. Navigation to a
section is not a thing users need on this page; the tree and the parameter list
already do that, and activating a row already navigates.

**D2 -- One renderer.** `_SectionDetailView`, `_GroupBox` (the local subclass,
not the shared `ui_qt.group_box.GroupBox`) and `_AllSectionsView` are replaced
by a single `_StreamView` built on one `QListWidget`, keeping today's
`_AllSectionsView` structure and its `_DiagnosticsRowDelegate`. The
Issues/Outstanding bordered boxes disappear entirely.

**D3 -- Clean sections do not render.** A bucket is *clear* when
`error_count == 0 and warning_count == 0 and outstanding_count == 0`, computed
from unfiltered `PageBuckets` data. Clear buckets are excluded from the stream
and named on one foldable footer line instead.

**D4 -- The clear line, expanded, keeps the positive completion signal.**
Collapsed: `7 sections clear`. Expanded, one quiet row per clear bucket:
  - present bucket with a known total: `Cell . 5 of 5 filled`
  - present bucket with `required_total` of `None` or 0: `Cell` alone
  - absent bucket: `Separator . section absent`, rendered italic + muted, the
    same treatment the rail used for an absent section.
  Rows on the clear line are **not** activatable. Nothing to go to.

**D5 -- Section headers carry words, not badges.** Header = bold bucket label,
plus a muted suffix built from whichever parts are nonzero, joined with " . ":
  - issue part: `1 error`, `3 warnings`, `1 error . 2 warnings`
  - outstanding part: the existing `_ratio_words(bucket)` verbatim
    (`2 of 5 remaining` / `section absent` / `N sections absent` / Document's
    `N remaining`).
  No count badges anywhere in the stream. The strip chips are the one summary;
  the row marks are the one per-item signal. This is what kills problem 1, so do
  not reintroduce badges "for scannability".

**D6 -- Group by: `Section` | `Type`.** Not "Severity": `Severity` is a real
core enum with exactly ERROR and WARNING in it, and Outstanding rows are
`CompletionTask`s, not diagnostics, so labelling that axis "Severity" would be
false in the app's own vocabulary. Group headers in Type mode use the same nouns
as the chips, so the control is self-explanatory:
  - `ERRORS`, `WARNINGS`, `OUTSTANDING`, each with its count in the suffix.
  - Group order is fixed: errors, warnings, outstanding. Within a group, rows
    keep `PageBuckets` order (document order). No new sorting logic.
  - Empty groups do not render.

**D7 -- In Type mode every row carries a section breadcrumb.** Section is no
longer the header, so it moves onto the row as a muted leading crumb: the bucket
label plus the existing relative location, e.g. `State -> Initial conditions`.
Factor one helper both modes use, so the two can never spell a location
differently:

```python
def _row_location(bucket, nav_path, *, include_section: bool) -> str: ...
```

In Section mode `include_section=False`, which is exactly today's
`_relative_location`.

**D8 -- Sections stay foldable; no sticky headers in v1.** Today's fold set and
click-to-fold behaviour carries over unchanged and is the answer to "a badly
broken file is a long scroll": collapse what you have dealt with. Sticky headers
are a real improvement but need a scroll-tracking overlay widget over the
viewport; defer until someone actually reports scroll pain. Fold headers remain
`Qt.ItemIsEnabled` (clickable, never selectable), so they are still not keyboard
reachable. That is a pre-existing gap, unchanged here, and out of scope.

**D9 -- A genuinely clean file gets a real answer, not an absence.** When
`error_count == warning_count == outstanding_count == 0`, the stream renders one
pinned, non-activatable all-clear row above the clear line:
  - `style.all_clear("No issues, nothing outstanding")`
  - second muted line: `10 of 10 sections complete and valid`
  The clear line still renders below it, expandable as usual. No circled tick or
  cross marks anywhere (standing rule); the existing plain check from
  `style.all_clear` is the whole treatment.

**D10 -- Filters stay chips, and a filtered-empty section renders no header.**
The three chips remain the only filter surface and keep their toggle semantics,
`chipOff` QSS property, and truthful unfiltered counts. Build each section's
visible rows first and emit the header only if at least one row survives; a
header over nothing is the same "chrome announcing absence" bug we are removing.
One `N hidden by filters` line at the very bottom of the stream, using the
existing `_hidden_by_filters_text`. Consequence to accept and state in a test:
a section whose content is entirely filtered out appears nowhere -- not in the
stream, and not on the clear line either, because clear is computed unfiltered.
The hidden line accounts for it.

**D11 -- View state.** `_selected_key` is gone. The panel keeps: the fold set,
the clear-line expanded flag, chip filter state, and the group-by mode.
`reset_view_state` (called only when a *different* document replaces the
session) resets folds, the clear-line flag and the chips, as today. It does
**not** reset group-by: that is a session preference rather than document state,
the same way a sort order is. Reversible if it feels wrong on the walk.

**D12 -- Full width, no measure cap.** Removing the rail widens message wrap by
about 17% over today's pane. Validator messages are one to two lines; a cap
would need a delegate change shared with the Inspector. Check it on the
on-screen walk instead of engineering for it now.

## 4. Copy (pinned)

| Where | String |
|---|---|
| Group by control | `Group by`, options `Section`, `Type` |
| Type-mode headers | `ERRORS`, `WARNINGS`, `OUTSTANDING` (count in suffix) |
| Clear line, collapsed | `{n} sections clear` (`1 section clear` when n == 1) |
| Clear row, filled | `{label} . {n} of {n} filled` |
| Clear row, absent | `{label} . section absent` |
| All clear, line 1 | `✓ No issues, nothing outstanding` (via `style.all_clear`) |
| All clear, line 2 | `{n} of {n} sections complete and valid` |
| Hidden line | unchanged: `{n} hidden by filters` |
| No document | unchanged: `No document open` |

`_MSG_NO_ISSUES`, `_MSG_NOTHING_OUTSTANDING` and `_MSG_PARTIAL_NO_TARGET` lose
their group boxes. Delete the first two. **Keep the Partial notice**: when
`model == "Partial"` and there is nothing outstanding anywhere, render it as one
muted, non-activatable row above the clear line, because a bucket alone cannot
distinguish "Partial, nothing is ever tracked" from "fully filled". That is the
one place `model` still reaches this module, and the reason is unchanged.

No em dashes in any UI string.

## 5. Phases

Run them in order; stop after each for review, and do not commit unless asked.

**Phase 1 -- Stream in Section mode.**
Replace both views with `_StreamView`; delete the rail and the group boxes;
implement D3, D4, D5, D8, D9, D10, plus the Partial notice. Group-by control not
built yet. Update QSS (drop `#DiagnosticsRail`, `#DiagnosticsGroupBox*`,
`#DiagnosticsPaneHeader`, `#DiagnosticsSectionScroll`; rename
`#DiagnosticsAllSectionsList` to `#DiagnosticsStreamList`). Update `AppDriver`
and the tests per section 6. `python -m pytest` green before handing back.

**Phase 2 -- Group by Type.**
Add the segmented control to the strip (D6), the Type-mode grouping, and the
shared `_row_location` breadcrumb (D7). Reconciliation test runs in both modes.

**Phase 3 -- Prove it.**
Headless `AppDriver` coverage for every state in section 7, then drive the real
app (`/run`) and screenshot: a mostly clean file, a file with errors and
outstanding work, a fully clean file, a Partial file, both group modes, chips
toggled. Compare against the wireframe and report divergences honestly rather
than declaring a match.

## 6. Test surface

Files that touch this panel today (rewrite, do not delete coverage):

`tests/ui_driver.py` (51 refs), `tests/test_validation_page_layout.py` (83),
`tests/test_diagnostics_filters.py` (56), `tests/test_outstanding_section.py`
(14), `tests/test_completion_display.py`, `tests/test_empty_state.py`,
`tests/test_issue_keyboard_navigation.py`, `tests/test_cell_issues.py`,
`tests/test_make_main.py`, `tests/test_completion.py`.

**Driver seams to delete:** every `diagnostics_rail_*`, `diagnostics_pane_mode`,
`diagnostics_section_header_text`, `diagnostics_section_issues_badge_texts`,
`diagnostics_section_outstanding_title`, `diagnostics_section_*_empty_text`,
`diagnostics_section_hidden_line_text`,
`diagnostics_all_sections_hidden_line_text`.

**Driver seams to add:**

```python
diagnostics_group_mode() -> str                 # "section" | "type"
diagnostics_set_group_mode(mode) -> AppDriver
diagnostics_stream_headers() -> list[str]       # header text incl. suffix, in order
diagnostics_stream_issue_texts() -> list[str]
diagnostics_stream_task_texts() -> list[str]
diagnostics_stream_subhead_texts() -> list[str] # OPTIONAL . K UNFILLED
diagnostics_clear_line_text() -> str | None
diagnostics_toggle_clear_line() -> AppDriver
diagnostics_clear_section_texts() -> list[str]  # expanded rows
diagnostics_all_clear_text() -> str | None
diagnostics_hidden_line_text() -> str | None    # replaces both old accessors
diagnostics_fold_section(label) -> AppDriver
```

Keep unchanged: `diagnostics_strip_counts`, `diagnostics_bucket`,
`diagnostics_chip_is_on`, `diagnostics_toggle_chip`, and the activation
emitters.

**The one test that must survive intact in spirit** is the reconciliation test.
Restate it over the stream, in both group modes: every diagnostic and every task
in `PageBuckets` is accounted for exactly once by
`rendered rows + hidden-by-filters count + clear-section rows`, and nothing
renders that `PageBuckets` does not contain. This is what makes D2 safe.

## 7. States to cover

| State | Expectation |
|---|---|
| No document | placeholder unchanged |
| Fully clean file | all-clear row + `10 sections clear` |
| One error in one section | one header, one row, `9 sections clear` |
| Absent required section | header `Separator . section absent`, row action `+ Add section` |
| Absent optional section, nothing outstanding | on the clear line, italic, `section absent` |
| Model is Partial, nothing outstanding | Partial notice row, no ratio anywhere |
| Model is Partial with NULL_FIELD tasks | tasks render normally, notice absent |
| DECLARE_MODEL only | header shows no ratio (`_is_declare_model_only`) |
| Optional tasks present | `OPTIONAL . K UNFILLED` subhead inside the section |
| Chip toggled off, section emptied | no header for that section, hidden line counts it |
| All chips off | no sections, hidden line only, clear line still true |
| Fold a section, then refresh (commit/undo) | fold survives |
| Open a different document | folds, clear line, chips reset; group mode persists |
| Type mode | three group headers max, breadcrumbs on every row |
| Type mode with zero errors | no ERRORS header |

## 8. Explicitly out of scope

Sticky headers (D8). Keyboard-reachable fold headers. Any change to
`core.page_buckets`, `core.completion`, or the activity-bar badge. Any change to
the Inspector's Issues section, which shares `ParameterRowDelegate` -- if a
delegate change looks necessary, stop and ask, because it lands in two places.
