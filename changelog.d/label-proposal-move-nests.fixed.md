- **Het bevestigen van een labelvoorstel kon een release in zichzelf stoppen.** `shutil.move`
  faalt niet als de bestemming al een map is: hij verplaatst de bron er *in*. De release komt
  dan één niveau dieper te staan, de scan indexeert hem twee keer, en niets meldt dat er iets
  misging. De mover van de importer leerde dat op 4 september; dit endpoint doet dezelfde
  aanroep en had die controle nooit. Op productie is het hier nog niet misgegaan — de 552
  mappen die zichzelf bevatten komen allemaal van de mover, van vóór die datum — maar de
  aanroep is identiek en de schade zou dat ook zijn. De regel staat nu op één plek,
  `services/common/Helpers/ReleaseFolder.py`, waar zowel de importer als music-manager bij kan:
  music-manager bevat `services/importer` niet, en dat is precies waarom de controle daar
  ontbrak. Botst de bestemming, dan verplaatst er niets, blijft het voorstel openstaan en telt
  de beheerpagina het apart in plaats van het als bevestigd op te tellen.
