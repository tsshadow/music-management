# Festival lineups

A lineup is a text file of artist names under `/music/metadata/festival-lineups`. `getLineups`
lists them, `getSongs?festivalLineup=` and `getSpotifyTracks?lineup=` filter on them, and the web
and phone browse pages show them. This document says where the names come from, because that turns
out to be the hard part.

## The file, and what its path means

A lineup's id is the path to its file without the extension, so `Defqon.1/2014/RED` is the RED
stage of that edition. **Every directory on that path is itself a lineup**, holding the union of
everything below it: `Defqon.1/2014` is that edition across its stages, `Defqon.1` the festival
across its editions. No artist name is written down twice, and a correction is made in one place.

Split by stage only for a festival whose stages differ in genre — Defqon.1, Decibel. For a
single-genre festival the edition is one file, `Harmony of Hardcore/2026.txt`. Flat files from
before the hierarchy (`Intents 2025.txt`) are still read exactly as they were.

The file holds one artist name per line and nothing else. `FestivalLineupRepository` treats every
non-empty line as an artist, so there is no comment syntax and a header would become an artist
called `# generated`.

## Why the names have to be right

`getSpotifyTracks` filters with `LOWER(artist_display_name) IN (...)`, comparing the *whole*
display name. `Angerfist` matches a track by `Angerfist` and never one by `Angerfist & Outsiders`,
and a spelling this library stores differently (`D-Block & S-te-Fan` against
`D-Block and S-te-fan`) matches nothing at all and says so nowhere.

That is what `scripts/import_festival_lineup.py` is for: it checks every line against the artist
names LMS actually holds and reports what will match, what will not, and the closest names in the
library, before writing anything.

## Where the bill comes from

Typed out by hand from the festival's own bill. Two sources were tried and rejected:

- **Partyflock**, named in the browse design as the preferred source, forbids scrapers in its terms
  of use (article 5) and reuse of its data without permission (article 6).
- **The library's own FESTIVAL tags.** Warm-up mixes, livesets and podcast episodes all carry the
  tag, so the derived "lineup" filled up with names that were never on the bill.

What is left is reading the festival's own line-up page. The prompt below is what does that in
Claude for Chrome; the JSON it produces is the format the import path takes.

## The prompt

```
Je maakt festival-lineupbestanden voor mijn muziekbibliotheek. De uitvoer is JSON.

FESTIVALS (loop ze één voor één af):
- Defqon.1, 2014 t/m 2026
- Decibel Outdoor, 2014 t/m 2026
- Harmony of Hardcore, 2014 t/m 2026
- Dominator, 2014 t/m 2026
- Intents Festival, 2014 t/m 2026

FORMAAT
Eén object per lineup:

{
  "festival": "Defqon.1",
  "year": 2014,
  "stage": "RED",
  "artists": ["Angerfist", "Da Tweekaz"]
}

- "stage" is optioneel: laat het veld wég bij een festival waarvan alle podia
  dezelfde stijl draaien. Dan is de hele editie één object.
- Splits wél per podium als de podia in genre verschillen (Defqon.1, Decibel).
- Meerdere objecten mogen in één bestand als JSON-array. Groepeer per festival:
  alle edities en podia van Defqon.1 in één array.
- Schrijf de podiumnaam zoals het festival hem schrijft (RED, BLUE, UV, BLACK).
- Meerdere weekenden of dagen van dezelfde editie horen in hetzelfde object,
  dubbele namen weggelaten.

BRONNEN
De officiële festivalsite (line-up- of timetablepagina), anders de Wikipedia-pagina
van die editie. Gebruik Partyflock NIET: hun voorwaarden verbieden hergebruik van
hun data. Vind je een editie niet, meld dat en ga door — verzin nooit namen. Noem
per object de bron-URL in je bericht, niet in de JSON.

REGELS PER NAAM
- Exact zoals op de bill, inclusief hoofdletters, punten en koppeltekens:
  "D-Block & S-te-Fan", "Sub Zero Project", "Da Tweekaz".
- Haal set-decoratie weg: "(live)", "LIVE", "presents ...", "closing set",
  "hosted by", tijden, podiumnummers.
- b2b of samenwerking: zet zowel de gecombineerde naam zoals hij op de bill staat
  ("Angerfist & Outsiders") als elke artiest apart in de lijst. Beide, want het
  filter matcht op de hele artiestnaam.
- Schrijf "b2b" als "&" in de gecombineerde naam.
- Alleen artiesten; MC's en hosts overslaan als de bill die apart zet.
- Volgorde van de bill aanhouden, duplicaten binnen één object weglaten.

OPLEVERING
Per festival één codeblok met geldige JSON, plus de bron-URL's eronder in gewone
tekst. Werk festival voor festival en wacht na elk festival op mijn "ga door".
```

The prompt is Dutch because the conversation it runs in is; the format it produces is not
language-specific.

## Importing what comes back

One object becomes one file. The artist names go in on stdin, the path comes from the flags:

```bash
jq -r '.artists[]' lowlands-2026-alpha.json \
  | python3 scripts/import_festival_lineup.py \
      --festival Lowlands --year 2026 --stage Alpha --file - --write
```

Without `--write` nothing is created and you get the match report first — the count, and per
unmatched line the closest names the library does have, so the correction is a copy rather than a
search. Leave `--stage` out and the file becomes `Lowlands/2026.txt`.

For an array of objects, run it once per element (`jq -c '.[]'`), because each object carries its
own festival, year and stage.
