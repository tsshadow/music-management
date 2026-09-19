- **De debug-build heeft een eigen icoon: grijs, met een D-badge rechtsonder.** Debug en
  release stonden naast elkaar op de telefoon en in Android Auto met exact hetzelfde icoon; het
  enige verschil was het label "MuMa Debug", en dat tekent de auto niet. Het debug-build-type
  legt nu zijn eigen `ic_launcher_foreground` over die van main heen (grijs `#9E9E9E`, de
  indigo-variant blauwgrijs `#78909C`, zodat de icoonkleur-instelling in debug testbaar blijft);
  de release-bestanden zijn onaangeroerd. Beide komen uit `tools/render_branding_icons.py`; de
  badge blijft binnen de 72dp van het launcher-masker. Het monochrome (thema-)icoon is niet
  aangepast: een thema-icoon toont debug en release nog steeds gelijk.

<!-- release notes -->

- **De debug-app heeft nu een grijs icoon met een D**, zodat je op de telefoon en in de auto ziet
  welke van de twee je opent.
