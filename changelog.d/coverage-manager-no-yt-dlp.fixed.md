- **De Volledigheid-tab gaf "No module named 'yt_dlp'" zodra hij live stond.** De opgeslagen
  telling werd gelezen via een dataclass in `deep_sweep.py`, en die module importeert yt-dlp
  bovenaan; de manager-container heeft yt-dlp niet en gaf dus geen enkele rij terug. De
  dataclass staat nu in `account_snapshot.py` zonder die import. Een test leest een rij in een
  subprocess waarin `yt_dlp` onimporteerbaar is, zodat dit niet stil terug kan komen.
