- **"Sign in with Google" is back in the app.** It disappeared with the old Kotlin screens, and the
  web login that replaced them cannot use Google's web sign-in inside the app (Google blocks it in
  an embedded browser; the app's bundle never contained the button). The login page now shows a
  native "Inloggen met Google" button when the APK was built with the Google client ID; it opens
  Android's own account chooser (Credential Manager) and signs in through the same
  `/api/auth/google` as the website, access requests included. Downloads and Android Auto share the
  session afterwards. Needs the Android OAuth client for `nl.teunschriks.mumamobile` with the
  release certificate SHA-1 in Google Cloud Console (bug report 011). Bug report 106.

<!-- release notes -->

- **Inloggen met Google kan weer in de app.** Op het inlogscherm staat onder het wachtwoordformulier
  een knop "Inloggen met Google"; je kiest je Google-account in het venster van Android zelf.
