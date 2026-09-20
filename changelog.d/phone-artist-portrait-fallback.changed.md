- **Een nummer zonder hoes toont in een rij of kaart de foto van zijn eerste artiest, niet een
  tegel met alleen de titel.** De speler deed dat al (hoes, dan portret, dan het getinte
  paneel); `TrackCard` en `TrackRowCompact` sloegen het portret bewust over, en een plank
  "Recent uitgebracht" zonder hoezen werd zo een kolom grijze titelblokjes. De keten is nu in
  `coverArt.artistImageFallback()` gedeeld, met `primaryArtistOf()` als de ene plek die de eerste
  artiest kiest (de `artists`-lijst met ids gaat voor de samengevoegde string). MuMa zegt "geen
  portret" met een 404 die de browser niet cachet, dus een mislukte URL wordt per sessie
  onthouden en de volgende rij van dezelfde artiest begint meteen bij het paneel. Van de 56.800
  artiesten hebben er 11.759 een portret; de 44.972 met status `failed` komen pas bij de
  volgende opstart na de 30-daagse wachttijd opnieuw aan de beurt, dus de planken vullen zich
  niet in één keer.
