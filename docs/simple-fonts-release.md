# Simple Fonts release — 2026-11-26

## Scope

Two active faces only, unchanged TTF/WOFF2 bytes and unchanged 0.8 font ZIP.
Two-column desktop cards stack below 720px; cards are fixed at 490px with a
300px specimen area. Each article contains its own font downloads, labelled
“Scrivi qualcosa” input, and accessible recycle control. Custom text is assigned
with textContent, never interpreted as HTML. Both dimensions are measured during
bounded fitting after typing, recycling, font loading, resizing and tab selection.
Five funny Italian presets per face use a deterministic seeded sequence without
immediate repetition. Long text becomes smaller; unsupported glyphs use fallback.
Fonts ends with CC BY 4.0 / Balilla Type Lab attribution. Study retains all twelve
unchanged lazy originals as an image-only horizontal rail. The original-materials
archive and all its public actions are removed. Research details remain intact.

## Gates

- Private complete regression suite: 75 passed in 106.18s.
- Sanitized public complete suite: 57 passed in 57.55s, including rebuilding both
  active faces twice from authorized inputs and matching the frozen font hashes.
- Generator: 45 artifacts; deterministic regeneration and obsolete-file cleanup
  checked by pytest. The unchanged font ZIP SHA-256 is
  6d0ec481d4fd366d0ce02c3e22f9a5afc02490437c46442cf2b7519713516d55.
- 64 passing stand-in DOM checks cover both inputs (Italian accents, other scripts, literal
  markup, 22,000-character text and empty input), preset restoration, full pool
  reachability, no immediate repeats, seeded replay and resize fitting.
- Mutation: temporarily changed the capitals card TTF link to the panel font in
  the template, regenerated, and observed the card-local-download test fail
  (1 failed in 0.05s, exit 1). Restored; exact test then passed in 0.03s.
- git diff --check passed in both repositories.
- Source preflight passed for all exported tracked files, nested ZIP contents and
  reachable Git blobs: no scanned credential patterns or machine-local paths.

## Public source

https://github.com/yolo-maxi/ricostruzioni-digitali — public, default branch main,
verified through GitHub API. A new root history contains a sanitized snapshot;
none of the private repository's history was pushed. The private source/history
remain intact. Omitted: explicitly unpublished close photo, original archive,
withdrawn font artifacts, operational notes and caches. The only extracted legacy
code is three generic geometry helpers required by the active panel builder.
The public README documents source-photo rights separately from CC BY 4.0 font
licensing and explains why the private close-photo cross-check cannot rerun.

## Delivery

Target: https://ricostruzioni-digitali.repo.box/ . Registry app and public_listed
policy unchanged. No Caddy or registry edits. The custom-input release passed
publish dry-run and actual publish. External HTTPS returned 200 and exact local
byte equality for all 45 artifacts, including all four active font downloads and
all twelve original images. Home includes both custom inputs and recycle controls,
and Study links the verified public repository. The originals ZIP and withdrawn
TTF/WOFF2 paths return 404. See live-verification.json for per-artifact SHA-256.
Public code/artifact release: df07bcfe2c9e1c8e737ea886a1357fff1d14ae5b.
The publisher's route warning was checked against the existing generated route:
the unchanged app hostname points at its expected static root through the central
gate. GitHub API reports public visibility and main as default; its public page
returns HTTP 200. The private canonical checkout remains untouched.

## Verification boundary

No interactive browser or screenshot proof is claimed. The browser runner remains
suspended; no replacement browser was invoked. Tests use DOM/source contracts,
mocked layout measurements and real font rebuilds, followed by external HTTPS
artifact equality. Actual browser typography, minimum-font preferences, native
input UI and screen-reader announcements remain visually/uninteractively unverified.
