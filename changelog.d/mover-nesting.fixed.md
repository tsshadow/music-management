- **Een release die je twee keer importeerde belandde in zichzelf.** `shutil.move` ziet een
  bestaande doelmap niet als botsing maar als "hier moet je in", dus de tweede kopie kwam één
  niveau dieper te staan: `Label/Release/Release/`. Er werd geen fout gegooid en niets gelogd. De
  opruimtak die de bron verwijdert sloeg pas aan bij de dérde kopie, als die geneste map óók al
  bestond -- dan pas gaf `shutil.move` een `shutil.Error`. Op productie hebben **429** releasemappen
  zichzelf op die manier ingeslikt, met als zichtbaar gevolg dat dezelfde track twee keer in de
  bibliotheek staat. De mover kijkt nu vóór de verhuizing of het doel bestaat en gebruikt daarna
  dezelfde regel als de renamer: gelijke bestandsnamen en -groottes betekent een dubbele download
  en de bron verdwijnt; verschilt de inhoud, dan blijven beide staan met een WARNING. De
  vergelijking zelf verhuisde naar `services/importer/release_compare.py`, want beide stappen
  hebben hem nodig.

<!-- release notes -->

- **Een release die twee keer geïmporteerd werd, kwam in zichzelf terecht** en verscheen daardoor
  dubbel in de bibliotheek. Dubbele downloads worden nu herkend en opgeruimd; bij twijfel blijft
  alles staan met een melding.
