# PLAN — transparency and wording

## Status

Phases 1–3 are done. The wording glossary (D7/D8/D9) is already swept through
the app, and `LoadRecord` carries the load facts the remaining phases display.

**Next: Phase 4**, starting with its wireframe pass. Phases 4 and 5 both need
one before any UI is built.

One question is still open, and Phase 5 cannot start without it. Bella's
instruction for legacy files was "do the most conventional thing". Convention
is an **upgrade prompt**, not a read-only mode, because a Word-style
compatibility mode would need the ability to work natively in the old format
and the installed `bpx` has only the v1.x schema. D3 records the prompt; if
read-only is preferred after all, only D3 changes.

Design record, including the rejected alternatives:
(internal design archive)

## Governing principle — the honesty charter

Six rules, written so each can fail a test rather than lose an argument. Every
decision below is downstream of them.

- **H1 · Every number on screen is a number in a file.** No rounding,
reformatting, or derived statistics presented as data. Already true where it
matters and worth protecting: values render through `json.dumps`,
`core/spread.py` labels the real extremes rather than its padded axis, chart
curves stop at their own domain edge.
- **H2 · The app never claims a check it did not run.** Absence of an error
means *not checked* whenever `validation_completed` is False. `inspector.py`
already refuses to say "Valid" in that case; every other validity surface uses
the same ladder.
- **H3 · What you see is what will be written.** If saving changes anything the
user did not change, the app says so beforehand. Formatting, comments, key
order and float spelling all count as the file.
- **H4 · What the app is reading is what the user opened.** The editor and the
validator look at the same document, or the app stops rather than annotating
one document with another's findings.
- **H5 · Every value has a stated origin.** Typed here, pulled from a named
reference, or synthesised by a converter. The third currently has no name on
screen.
- **H6 · Refuse before you fudge.** A blocked action with a clear reason beats a
completed action with a quiet compromise. A refusal always names what is wrong
and what unblocks it.

## What the app still gets wrong

Verified in the code, and each still open.

1. **Legacy conversion is invisible and the tree disagrees with the
diagnostics** (H4, H5). `bpx` converts a v0.x object before judging it and warns
that the conversion is "approximate": State synthesised, initial SOC set to 1,
lumped thermal conductivity dropped, optional v1 fields omitted so downstream
tools apply their own defaults, "cross-version semantic changes are not
corrected" (`bpx/parsers.py`). We capture the warning but a
`PythonWarningDiagnostic` carries no loc, so it lands as one anonymous amber
line. Our raw dict is never converted, so the tree renders v0.x while every
diagnostic refers to v1.x paths — a likely source of the orphan diagnostics the
nearest-ancestor rule currently absorbs.
2. **Save rewrites the whole file** (H3). `core/export.py` goes through
`json.dumps(indent=2)` / `yaml.safe_dump`. YAML comments are destroyed and
anchors resolved; JSON whitespace is normalised. Never stated anywhere.
3. **The main document is never checked against disk** (H3, H6). Only
`state/reference_snapshot.py` captures an `mtime`. A read-only reference shows a
stale band; the file being edited has no such check, so Save silently overwrites
a newer version.
4. **"Checked this far" is modelled but never said** (H2). The gateway documents
the staged abort and `inspector.py` honours it per parameter. No surface states
it at document level, so an empty diagnostics list reads as clean when it can
mean unexamined. An aborted run's unjudged sections also carry no tree mark and
so read exactly like clean ones — there is no fix inside the dot language, where
absence of a mark *is* "clean", so the honest statement is the document-level
one Phase 4 pins to the stream.
5. **The main document's record is thinner than a reference's** (H5). A
reference expands to Origin, Validity, Model, Contents, Citation or path; the
main card shows Model, BPX version, File, State, Contents. `core/document.py`
reads three of the Header's five fields — `Description` and `References` never
reach a surface where a person asks what a file is.
6. **`State: Modified` collides with the BPX `State` section**.

## Decisions

- **D1 · "Reference" wording is kept.** No rename, in code or on screen. The
three meanings are separated by context and by never abbreviating: *pinned
reference*, *reference library*, and the spec's `Header.References` shown as
**Citation**, which is already what the Workspace calls it for library sets.
- **D2 · Load facts live in two places, both permanent.** A **Read as** and a
**Checked** row in the file record, and a pinned group at the top of the
diagnostics stream that no filter chip can hide. No dismissible banner:
dismissal promises the fact stopped mattering.
- **D3 · Legacy files are offered a converted copy at open.** Dialog states the
version, the named consequences, and that the original is untouched. Buttons:
*Open converted copy* (primary, opens as a new unsaved document), *Open as-is,
read-only*, *Cancel*. A legacy file pinned as a **reference** needs no
conversion at all — references are already read-only, so its values are shown
and its validity reads *Not checked · BPX 0.4 cannot be checked against 1.1*.
- **D4 · YAML comments: warn, do not refuse.** Stated permanently in the file
record when the opened file contains comments, and confirmed once before that
document's first save. No "don't ask again" checkbox — a control that hides a
destructive fact is what this charter exists to prevent. A round-trip writer
(`ruamel.yaml`) is a separate future track, not part of this one.
- **D5 · Disk facts are shown**: size and modified time, in the file record.
Needed for the stale check regardless.
- **D6 · The record is editable exactly where the document is.** Title,
Description and Citation are editable in the main document's record and
read-only in a reference's. Not a second editor: the same `SetValue` command, so
undo is identical wherever the user typed. Every other row is a fact about the
file and is editable nowhere.
- **D7 · One validity ladder everywhere**: *Valid* · *N errors, N warnings* ·
*Not checked* · *Incomplete*. "Outstanding" becomes **Incomplete** — the only
chip whose noun never said what it counted.
- **D8 · One saved-state word pair**: *Unsaved changes* / *Saved*. Never
"State", never "Modified", never "Dirty". No BPX section name is ever borrowed
for an app concept.
- **D9 · "Pull" becomes "Use this value"**, undo reading
`Use "Thickness [m]" from Chen2020`. Wording only; the
`PullParameter`/`PullSection` command names are unaffected, so D1 stands.

