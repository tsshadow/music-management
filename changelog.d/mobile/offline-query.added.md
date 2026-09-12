- **De nieuwe interface leest de gedownloade bibliotheek nu zonder verbinding.** `MumaStorage.query`
  beantwoordt de `/rest`-aanroepen die de webspeler echt doet — tracks, albums, artiesten, genres,
  jaren, labels, zoeken, favorieten en hoesjes — uit Room en de bestanden op het toestel, in
  precies de JSON-vorm en met precies de id's die LMS teruggeeft, zodat een offline rij en een
  online rij van hetzelfde nummer één rij zijn. Alleen tracks die daadwerkelijk gedownload zijn
  tellen mee, en een aanroep die offline niets kan betekenen geeft een leeg maar geldig antwoord in
  plaats van een fout.

<!-- release notes -->

- De nieuwe interface werkt nu ook zonder verbinding: alles wat je gedownload hebt staat gewoon in
  de lijsten, met dezelfde hoesjes en dezelfde filters.
