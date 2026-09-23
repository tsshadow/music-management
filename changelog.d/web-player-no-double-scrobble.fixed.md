- **Elke luisterbeurt in de app werd twee keer geteld.** Sinds de app de web-UI draait (12
  september) scrobbelden twee spelers dezelfde track: de native speler (`mobile`/`auto`) en de
  web-player in de WebView (`frontend`). De server herkent een dubbele alleen aan exact dezelfde
  tijd, en die verschilden, dus ~345 luisterbeurten op productie hebben een tweeling. De
  web-kopie was bovendien fout: bij een trackwissel door de service werd de starttijd niet
  vernieuwd (zes verschillende tracks kregen dezelfde `listened_at`), en vanuit een WebView op
  de achtergrond kwam hij een half uur te laat of mislukte hij — de "Scrobble mislukt"-melding.
  Op de native shell laat de web-player het scrobbelen nu aan de service over.
<!-- release notes -->
- **Luisterbeurten in de app werden dubbel geteld.** De app scrobbelde elke track twee keer; dat
  is nu één keer, en de melding "Scrobble mislukt" bij het terugkeren naar de app verdwijnt.
