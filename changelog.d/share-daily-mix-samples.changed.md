- Internal: Klassiek, Zachter, Middenin and Harder now share one pair of day-stable library
  samples per listener instead of each drawing the same two (issue #138). The nightly
  feeds-refresh spent ~24 s of SQL per listener sampling the library four times for one answer;
  it now spends ~6 s. The mixes themselves are unchanged -- the same ids in the same order, reused
  in-process for up to ten minutes. The label mix keeps its own samples, since it filters on its
  label.
