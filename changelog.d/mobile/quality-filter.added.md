- **"Speel flac hardstyle af" en "speel hardcore in hoge kwaliteit af" werken.** De spraakparser
  leest flac, lossless, wav en hq als kwaliteitsondergrens, en "hoge kwaliteit" of "high
  quality" als 320 of beter; het voorzetsel ervoor gaat mee weg zodat "in" niet in de vrije term
  belandt. Het filter reist als `QUALITY`-cluster naar `getSongs`, dezelfde cluster die een
  preset met `minQuality` in de auto meestuurt. De uitleg onder MuMa Voice noemt de
  ondergrens, niet de hele lijst lagen erboven.

<!-- release notes -->

- **"Speel flac hardstyle af" werkt.** Ook "in hoge kwaliteit" voor 320 kbps of beter, in de
  auto en in MuMa Voice.
