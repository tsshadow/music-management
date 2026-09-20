- **De statusbalk en de navigatiebalk waren grijs, en de app tekende er niet achter.** Sinds
  targetSdk 35 negeert Android `statusBarColor`/`navigationBarColor` en zijn de balken
  transparant; of de WebView erachter zit, beslist Capacitor's `SystemBars`-plugin -- en die
  doet dat alleen als de pagina `viewport-fit=cover` in zijn viewport-meta heeft. Zonder dat
  kreeg de WebView een marge ter grootte van de balken en toonden de balken de eigen achtergrond
  van de WebView, een grijs (#303030) dat nergens in de app gekozen is. De webpagina draagt nu
  die meta en vult zelf de `env(safe-area-inset-*)`: de zoekbalk bovenaan (sticky, met dezelfde
  doorschijnende grond als Spotify), de onderste navigatie, Now Playing, het lade-menu, de
  wizard en de meldingen. `backgroundColor` in `capacitor.config.json` is de kleur van het
  eerste frame en van de marge op een oudere WebView (< 140), en `SystemBars.style: DARK` houdt
  de balk-iconen licht, ook op een telefoon met een licht thema.
