- **Android Auto still showed only play, previous and next.** The icon constants of 7.4.1 did not
  bring the rating, shuffle, repeat and news buttons back. The buttons now go out as media button
  preferences with an explicit overflow slot instead of the deprecated custom layout, which also
  gives the car the previous/next slot reservations it documents; the placeholder button that
  used to hold the "next" slot is gone. When the car connects, the app logs exactly which buttons
  the car was handed, so a diagnostics report after one drive settles it if they still do not
  appear. Bug report 057.

<!-- release notes -->

- **Android Auto:** another attempt at bringing the rating, shuffle, repeat and news buttons back
  to the car's player screen. If they are still missing, send a diagnostics report after the drive.
