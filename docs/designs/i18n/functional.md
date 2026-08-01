# Frontend Internationalisation (i18n) — Functional Design

## Overview

The Svelte web frontend (`services/frontend`) currently has every piece of interface text hardcoded in the
components themselves, in a mix of Dutch and English. There is no way for a user to pick a language, and no
way for a developer to add one.

This feature introduces the translation mechanism and the user-facing language setting. It is deliberately
scoped to the plumbing: the translation files, the lookup mechanism, the language picker in Settings, and
the synchronisation of the chosen language to the user's account. Translating the existing screens is a
separate, incremental follow-up — after this lands, converting a screen is a mechanical change with no
further design work.

The two languages shipped are English and Dutch. The chosen language follows the user across devices and
browsers, in the same way their favourite genres already do.

## User Stories

- As a user, I want to choose the language the interface is shown in, so that I can use the application in
  the language I am most comfortable with.
- As a user, I want the language I picked to still apply when I log in from another device or browser, so
  that I do not have to set it again everywhere.
- As a new user, I want the interface to start in my browser's language when it is one we support, so that
  the application is usable before I have visited the settings at all.
- As a developer, I want a single documented place to add interface text, so that new screens are
  translatable by default instead of accumulating more hardcoded strings.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A visitor opens the application for the first time, browser set to Dutch | Interface language is Dutch |
| A visitor opens the application for the first time, browser set to French (unsupported) | Interface language is English |
| A user picks a language in Settings | Translated text switches immediately, without a page reload |
| A user picks a language, then reloads the page | The picked language is still active |
| A logged-in user picks a language, then logs in on another device | That device shows the same language |
| A logged-in user has a language on their account that differs from the one stored in this browser | The account's language wins |
| A user who set a language before logging in logs in for the first time | The language from this browser is adopted as their account language |
| A user logs out | The language reverts to this browser's own preference; the next person to use the browser does not inherit the previous user's account language |
| The account cannot be reached while saving the language | The language still changes locally; no error is shown to the user |
| Text has not been translated into the active language yet | The English text is shown rather than a blank or an error |

## Acceptance Criteria

1. Settings contains a language control offering English and Dutch, each written in its own language
   ("English", "Nederlands").
2. Choosing a language updates the translated text on screen immediately, with no page reload.
3. The chosen language survives a page reload in the same browser.
4. For a logged-in user, the chosen language is stored on their account and applied when they log in
   elsewhere.
5. On first visit with no stored preference, the browser's language is used when it is English or Dutch,
   and English otherwise.
6. Text that has no translation in the active language falls back to English, and never renders as a blank
   space, a raw key, or an error, for any text shipped with this feature.
7. A failure to reach the account while loading or saving the language never blocks or breaks the
   interface; the local preference continues to apply.
8. Logging out does not leave the previous user's account language applied to the browser.

## Open Questions / Not Yet Decided

- The order in which the existing screens are translated is not decided here, and is out of scope for this
  design. Existing hardcoded text (currently a mix of Dutch and English) is untouched by this change and
  keeps rendering exactly as it does today.
- Additional languages beyond English and Dutch are not planned yet. Adding one is intended to be a matter
  of adding a translation file and listing it, with no change to the mechanism.
