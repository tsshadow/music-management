# MuMa Mobile

MuMa Mobile is the Android client of this Music Management suite: a music
streaming client for [Subsonic][subsonic] [API][subapi] (version 1.7.0 or
higher) compatible servers, pointed at this project's own
`music-management-server`.

It is a hard fork of the discontinued [Ultrasonic][ultrasonic] project and was
renamed once the two had diverged far enough that there was no upstream left to
merge from. Broadcast actions and notification channel IDs still carry the
historical `org.moire.ultrasonic` prefix on purpose — they are contracts held by
the Android system across an in-place upgrade, not names.

[ultrasonic]: https://gitlab.com/ultrasonic/ultrasonic

## What is in this module

Since 7.0.0 the app has no screens of its own: the user interface is the Svelte web player from
`services/frontend`, staged into the APK by the `prepareWebBundle` Gradle task and shown by
`CapacitorActivity`. This module is the native half -- the playback service, downloads and the
Room cache, Android Auto, car mode, voice, crash reports, the widget, and the Capacitor plugins
under `capacitor/` the web player talks to. The design and its decisions are in
`docs/designs/universal-ui/`.

## License

This software is licensed under the terms of the GNU General Public License
version 3 (GPLv3).

Full text of the license is available in the [LICENSE](LICENSE) file and
[online][gpl3].

## Android signing configuration

MuMa Mobile now shares a single upload key between local builds and GitHub
Actions. Configure the same credentials in both environments so that release
artifacts are interchangeable.

### Local development

Create or update `.env` (this file must never be committed) with the
location of your keystore and its credentials:

```
# Not tracked by Git – used only on your workstation
SIGNING_STORE_FILE=keystore.jks
SIGNING_STORE_PASSWORD=***replace***
SIGNING_KEY_ALIAS=***replace***
SIGNING_KEY_PASSWORD=***replace***
```

Place the referenced `keystore.jks` in the project root or adjust the path to
match your setup. You can generate a development keystore with
`./gradlew generateKeystore` when `keytool` is available on your PATH. Debug
builds will keep using the default Android Studio debug keystore until the
shared upload key is present, so you can still run the app before finishing the
signing setup.

### GitHub Actions

Add the following repository secrets under **Settings → Secrets and variables →
Actions** so the workflow can sign release artifacts automatically:

| Secret | Purpose |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | Base64-encoded contents of `keystore.jks` (`base64 -w0 keystore.jks`). |
| `ANDROID_KEYSTORE_PASSWORD` | Password protecting the keystore. |
| `ANDROID_KEY_ALIAS` | Alias of the signing key within the keystore. |
| `ANDROID_KEY_PASSWORD` | Password for the key alias. |

GitHub Actions will decode the keystore, reuse the same credentials as Android
Studio, and publish signed APK/AAB artifacts for every push, pull request, or
manual run.

## Building and Deployment
If you are modifying the code and need to rebuild and redeploy the system:

1.  **Install dependencies**: `./scripts/install.sh`
2.  **Build app**: `./scripts/build.sh [debug|release]` (defaults to debug)
3.  **Publish app & hoster**: `./scripts/publish.sh [debug|release]` (defaults to debug)
4.  **Deploy to remote**: `./scripts/deploy.sh [debug|release]` (defaults to debug)
5.  **Full pipeline (Build + Publish + Deploy)**: `./install` or `./install.sh [debug|release]` (defaults to debug)
    - Use `patch`, `minor`, or `major` as mode for version increments (e.g., `./install patch`).

### Server address and Google sign-in

The APK does not carry a server in its source. `app/build.gradle` compiles four values into
`BuildConfig` from a Gradle property, or from an environment variable when the property is absent:

