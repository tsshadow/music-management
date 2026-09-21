- **De labelchip in de speler rendert weer, en de festivalrij in de nummerdetails bestaat nu
  echt.** De speler las `track.label || track.publisher`; LMS zet op een song-node `labels: [...]`
  (de PUBLISHER-cluster) en nooit een van die twee, dus geen enkel nummer kreeg zijn label onder de
  genres terwijl de sheet -- die wél `labels` leest -- het gewoon toonde. De sheet las op zijn beurt
  `track.festival`, een veld dat LMS nooit stuurde: de song-node krijgt nu `festivals` naast
  `labels` en `moods`. Die array vult zich pas als `FESTIVAL` in de extra-tags van de scanner staat.
