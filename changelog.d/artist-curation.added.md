- **Artiestcuratie in Beheer.** `library_artists` vult zichzelf — de scanner slaat elke naam op die
  een taggerregel ooit maakte — en zo'n een op tien is een echte artiest. Er is nu een wachtrij,
  in de vorm van Genre Curatie: per naam goedkeuren, afkeuren of corrigeren naar een andere
  spelling, in bulk per pagina. Elke beslissing gaat naar `rules_ignored_artists`, dus de tagger
  handelt ernaar zonder nieuwe regelcode; de 2.658 bestaande redirects staan als afgekeurd
  voorgesorteerd. Naast elke naam staat een **advies** uit de analyse van 0.0.54, nu eindelijk
  ergens aan vastgemaakt: "verwijderen" voor wat geen naam kan zijn (`Premiere`, `OUT NOW`,
  `***`), "samenvoegen met X" voor spellingvarianten en een losse `DJ`/`MC` (`Dr.Peacock` →
  `Dr. Peacock`, `DJ Angerfist` → `Angerfist`), met de reden erbij. Het woordenboek van de
  analyse zijn uitsluitend de goedgekeurde namen — geen bootstrap uit de data zelf, want die gaf
  `Rbr → RBR ©` — en een herschrijving naar een spelling met mínder nummers wordt niet
  geadviseerd. Een advies doet nooit iets uit zichzelf; "Advies opvolgen" is de knop.

<!-- release notes -->

- Beheer heeft nu Artiestcuratie: per naam goedkeuren, afkeuren of samenvoegen, met een advies
  erbij ("verwijderen", "samenvoegen met Angerfist") en een knop om dat advies per pagina op te
  volgen.
