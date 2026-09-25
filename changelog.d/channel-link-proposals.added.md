- **Channels get a proposed label or artist.** Since 0.70.0 every SoundCloud and YouTube channel is
  its own row in the database, but none pointed at a label or an artist. Beheer -> Downloaders ->
  **Koppelingen** now compares every channel name with the known labels and the approved artists
  (case, accents and punctuation ignored; an alias or a redirect from artist curation counts too) and
  proposes only exact equality. Confirming records the link, rejecting does so for good. Measured on
  production: roughly 860 of the 1.376 channels get a proposal, 18 are skipped as ambiguous. The
  Volledigheid table shows the linked label or artist in a new "Gekoppeld aan" column, with a
  "voorstel" marker where one is still open. New table `channel_link_proposals` (`migrate_v40`), new
  endpoints under `/api/channel-links`; the coverage response gained an additive `channel` per account.
- **The Volledigheid table showed no last download for any SoundCloud channel.** The archive files a
  SoundCloud download under the numeric `soundcloud_id` (157.887 of 157.888 rows); the page looked it
  up by account name and never found it, so all 1.113 accounts read "onbekend". Now by id (bug
  report 087).
<!-- release notes -->
- Beheer -> Downloaders -> Koppelingen proposes which label or artist a channel is; confirm or reject
  per channel. The Volledigheid table shows the link.
- The Volledigheid table shows the last download of SoundCloud channels again.
