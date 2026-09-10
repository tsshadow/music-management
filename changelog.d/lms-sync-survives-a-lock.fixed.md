- **De sync gaf het op zodra LMS zijn database even vasthield.** Bij de deploy van 0.56.0 startte LMS
  zijn eigen scan, de database zat op slot, en de sync stopte na **één van de 285.332 tracks**.
  Daarna probeerde niets het opnieuw, want hij draaide alleen bij het opstarten — dus LMS werkte een
  dag lang met een verouderd beeld en toonde nog gewoon elke kopie van een nummer.
- Een lock is de server die werkt, geen fout. Een blok dat op slot loopt wordt nu afgewacht (tien
  pogingen, vijftien seconden ertussen) in plaats van de hele ronde weg te gooien, en de wachttijd op
  een statement gaat van 5 naar 30 seconden — vijf was precies te kort voor een scanstap. Een blok
  dat op slot blijft wordt overgeslagen en geteld; de volgende ronde schrijft dezelfde rijen.
- Een fout die géén lock is wordt niet afgewacht: wachten op een kapot schema helpt niemand en
  begraaft de echte melding.
- **En de sync draait nu in een lus, niet alleen bij het opstarten.** De versie-worker groepeert
  ongeveer 500 tracks per uur zolang hij achterstand heeft, en wat hij leert bereikte de server pas
  bij de volgende deploy. Elk uur, in te stellen met `LMS_DB_SYNC_SLEEPTIME`.
