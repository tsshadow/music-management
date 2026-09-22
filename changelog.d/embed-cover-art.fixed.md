- **Gedownloade nummers krijgen weer een hoes.** Beide downloaders voegden yt-dlp's
  `EmbedThumbnail`-postprocessor toe, maar zetten `writethumbnail` niet. Die postprocessor bedt
  een thumbnail-*bestand* in: hij zoekt `info['thumbnails'][i]['filepath']`, vindt niets, meldt
  "There are no thumbnails on disk" en geeft het bestand onveranderd terug. Op de
  commandoregel impliceert `--embed-thumbnail` dat `--write-thumbnail`; via de Python-API niet.
  Niets ging stuk: downloads landden, de postprocessor draaide, en de bestanden hadden geen
  hoes. Op productie had 387 van de 149.626 SoundCloud-nummers er een. Geldt vanaf nu voor
  nieuwe downloads; bestaande bestanden hebben een aparte backfill nodig.
- **De nummerlijst in de webinterface valt terug op de artiestfoto.** De tabel tekende een kale
  `<img>` die bij een ontbrekende hoes direct naar het MuMa-merk sprong, dus de keten
  hoes → artiestfoto → getint vlak die de kaarten en de speler al gebruikten, bereikte nooit de
  lijst waaruit de meeste nummers gespeeld worden. Offline wordt de artiestfoto overgeslagen --
  dat is ook een serververzoek -- en het vlak blijft hier zonder titel: naast de titel van de
  rij is een tweede exemplaar op 48 pixels ruis, geen herkenning.

<!-- release notes -->

- **Gedownloade nummers krijgen weer een hoes.** De downloaders schreven de thumbnail niet weg,
  waardoor yt-dlp niets had om in te bedden. Geldt voor nieuwe downloads.
- **De nummerlijst toont de artiestfoto** als een nummer zelf geen hoes heeft, net als de kaarten
  en de speler al deden.
