- **Eén LMS-thread gaf op alles 500 zodra de app opnieuw geopend werd.** `getSong`, `stream`,
  `scrobble`, `getMemories` — alles wat op die thread landde faalde met `Stale object,
  auth_token`, tot een herstart. Dbo bewaart objecten per sessie en de sessie is per thread:
  thread A hield jouw token op versie N, thread B stempelde `last_used` naar N+1, en de
  volgende bump van A schreef op zijn oude kopie. De `catch` in `processAuthToken` ving dat
  niet — de flush zit in `~WriteTransaction`, buiten elke catch — en het vuile object bleef in
  de sessie hangen, zodat elke latere write-transactie op die thread hem opnieuw flushte. Nu
  wordt het token vóór de bump opnieuw gelezen (onder de write-lock), expliciet geflusht
  binnen de try, en bij een stale write weggegooid.

<!-- release notes -->

- **De app opnieuw openen leverde soms lege lijsten en foutmeldingen op** — een serverthread
  bleef na een race op je login-token elke aanvraag afwijzen. Opgelost.
