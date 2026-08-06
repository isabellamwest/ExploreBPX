# PLAN — transparency and wording

## Status (2026-08-06)

Design agreed rev 3 (Isabella). Wireframes and the
full reasoning: (internal design archive)

**Implemented 2026-08-06, at Bella's instruction, ahead of the phase order:** the
D7/D8/D9 wording — "Not validated" → *Not checked* (Inspector), "N outstanding" →
*N incomplete* (diagnostics chip/tooltips, workspace badge, all-clear line),
"State: Modified" → *Status: Unsaved changes / Saved* (workspace record + status
bar), "Pull" → *Use this value* (ledger button/tooltip), undo entries now
`Use "<key>" from <source>`, Source-page echo tag "Pulled" → "Used", its toast now
names the source file. Also fixed en route: the ledger button's QSS pointed at a
dead `#CopyUpButton` selector, so the button rendered unstyled — renamed to
`#PullButton`. Suite 1694 green after the sweep. Command names (`PullParameter`/
`PullSection`) and internal identifiers keep their code vocabulary, per D1/D9.
The structural phases below (1–5) remain unstarted.

One item wants a confirming word before Phase 5 starts: Bella's instruction for legacy
files was "do the most conventional thing". Convention is an **upgrade prompt**, not the
read-only mode proposed in rev 2, because Word-style compatibility mode needs the ability
to work natively in the old format and the installed `bpx` has only the v1.x schema. D3
below records the prompt; if Bella prefers read-only after all, only D3 changes.

Phase 1 is **complete** (2026-08-06, outcome recorded under the phase below); the
wording glossary (D7/D8/D9) is implemented and the H2 badge violation it uncovered is
fixed. Next action: **Phase 3**, `LoadRecord` in `core` — Phases 4 and 5 still need
their wireframe passes before any UI is built.

## Governing principle — the honesty charter

Six rules, written so each can fail a test rather than lose an argument. Every decision
below is downstream of them.

- **H1 · Every number on screen is a number in a file.** No rounding, reformatting, or
derived statistics presented as data. Already true where it matters and worth protecting:
values render through `json.dumps`, `core/spread.py` labels the real extremes rather than
its padded axis, chart curves stop at their own domain edge.
- **H2 · The app never claims a check it did not run.** Absence of an error means *not
checked* whenever `validation_completed` is False. `inspector.py` already refuses to say
"Valid" in that case; every other validity surface uses the same ladder.
- **H3 · What you see is what will be written.** If saving changes anything the user did
not change, the app says so beforehand. Formatting, comments, key order and float spelling
all count as the file.
- **H4 · What the app is reading is what the user opened.** The editor and the validator
look at the same document, or the app stops rather than annotating one document with
another's findings.
- **H5 · Every value has a stated origin.** Typed here, pulled from a named reference, or
synthesised by a converter. The third currently has no name on screen.
- **H6 · Refuse before you fudge.** A blocked action with a clear reason beats a completed
action with a quiet compromise. A refusal always names what is wrong and what unblocks it.

## Findings — verified in the code, 2026-08-06

1. **Legacy conversion is invisible and the tree disagrees with the diagnostics** (H4, H5).
`bpx` converts a v0.x object before judging it and warns that the conversion is
"approximate": State synthesised, initial SOC set to 1, lumped thermal conductivity
dropped, optional v1 fields omitted so downstream tools apply their own defaults,
"cross-version semantic changes are not corrected" (`bpx/parsers.py:12-23`). We capture the
warning (`core/validation.py:110`) but a `PythonWarningDiagnostic` carries no loc, so it
lands as one anonymous amber line. Our raw dict is never converted, so the tree renders
v0.x while every diagnostic refers to v1.x paths — a likely source of the orphan
diagnostics the nearest-ancestor rule currently absorbs.
2. **Save rewrites the whole file** (H3). `core/export.py:15-20` goes through
`json.dumps(indent=2)` / `yaml.safe_dump`. YAML comments are destroyed and anchors
resolved; JSON whitespace is normalised. Never stated anywhere.
3. **The main document is never checked against disk** (H3, H6). Only
`state/reference_snapshot.py` captures an `mtime`. A read-only reference shows a stale
band; the file being edited has no such check, so Save silently overwrites a newer version.
4. **"Checked this far" is modelled but never said** (H2). `bpx_gateway.py:99-106` documents
the staged abort and `inspector.py` honours it per parameter. No surface states it at
document level, so an empty diagnostics list reads as clean when it can mean unexamined.
5. **Format is decided twice** (H3). `bpx_gateway.py:130` picks the parser by extension;
`document_session.py:332` independently re-derives it the same way, discarding the format
the loader recorded.
6. **The main document's record is thinner than a reference's** (H5). A reference expands to
Origin, Validity, Model, Contents, Citation or path; the main card shows Model, BPX version,
File, State, Contents. `core/document.py:95-97` reads three of the Header's five fields —
`Description` and `References` never reach a surface where a person asks what a file is.
7. **`State: Modified` collides with the BPX `State` section** (`bpx/schema.py:721`).

