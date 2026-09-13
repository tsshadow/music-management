- **`MumaDiagnostics` weet nu ook wélke interface een rapport schreef.** `identify({bundleVersion,
  userAgent})` legt vast dat de webinterface heeft gedraaid, met welke frontend-build en welke
  WebView; ontbreekt die aanroep, dan meldt een rapport gewoon "legacy" zoals voorheen.
  `CrashReportManager` zet die drie feiten voor in de metadata-kop, boven het bestaande
  actielogboek dat de webacties en -fouten al bevatte.