| Gradle property | Environment | Default | Effect |
| --- | --- | --- | --- |
| `muma.serverUrl` | `MUMA_SERVER_URL` | `https://music.example.org` | The address a fresh install suggests on its first-run screen, and the host `muma.apiUrl` belongs to. The listener types the server the app talks to; the example default suggests nothing (issue #192). |
| `muma.googleClientId` | `MUMA_GOOGLE_CLIENT_ID` | empty | The Google OAuth Web client id of "Sign in with Google". Empty hides the button. |
| `muma.apiUrl` | `MUMA_API_URL` | empty | Own host for the MuMa API. Empty means `<server>/muma`. |
| `muma.ownDomain` | `MUMA_OWN_DOMAIN` | empty | The owner's domain. A stored server whose host equals the server's host, the domain, or ends in `.<domain>` gets `muma.apiUrl`. Empty means exact host match only. |

Locally: export the environment variables, or put the properties in `~/.gradle/gradle.properties`.
Do not pass them with `-P` on the command line: the value then shows in the process list of a
shared runner (bug report 125). In CI they are CI/CD variables with the same names. Values are
checked (a URL, and letters, digits, `.`, `_`, `-` for the client id), so a quote cannot break the
generated code.

A release (`assembleRelease`, `bundleRelease`, `packageRelease`) fails in Gradle when the server is
the example default or the client id is empty, and `scripts/ci/muma-mobile-build-upload.sh release`
stops earlier for the same reason. `MUMA_ALLOW_DEFAULTS=true` lifts the Gradle check for a build that
is never shipped; `mobile:smoke` sets it and expects the server from `MUMA_SERVER_URL` prefilled on the
first-run screen. `./scripts/test/muma-mobile-config-check.sh` runs the cases in the Android image.

### Release-build smoke test
The shipped APK is R8-minified (`app/minify/*.pro`), and a missing keep rule only fails in that
build -- the 6.21.0 startup crash (`docs/bug-reports/029`) was invisible to every unit test.
`./scripts/test/muma-mobile-emulator-smoke.sh` (CI job `mobile:smoke`, which gates
`mobile:build-release`) builds the release variant with a throwaway keystore, starts it twice on a
headless emulator and checks that it survives, that `CapacitorActivity` is resumed, and that the
first-run screen shows the build's suggested server, which only arrives through Capacitor plugin
calls. Needs
`/dev/kvm`; run it locally after touching a keep rule. Details in `docs/testing-inventory.md`.

### APK Hoster
The `apk-hoster` service is managed in its own repository: a separate `apk-hoster` repository.
Builds from this project are automatically synced to the hoster's storage if configured in `.env`.

#### Distribution and Custom Paths
You can configure where builds are saved and how they are served:
- `DIST_DIR`: Local path where APKs and `index.html` are saved (e.g., `/mnt/user/ultrasonic-builds`).
- `REMOTE_DIST_PATH`: Path on the remote server where builds are located.
- `BUILDS_MOUNT`: Mount of the builds share, default `/mnt/$USER`; `REMOTE_DIST_PATH` and the local fallback live under it.

#### Remote Deployment Options
You can configure deployment in `.env`:
1.  **Portainer Webhook**: Set `PORTAINER_WEBHOOK_URL`. This can be used to notify other services of a new build.
2.  **SSH**: Set `REMOTE_HOST`, `REMOTE_USER`, etc. The script will automatically sync your APKs to the remote server using `scp`.

#### APK Hoster API
The `apk-hoster` service provides the following endpoints:
- `GET /api/version?apk=ultrasonic`: Returns JSON with the latest version info.
- `POST /api/add-apk`: Upload a new APK file.
    - Fields: `apk` (file), `release_notes` (text, optional), `password` (text, optional).
    - Headers: `X-Upload-Password` (optional alternative to `password` field).
    - Configuration: Set `UPLOAD_PASSWORD` and `ALLOWED_IPS` (comma-separated) in `.env` to secure this endpoint.

**Tip**: Use `DEPLOY_TARGET_NAME` in `.env` to give your deployment target a friendly name which will be displayed during the deployment process. The system now uses this to automatically manage stack naming and discovery across different repositories.

[subsonic]: http://www.subsonic.org/
[subapi]: http://www.subsonic.org/pages/api.jsp
[airsonic]: https://github.com/airsonic-advanced/airsonic-advanced
[supysonic]: https://github.com/spl0k/supysonic
[ampache]: https://ampache.org/
[gpl3]: https://opensource.org/licenses/gpl-3.0.html