## Decisions

- **D1 · "Reference" wording is kept.** No rename, in code or on screen (Bella, 2026-08-06).
The three meanings are separated by context and by never abbreviating: *pinned reference*,
*reference library*, and the spec's `Header.References` shown as **Citation**, which is
already what the Workspace calls it for library sets.
- **D2 · Load facts live in two places, both permanent.** A **Read as** and a **Checked**
row in the file record, and a pinned **This file** group at the top of the diagnostics
stream that no filter chip can hide. No dismissible banner: dismissal promises the fact
stopped mattering.
- **D3 · Legacy files are offered a converted copy at open.** Dialog states the version, the
named consequences, and that the original is untouched. Buttons: *Open converted copy*
(primary, opens as a new unsaved document), *Open as-is, read-only*, *Cancel*. A legacy file
pinned as a **reference** needs no conversion at all — references are already read-only, so
its values are shown and its validity reads *Not checked · BPX 0.4 cannot be checked
against 1.1*.
- **D4 · YAML comments: warn, do not refuse.** Stated permanently in the file record when
the opened file contains comments, and confirmed once before that document's first save.
No "don't ask again" checkbox — a control that hides a destructive fact is what this charter
exists to prevent. A round-trip writer (`ruamel.yaml`) is a separate future track, not part
of this one.
- **D5 · Disk facts are shown**: size and modified time, in the file record. Needed for the
stale check regardless.
- **D6 · The record is editable exactly where the document is.** Title, Description and
Citation are editable in the main document's record and read-only in a reference's. Not a
second editor: the same `SetValue` command, so undo is identical wherever the user typed.
Every other row is a fact about the file and is editable nowhere.
- **D7 · One validity ladder everywhere**: *Valid* · *N errors, N warnings* · *Not checked* ·
*Incomplete*. "Outstanding" becomes **Incomplete** — the only chip whose noun never said
what it counted.
- **D8 · One saved-state word pair**: *Unsaved changes* / *Saved*. Never "State", never
"Modified", never "Dirty". No BPX section name is ever borrowed for an app concept.
- **D9 · "Pull" becomes "Use this value"**, undo reading `Use "Thickness [m]" from Chen2020`.
Wording only; the `PullParameter`/`PullSection` command names are unaffected, so D1 stands.

## Design rules per surface

1. **File record (Workspace)** — one shape used by the main document and every reference,
with no row a reference has and the main lacks: Title · Description · Citation · Model ·
Read as · Checked · Contents · From (path, size, modified) · Saved to / Unsaved changes.
*Read as* and *Checked* expand to the detail. Main document: Title/Description/Citation
editable in place. Reference: identical rows, read-only.
2. **Diagnostics stream** — a **This file** group above the parameter rows, exempt from the
filter chips, one line per structural fact (converted from BPX 0.4 · checking stopped at
Header · comments will not survive saving). Never dismissible.
3. **Legacy open prompt** — per D3. Consequences listed before the click, including the
reassurance that the original file is not modified.
4. **Stale-on-disk Save block** — per H6. Names the file and the time it changed; offers
*Reload*, *Save as copy*, *Overwrite*, each spelled out. *Save as copy* must be one of the
buttons, not a menu found afterwards: this is the moment a user most likely has unsaved work.
5. **Refusal sentence shape, everywhere** — what is blocked, why, and the action that
unblocks it. "Cannot save: lgm50.json changed on disk at 14:22. Reload, save as a copy, or
overwrite."
6. **Control and echo share a verb.** "Pin as reference" then "Pinned Chen2020", never
"added".

