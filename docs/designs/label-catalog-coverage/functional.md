# Label Catalogue Coverage — Functional Design

## Overview

The library holds label releases under `EPs/<label>/<catalogue number> <release name>/`. Dirty Workz
numbers its releases `DWX0001` … `DWX2212`; if the library holds 001–303 and 305–309, nothing today
shows that 304 is not there. The owner has to sort a folder listing by hand and read the gaps off it.

This feature adds a **Catalogus** section to the label edit page (Beheer → Labels → a label) that
reads the catalogue numbers out of the release folders the label already has, groups them into
series (`DWX`, `DWXCD`, `DWXCVR`, …), and per series shows the observed range, how much of it is
present, and which numbers in that range are not. It computes nothing beyond what is on disk: the
claim is "of the numbers between the lowest and highest we hold, these are not here", never "the
label released these and you do not have them" — a label may skip numbers, and we cannot know.

## User Stories

- As the library owner, I want to see per label how complete my catalogue is, so that I know
  whether it is worth hunting for more.
- As the library owner, I want the numbers that are not present listed compactly, so that a gap of
  one release and a gap of fifty read differently.
- As the library owner, I want to copy every absent catalogue number as a list of search terms, one
  per line, so that I can paste them into a search or a download tool without retyping.
- As the library owner, I want a release with an odd suffix (`DWX1105D`, `DWX0544-`) to count as
  filling its position but still be pointed out, so that I can decide whether it is the real release.
- As the library owner, I want catalogue numbers the page cannot read (`DWXFREE`) shown rather than
  silently dropped, so that a mistyped folder name is visible.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Opening the edit page of a label that has releases in the library | The page shows as before; a **Catalogus** section appears below the catalogue prefixes, loading on its own. The rest of the page is usable while it loads. |
| The label has releases numbered `DWX000`…`DWX2212`, some absent | One block per series with a header like `DWX · 000–2212 · 1921 van 2213 aanwezig (87%)`, a thin progress bar, and below it the absent numbers as runs: `DWX0177, DWX0223, DWX0287–DWX0289, …`. |
| The label has several series (`DWX`, `DWXCD`, `DWXCVR`) | One block per series, the series with the most present numbers first. |
| A series has many runs of absent numbers | The first ~40 runs are shown with a "toon alles" link that expands the rest. |
| Pressing **Kopieer als zoektermen** on a series | Every absent catalogue number of that series, fully written out (`DWX0287`, `DWX0288`, `DWX0289`, one per line) is on the clipboard; the button briefly confirms. |
| A release carries a suffix (`DWX1105D`, `DWX0544-`) | Position 1105 / 0544 counts as present; the catalogue number is listed under **Varianten** in the series block with the release folder as tooltip. |
| A catalogue number cannot be read as prefix + number (`DWXFREE`) | It is listed under **Overig** with its release folder as tooltip and is never counted as a gap. |
| A single mistyped folder makes a series span an absurd range (`DWX0001` … `DWX2000000`) | The header still shows range and count; the absent list is replaced by "te veel om op te sommen" and the copy button is not offered for that series. |
| The label also has files under `Soundcloud/`, `Podcasts/` or `Top 100/` | Those are not part of the catalogue and do not appear; alleen de EPs-map telt. A channel or show folder never becomes a series or an "overig" entry. |
| Some of the label's release folders have not been picked up by the scanner's label link yet | They still count: the section reads the label's folder on disk, not only what the library has linked to the label. |
| The label has releases but none with a readable number | The section says so ("Geen leesbare catalogusnummers in de mappen van dit label.") instead of showing empty blocks. |
| The label is not in the library yet (rules entered ahead of the first file) | The section is not shown. |
| Loading the catalogue fails | The section shows its own error line; the rest of the page is unaffected. |

Wording: the page says **niet aanwezig**, never "ontbreekt" or "missing", and calls the figure
**waargenomen bereik** (observed range) — nothing is claimed before the lowest or after the highest
number the library holds.

## Acceptance Criteria

1. The edit page of a label with releases shows a Catalogus section; the page's existing sections
   render before the catalogue has loaded.
2. For a label with `DWX000`…`DWX2212` on disk, the DWX block's header states the range, the count
   present out of the range size, and the percentage; the absent numbers below match a manual folder
   count.
3. Consecutive absent numbers are shown as one run (`DWX0287–DWX0289`); a lone one as itself.
4. "Kopieer als zoektermen" puts every absent number of that series on the clipboard, one per line,
   each written in full with the series' zero padding.
5. `DWX1105D` fills position 1105 and appears under Varianten; `DWXFREE` appears under Overig and
   creates no gap.
6. `247HC001` is read as series `247HC` number `001`; `R909-29` as series `R909` number `29`;
   `DWXCD-050` as series `DWXCD` number `050`; `AFT3R001` as series `AFT3R` number `001`.
7. A series whose observed range exceeds 20 000 numbers shows counts only and no list.
8. A label with no readable numbers shows the empty-state sentence; a label not in the library
   shows no Catalogus section.
9. A failure to load the catalogue is reported inside the section and leaves the rest of the page
   working.
10. Only the EPs folder counts: a label's SoundCloud sets, podcasts and Top 100 entries never show
    up in the section, and a release folder that the library has not linked to the label yet is
    still counted.

## Open Questions / Not Yet Decided

Deferred to later phases, deliberately not in this change:

- **A coverage column in the labels list.** The per-label computation reads every media file of the
  label; the cost across thousands of labels is unmeasured, so the list stays as it is.
- **A per-number cell strip** (one cell per catalogue number, coloured present/absent) as a visual
  alternative to the runs list.
- **A manual write-off table**: marking a number as "known never released" or "not wanted" so it
  stops appearing. Until that exists the page reports observation only, which is why it says
  "niet aanwezig" rather than "ontbreekt".
- Whether the tagger's `rules_catid_label` prefixes should be cross-checked against the series
  found on disk (a series with no prefix rule, or a rule with no series).
