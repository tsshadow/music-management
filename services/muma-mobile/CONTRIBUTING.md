# Contributing

MuMa Mobile is developed inside the `music-management` repository. Issues and
merge requests live in [this project's
tracker](https://gitlab.example.com/muma/music-management/-/issues) —
the upstream Ultrasonic project it was forked from is discontinued, so nothing
is reported or merged there.

## Contributing Translations

Translations are plain `strings.xml` resources under
`app/src/main/res/values-*/`; edit them in a merge request. There is no
external translation platform.

## Contributing Code

By default, merge requests should be opened against the **develop** branch
from your own branch, MR against the **master** branch should only be used
for critical bug fixes.

### Here are a few guidelines you should follow before submitting:

1. **License Acceptance:** All contributions must be licensed as [GNU
   GPLv3](LICENSE) to be accepted. Use `git commit --signoff` to acknowledge
   this.
2. **No Breakage**: New features or changes to existing ones must not
   degrade the user experience.
3. **Coding standards**: best-practices should be followed, comment
   generously, and avoid "clever" algorithms. Refactoring existing messes is
   great, but watch out for breakage.
4. **No large PR**: Try to limit the scope of PR only to the related issue,
   so it will be easier to review and test.
5. **Make your own branch**: When you send us a merge request, please do it
   from your own branch. Avoid using the `develop` branch.

### Merge request process

On each merge request GitLab runs a number of checks to make sure there are
no problems.

Take special note of point five of the previous paragraph. Do not use the
`develop` branch, make your own. Not following this step will cause your
merge request to be rejected without even checking it.

#### Signed commits

Commits must be signed. [See here how to set it
up](https://docs.gitlab.com/ee/user/project/repository/gpg_signed_commits/).

#### KtLint

This programm checks if the source code is formatted correctly. You can run
it yourself locally with
```
./gradlew -Pqc ktlintFormat
```
Running this command will fix common problems and will notify you of
problems it couldn't fix automatically.

#### Detekt

Detekt is a static analyser. It helps to find potential bugs in our code.
You can run it yourself locally with
```
./gradlew -Pqc detekt
```
There is no baseline: every finding fails the build. Fix what it reports; where a
finding is intentional, put a targeted `@Suppress("<Rule>")` on the declaration
with a comment saying why. The build still picks up a per-module
`detekt-baseline.xml` if one exists, but none should be added back.

#### Lint

Lint looks for general problems in the code or unused resources etc. You can
run it with
```
./gradlew -Pqc lintRelease
```
If there is a need to regenerate the baseline, remove
`app/lint-baseline.xml` and rerun the command.
