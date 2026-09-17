- **De speler op de telefoon toonde bij een track zonder cover altijd hetzelfde platte MuMa-merk,
  en de mini-speler had een aparte ronde artiestenfoto naast de naam die nergens anders in de app
  voorkwam.** Een bibliotheek die grotendeels zonder covers zit oogde daardoor stuk in plaats van
  gewoon ongedecoreerd. `Artwork.svelte` kent nu een expliciete val-door-keten cover → artiestfoto
  → getint paneel met de titel, gedeeld door de mini-speler (44px) en het volledige scherm; een
  nieuw nummer reset altijd terug naar de cover, zodat een oude 404 nooit de cover van het
  volgende nummer overslaat. De achtergrond van het volledige scherm is een verticaal verloop van
  de genre-tint van het spelende nummer (`trackTint()` in `genreTints.js`, dezelfde
  server-geleverde kleur als de genregrid) naar het neutrale `#121212`, in plaats van vlak zwart.

<!-- release notes -->

- De speler toont bij een track zonder cover nu de artiestfoto of anders de titel op een gekleurd
  vlak in plaats van altijd hetzelfde logo, en het scherm krijgt een vleugje van de genre-kleur in
  plaats van vlak zwart.
