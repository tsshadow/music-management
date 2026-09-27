- **A channel link now changes the tags, and a channel the search found nothing for can be linked by
  hand** (issue #58, `docs/designs/channel-links/`). Until now a confirmed link between a
  SoundCloud/YouTube channel and its label or artist was only shown in the Volledigheid table. The
  tagger reads it now: a download from a linked channel gets the linked label as its publisher --
  which the library stores as the track's label, where it used to store none because the publisher
  was always the platform -- and the linked artist replaces the channel name wherever that name
  was only standing in for an artist because the title named nobody. An artist the title did name
  is never touched, a real label is never overwritten, and the linked label's genre rules apply as
  they do to a label release. Linking, confirming or unlinking queues the channel's files for the
  tagger (reason `channel_link`, served after decisions and new files). Beheer -> Downloaders ->
  Koppelingen gains a **Handmatig koppelen** panel: type part of a channel's name, pick label or
  artist, type part of that name (only approved artists and real labels are offered) and link; the
  Volledigheid table has a **koppelen** button on every channel with no link and no proposal. On
  production (2026-09-27) the 149 open label proposals cover 52.128 tracks, 50.449 of which have no
  label today; 515 channels with 77.171 tracks got no proposal at all and can only be linked by hand.
  New: `PUT /api/channel-links/channels/{id}/{kind}`, `GET /api/channel-links/channels` and
  `GET /api/channel-links/targets`; `confirm` and `unlink` responses gain `queued` (additive);
  `channel_link_proposals.source` gains `manual` (`migrate_v48`).
<!-- release notes -->
- A channel linked to its label or artist now puts that label and artist on its downloads, and a
  channel without a proposal can be linked by hand under Beheer -> Downloaders -> Koppelingen.
