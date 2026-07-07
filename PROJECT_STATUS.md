# PROJECT_STATUS — Explore_BPX

Current engineering status. Roadmap and acceptance criteria live in
[docs/04-roadmap.md](docs/04-roadmap.md); this file records what is actually built
and what is next.

## Completed

- **Phase 1** — foundation (document loading, tree navigation, parameter
  inspection, basic editing with undo, continuous validation, save/export,
  `NavigationService`, `DocumentSession`/`AppState`, SearchPopup).
- **2.1** SearchPopup navigation.
- **2.2** Distinct Save vs Export semantics.
- **2.3** Keyboard navigation of validation issues (Enter/Return activates the
  selected issue through `NavigationService` in both the Validation workspace and
  the parameter-scoped Issues tab; selection change alone does not navigate).

## Known doc drift resolved

- Roadmap 2.3 was originally a "non-modal validation review cursor." It was
  descoped before implementation as conflicting with the app's evolved philosophy
  (avoid modes, keep the editor spatially stable, single `NavigationService`,
  minimal workflow state) and replaced with keyboard navigation of the existing
  issue lists. Docs 02/03/04/05 were updated to match; the top context bar is now
  a context-only surface (no mode role).
- Roadmap 5.1's dependency was repointed off the (cut) review cursor to the
  Validation workspace and issue mapping (Phase 1).

## Next

- **2.4** Parameter information popover and self-contained ParameterCard —
  independent of Workspace/multi-document work. See
  [docs/04-roadmap.md](docs/04-roadmap.md#24-parameter-information-popover-and-self-contained-parametercard).
