- **De lege hoes in de webinterface was nog altijd het Spotify-logo.** Het stond in zes bestanden
  (`spotify-fallback.svg` en `unknown-cover.svg`, elk in `services/frontend/public/images/`, in de
  LMS-`docroot` en in de `approot` waar de artwork service zijn standaardhoes vandaan haalt), en
  het was met de hand getekend, los van het merk. De placeholder is nu het MuMa-equalizerteken,
  afgeleid uit dezelfde `BARS`-constanten als het app-icoon en de notificatieglyph in
  `tools/render_branding_icons.py`, dus hij kan niet meer los gaan lopen van het icoon. De kleuren
  blijven de paneelgrijzen (`#282828` op `#181818`), want een ontbrekende hoes hoort dof te zijn en
  geen merkstempel.

<!-- release notes -->

- **De lege hoes in de webinterface toonde nog het Spotify-logo.** Dat is nu het MuMa-teken.
