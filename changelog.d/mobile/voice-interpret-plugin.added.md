- **`MumaSpeech` begrijpt spraak nu ook voor de webspeler.** Drie nieuwe methoden op het bestaande
  `MumaSpeech`-plugin: `interpret` draait de gesproken of getypte tekst door dezelfde `core/voice`-
  parser en -resolver die Android Auto en de microfoon van de Kotlin-app gebruiken, en levert een
  klaar-voor-de-UI resultaat terug (wat verstaan is, of het een duidelijke opdracht/een vraag/niets
  is, en bij een opdracht de filters als `getSongs`-parameters of het album/de afspeellijst-id) —
  het plugin speelt zelf niets af, dat blijft aan de webkant. `vocabulary` geeft de tekst van "wat
  verstaat MuMa" terug uit dezelfde stringresources als `VoiceCommandsFragment`, in elke taal die de
  app al heeft. `trace` geeft de laatste spraakverzoeken uit `VoiceTraceLog` voor een diagnosescherm
  op het web. De parser en de resolver zijn ongewijzigd; dit is alleen een derde deur ernaartoe,
  naast de auto en het microfoonscherm.

<!-- release notes -->

- De spraakherkenning van de app is nu ook beschikbaar voor de nieuwe interface, via hetzelfde
  woordbegrip als de auto en het bestaande microfoonscherm.
