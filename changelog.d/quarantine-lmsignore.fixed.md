- **LMS zou de quarantaine gewoon geïndexeerd hebben.** De muma-scanner slaat verborgen mappen
  sinds de vorige wijziging over, maar LMS is een tweede indexer met een eigen regel — en die heeft
  er geen: `exploreFilesRecursive` daalt elke map in en stopt alleen bij een `.lmsignore`
  (`ScanStepScanFiles.cpp`, naam uit `ScannerSettings.hpp`). Zonder ingestelde quarantainemap landt
  die als `.quarantine` naast de muziekroot, precies de boom waar de LMS-bibliotheek op wijst, dus
  een geparkeerde dubbele release was als LMS-tracks teruggekomen — het besluit dat de importer net
  had genomen, ongedaan gemaakt door de indexer. De quarantaineroot krijgt nu bij aanmaken een
  `.lmsignore`. Dat gebruikt LMS' eigen mechanisme in plaats van zijn scanner aan te passen.

<!-- release notes -->

- **Wat in quarantaine gaat blijft nu ook uit de speler.** Gequarantainede dubbele releases konden
  via LMS alsnog in de bibliotheek opduiken.
