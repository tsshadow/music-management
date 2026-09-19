- **Een nummer aantikken in de auto speelde alleen dat nummer en stopte dan.** Elk
  nummer-niveau media-id (genre-map, playlist, album, favorieten, zoekresultaat, feed) gaf
  Media3 een wachtrij van één; de telefoon speelt de lijst vanaf dat nummer. `onSetMediaItems`
  lost een tik nu op naar de gebladerde lijst plus startindex (`queueForTap`); een lijst die
  het nummer niet meer bevat valt terug op het oude pad, dus speelt nog steeds het ene nummer.

<!-- release notes -->

- **Een nummer aantikken in de auto speelt de lijst vanaf dat nummer**, in plaats van alleen
  dat nummer.
