- **The app no longer accepts a server certificate it cannot check, and no longer keeps the API
  key in the old server table.** The trust-all TLS path behind `allowSelfSignedCertificate` is
  gone: the client always checks the certificate. On start the app blanks `apiKey` in the legacy
  `ServerSetting` table next to the password it already blanked; the key in use lives in the
  encrypted settings (#227).
<!-- release notes -->
- De app vertrouwt alleen nog een geldig servercertificaat, en de oude servertabel bewaart geen
  API-sleutel meer.