## Design rules per surface

1. **File record (Workspace)** — one shape used by the main document and every
reference, with no row a reference has and the main lacks: Title · Description ·
Citation · Model · Read as · Checked · Contents · From (path, size, modified) ·
Saved to / Unsaved changes. *Read as* and *Checked* expand to the detail. Main
document: Title/Description/Citation editable in place. Reference: identical
rows, read-only.
2. **Diagnostics stream** — a pinned group above the parameter rows, exempt from
the filter chips, one line per structural fact (converted from BPX 0.4 ·
checking stopped at Header · comments will not survive saving). Never
dismissible. Its header is the file's own name; **"This file" is banned
everywhere**, in labels and prose alike.
3. **Legacy open prompt** — per D3. Consequences listed before the click,
including the reassurance that the original file is not modified.
4. **Stale-on-disk Save block** — per H6. Names the file and the time it
changed; offers *Reload*, *Save as copy*, *Overwrite*, each spelled out. *Save
as copy* must be one of the buttons, not a menu found afterwards: this is the
moment a user most likely has unsaved work.
5. **Refusal sentence shape, everywhere** — what is blocked, why, and the action
that unblocks it. "Cannot save: lgm50.json changed on disk at 14:22. Reload,
save as a copy, or overwrite."
6. **Control and echo share a verb.** "Pin as reference" then "Pinned
Chen2020", never "added".

## What the remaining phases build on

Phase 3 left a frontend-agnostic seam the UI phases consume rather than
rederive:

- `core/load_record.py` — frozen `LoadRecord` (fmt · is_legacy · checked ·
has_yaml_comments · size_bytes · mtime), built by
`LoadRecord.capture(data, document, path)`. Format and reach are carried from
the document's own load, never re-derived. Its `capture` call site
(`AppState.open`) is deliberately unwired until Phase 4, where the record is
first shown.
- **How far checking reached is modelled, not boolean**: `CheckReach`
(NOT_RUN · HEADER · PARAMETERISATION · COMPLETE). `ValidationResult.completed`
is a property derived from `reach`, so the two cannot disagree, and
`BPXDocument.validation_reach` mirrors it on every rebuild — the live answer
Phase 4's Checked row and stream line need, while `LoadRecord.checked` stays
the load-time snapshot.
- Legacy detection routes through `core/bpx_gateway.py` to
`bpx._migrations` — the one private `bpx` import, pinned by a test so an upgrade
fails loudly. Never a hand-rolled version check. An undetectable version field
reads as *not detectably legacy*: validation reports the fault itself, so
nothing is fudged.

## Remaining phases

### Phase 4 — the record and the stream group on screen
Design rules 1 and 2. `DocumentIdentity` gains `description` and `references`.
Card discipline applies to the editable rows: populate before connecting change
signals, clear `_touched` after `reset()`, or a bare Enter commits something
nobody typed.

Wireframes signed:
(internal design archive)

- **Record: "identity then the plaque"** — Title/Description/Citation editable
up top, immutable file facts in a quieter full-bleed band below (Model · Read
as · Checked · Contents · From · Status). Model absorbs the old "BPX version"
row ("DFN · BPX 1.1.0"); the reference's old "Validity" row is absorbed into
Checked (reach first, then the D7 verdict words). Empty editable rows state
their absence in ghost text ("Add a citation…").
- **Stream: the group uses the stream's own fold-header grammar** — exempt from
the chips, foldable but never hidden, absent when nothing is notable, muted
marks (never amber: these lines are not counted diagnostics).

### Phase 5 — the three interventions
Legacy open prompt, stale-on-disk Save block, YAML comment confirmation. All
three stand between a person and their work, so each gets its own wireframe pass
and its exact words agreed before it is built.

### Phase 6 — the wording sweep
Mechanical, against the signed glossary, once nothing else is in flight.

## Process

- Commit per phase, only when asked. Never push.
- Each phase ends with `python -m pytest` headless from the repo root and an
honest report. Two `PyparsingDeprecationWarning`s from `bpx` are expected.
`test_boundaries.py` and `test_typography.py` after every phase.
- On-screen proof after each UI phase, driving the real app and comparing
against the signed wireframes. Report divergences rather than declaring a match.
