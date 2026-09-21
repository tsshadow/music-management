- **Per kanaal is nu te zien hoe compleet het is.** De diepe ronde van de downloader telde al
  per account hoeveel tracks het platform vermeldt, hoeveel het archief heeft en hoeveel er nog
  open staan, maar schreef dat alleen naar het log. Die telling wordt nu als momentopname
  bewaard in `downloads_account_checks` (`snapshot_*`, per SoundCloud-account en per
  YouTube-kanaal-en-type) en getoond onder Beheer → Downloaders → Volledigheid: tegels met
  geteld/compleet/achterstand, de afschrijvingen per reden, en per kanaal een balk
  gearchiveerd/uitgesloten/open met laatste download en leeftijd van de telling. De telling is
  een partitie -- gearchiveerd + uitgesloten + open = vermeld -- en niet de lopende getallen uit
  het rapport, die verlopen afschrijvingen meetellen en niet optellen. Er staat bewust geen
  einddatum bij: de rondes lopen per kanaal op eigen tempo en een 429 remt alles tegelijk af.
  `GET /api/downloaders/coverage/{source}`. Het YouTube-archief krijgt met `migrate_v31` een
  `added_at`; bestaande rijen blijven NULL ("onbekend") in plaats van allemaal op de deploydag
  te landen.
<!-- release notes -->
- Beheer → Downloaders → Volledigheid laat per SoundCloud-account en YouTube-kanaal zien hoeveel
  tracks er zijn, hoeveel je hebt, hoeveel er bewust zijn overgeslagen en hoeveel de downloader
  nog moet ophalen -- plus wanneer de laatste download binnenkwam.
