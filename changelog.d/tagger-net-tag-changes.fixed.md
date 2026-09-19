- **Een bestand waarvan de tags netto niet veranderden werd toch elke ronde herschreven.**
  `Tag.has_changes()` was een plakkende vlag: elke mutatie zette hem aan en alleen een save
  zette hem uit. De artiestregels doen op elk "MOTZ Premiere"-bestand `[A, B] → [A] → [A, B]`,
  dus het bestand werd elke pass opnieuw geschreven en LMS las het elke pass opnieuw in, voor
  een tag die eindigde waar hij begon. De vlag is nu een vergelijking met de waarde bij het
  inlezen; de basislijn schuift pas op nadat de save is gelukt, en een geleegde tag houdt
  zijn basislijn als er weer een waarde in komt.

<!-- release notes -->

- **Bestanden werden herschreven terwijl er niets veranderde.** De tagger schrijft nu alleen
  als de tag écht anders is dan hij was.
