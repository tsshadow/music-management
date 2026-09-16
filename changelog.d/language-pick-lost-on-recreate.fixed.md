- **Een andere taal kiezen in de app ververste het scherm en veranderde niets.** De taalkeuze
  zette de webkant meteen om en liet de shell de activity opnieuw aanmaken, maar het opslaan
  naar het account hing achter een debounce van 400 ms — die timer stierf mee met de WebView.
  Na het herladen kwam de taal uit `localStorage` wél goed op, waarna `applyAccountSettings`
  de oude taal van het account er weer overheen zette. `LanguageSetting` wacht nu tot het
  account de nieuwe taal heeft (`flushLocaleSave`) voordat hij `setAppLocale` aanroept; in een
  browsertab verandert er niets, daar herlaadt niets.

<!-- release notes -->

- **Een andere taal kiezen werkt weer in de app** — het scherm ververst en komt in de gekozen
  taal terug, in plaats van in de oude.
