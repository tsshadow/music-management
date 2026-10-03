- **The release-date backfill read month-first .nfo dates day-first.** `release_date_backfill`
  ignored `rules_scene_group_date_format`, which the tagger rule obeys. For the 29 groups that write
  month-first (OMA, PUTA, BC, NBD and others) its dry run took `Rip.date: 05.09.2022` for
  5 September. The rule and Deezer agree on 9 May. A correct date therefore looked like a person's,
  and a date stored day-first before the table existed looked like the rule's own. On production
  that made 765 swapped files in 120 releases look correct. The backfill now reads the dates the
  way the rule does.
