- Genres en artiesten zonder portret krijgen in Android Auto een cover die de app zelf tekent, in
  de kleur die MuMa voor dat genre stuurt. Die niveaus waren tekstlijsten met een generiek icoon:
  de auto tekent alleen een raster als de items iets te tonen hebben, dus zonder beeld hielp de
  raster-hint uit de vorige release daar niets. Een artiest met een portret houdt het portret.
- De kleuren komen van `GET /api/library/genres` en worden een uur vastgehouden. Is MuMa
  onbereikbaar, dan blijven de kleuren staan die er al waren — de auto is precies de plek waar dat
  het vaakst gebeurt, en een leeg raster is erger dan een oud.
