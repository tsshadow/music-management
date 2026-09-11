- **"Hoog gewaardeerd" op het startscherm was altijd leeg.** De sectie vroeg de server om nummers met
  een rating, en stuurde die rating behalve als `ratingMin`/`ratingMax` óók als cluster mee. De server
  kent geen clustertype `RATING`, antwoordde "not found" en liet het hele verzoek vallen. Sinds de
  dag dat de code geschreven werd, zonder dat iemand een fout zag: een lege sectie wordt gewoon niet
  getoond.

<!-- release notes -->

- De sectie "Hoog gewaardeerd" op het startscherm toont nu daadwerkelijk je hoog gewaardeerde nummers.
