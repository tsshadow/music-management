- **Een genreregel op een artiest- of labelpagina bleef ongebruikt liggen.** De pagina sloeg de
  regel op en ververste de draaiende tagger, maar markeerde de bestanden niet voor een nieuwe ronde
   -- en zonder die markering heeft de tagger geen reden om er ooit nog langs te lopen. De regel
  wachtte dus achter een wachtrij van 165.394 bestanden, terwijl de pagina "Regel opgeslagen."
  meldde. De management-endpoints voor precies dezelfde regels deden dit al wél; die twee zijn nu
  één gedeelde `invalidate_quietly` in `RescanInvalidator`, zodat ze niet opnieuw uit elkaar kunnen
  lopen. De bevestiging noemt voortaan hoeveel bestanden er in de wachtrij zijn gezet, want "geen"
  en "duizend" zagen er tot nu toe hetzelfde uit.

<!-- release notes -->

- **Een genreregel op een artiest of label werd opgeslagen maar niet toegepast.** De betrokken
  nummers worden nu vanzelf opnieuw getagd, en je ziet meteen om hoeveel bestanden het gaat.
