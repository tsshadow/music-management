- **The app asks which server it talks to.** A fresh install opens on a screen that asks for the
  address of your MuMa server, checks it, and only then shows the login page. Type
  `music.example.net` and the app makes it `https://music.example.net`; only `https` is accepted,
  also on a home network. The check tells you what is wrong: no network, nothing answers, an
  untrusted certificate, no music server at that address, or a music server without MuMa behind it,
  where "Toch doorgaan" stores the address anyway. A build made for one server suggests that server
  on the screen; a build with the example default suggests nothing (#192).
- **Change the server later.** The login page shows the server's host with "Wijzigen", and Settings
  > Apparaat starts with a "Server" row. A change to another server asks first, signs you out and
  clears the cached library; a change in spelling only keeps the session (#192).
- **Updating keeps your server and your session.** An install that was already used gets the
  server it used stored once, so the update shows no new screen. "Sign in with Google" shows only
  for the server the app was built for (#192).

<!-- release notes -->

- Bij de eerste start vraagt de app het adres van je MuMa-server en controleert het.
- Op het inlogscherm en in Instellingen > Apparaat kun je de server wijzigen.
- Na de update blijf je gewoon ingelogd op je eigen server.