## Phases

Each phase ends with `python -m pytest` headless from the repo root and an honest report
(`matplotlib` absent from `.venv`; two `PyparsingDeprecationWarning`s expected).
`test_boundaries.py` and `test_typography.py` after every phase.

### Phase 1 — inventory and verification, no code changes
- Every user-facing string in `app/ui_qt/` collected into one list grouped by surface, so
the wording sweep is complete rather than anecdotal.
- Verify the three claims made from reading rather than running: whether the tree dot shows
an unchecked section as clean; whether any surface says "Valid" without consulting
`validation_completed`; and what a real v0.x file does end to end.
- Report honestly, including anything that contradicts the findings above.

**Outcome (2026-08-06, run empirically against the real app):**
1. *"Valid" without consulting `validation_completed`* — **confirmed and fixed**
(fd6b70f). The workspace badge read counts from `PartitionedIssues`, where an
abort's absence-shaped errors are absorbed into the incomplete count; deleting one
required field produced "Valid · 1 incomplete" over a `State` bpx never judged.
Worse than the plan feared: **every fresh SPM/SPMe/DFN skeleton is an aborted run**
("passes the schema with three parameters" in the badge's old docstring was false —
bpx aborts at Parameterisation), so New documents wore green "Valid" from birth.
The badge now says *Not checked · N incomplete* (muted dot) whenever
`validation_completed` is False. Reference rows are H2-safe by accident — they count
raw `document.error_count`, which an abort always leaves ≥ 1 — but still name no
"checking stopped" fact; that stays with Phase 4's Checked row.
2. *Tree dot on an unchecked section* — **confirmed**: an aborted run's unjudged
sections carry no mark and read exactly like clean ones. No quick fix exists inside
the dot language (absence of a mark is the dot language's "clean"); the honest
document-level statement is Phase 4's pinned "checking stopped at X" stream line.
3. *v0.x end to end* — **confirmed as finding 1**: the tree renders the raw v0.x
structure (no `State`), `bpx` validates its own converted copy
(`validation_completed` True, `is_valid` True), and the only trace is one anonymous
amber warning with no loc. Handled by D3/Phase 5, no interim change.
- Also closed en route: finding 5 (format decided twice) — one
`format_for_filename` rule in the gateway, used by loader and save (e706192).

### Phase 2 — charter and glossary signed
The gate. Nothing after it starts until the words are fixed.

### Phase 3 — `LoadRecord` in `core`
A frontend-agnostic value object carrying the format actually used, legacy detection, how
far checking reached, whether the source text contains YAML comments, and the disk facts.
Unit tested, no UI. Closes finding 5: the format decision is made once and carried.
Legacy detection routes through `core/bpx_gateway.py` to `bpx._migrations.is_legacy_bpx` /
`convert_v0_to_v1` — a private module, pinned by a test in the same style as
`_MODEL_MISMATCH_MARKER` so a `bpx` upgrade fails loudly. Never a hand-rolled version check.

### Phase 4 — the record and the stream group on screen
Design rules 1 and 2. `DocumentIdentity` gains `description` and `references`. Card
discipline applies to the editable rows: populate before connecting change signals, clear
`_touched` after `reset()`, or a bare Enter commits something nobody typed.

### Phase 5 — the three interventions
Legacy open prompt, stale-on-disk Save block, YAML comment confirmation. All three stand
between a person and their work, so each gets its own wireframe pass and its exact words
agreed before it is built.

### Phase 6 — the wording sweep
Mechanical, against the signed glossary, once nothing else is in flight.

## Process
- Commit per phase, only when asked. Never push.
- On-screen proof after each UI phase, driving the real app, compared against the rev 3
wireframes. Report divergences rather than declaring a match.
