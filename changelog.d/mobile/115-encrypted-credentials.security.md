- **The MuMa API key is now stored encrypted** (issue #115). Since #101 it is the one long-lived
  credential the app keeps -- permanent, a refresh does not rotate it -- and it sat in the plain
  preferences, which auto-backup copied and a rooted device could read. It and the Subsonic token
  are now sealed with AES-256-GCM under an Android Keystore key the app cannot read out, in a file
  excluded from auto-backup and device transfer. The deprecated `androidx.security:security-crypto`
  library is gone.
  - **After updating.** On first start -- also when Android Auto starts the app without the UI --
    the key moves into the encrypted store and the plain copy is removed. The old encrypted file is
    deleted, and the Subsonic token is fetched again once with the key. Nobody has to sign in again.
  - **Keystore trouble.** A Keystore key that was lost or invalidated, or a backup restored without
    the credentials, leaves the app signed out (the sign-in page; in the car "sign in again on your
    phone") instead of crashing.
<!-- release notes -->
- Your sign-in is now stored encrypted on the phone. After updating you stay signed in. If the
  phone's secure storage is ever reset, the app asks you to sign in again.
