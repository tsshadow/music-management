/**
 * A Wrapped payload with every card `ok`, in the shape `services/music_manager/wrapped/` sends.
 * Shared by the Wrapped tests. Names are placeholders.
 */

/** A track reference as the payload carries it. */
export function track(id, title, artist, extra = {}) {
  return {
    track_id: id,
    title,
    artist,
    file_path: `/mnt/music/Labels/${title}.flac`,
    library_path: `Labels/${title}.flac`,
    ...extra,
  };
}

const ok = (id, data, basis = null) => ({ id, status: "ok", reason: null, basis, data });

/** Every card of both tabs, each with data that fills its face. */
export const ALL_CARDS = [
  ok("title", {
    listens: 12000,
    linked: 9000,
    unmatched: 3000,
    distinct_tracks: 2100,
    estimated_secs: 2_000_000,
    listeners: 4,
  }),
  ok("listening_time", {
    measured_secs: 3600 * 20,
    imputed_secs: 3600 * 500,
    estimated_secs: 3600 * 520,
    measured_share: 0.04,
  }),
  ok("listeners", { active: 3, former: 1 }),
  ok(
    "top_tracks",
    {
      tracks: [
        { ...track(1, "Track One", "Artist A"), listens: 50 },
        { ...track(2, "Track Two", "Artist B"), listens: 40 },
        { ...track(3, "Track Three", null), listens: 30 },
      ],
      unmatched: 3000,
    },
    { counted: 9000, of: 12000, unit: "listens" },
  ),
  ok("top_artists", {
    artists: [{ artist_id: 7, artist: "Artist A", listens: 300 }],
    unmatched: 0,
  }),
  ok("top_genres", {
    genres: [
      { genre: "Hardcore", listens: 900 },
      { genre: "Uptempo", listens: 500 },
    ],
    untagged: 10,
    unmatched: 0,
  }),
  ok("seasons", {
    seasons: [{ season: "winter", genre: "Hardcore", listens: 300, tagged: 400 }],
    unmatched: 0,
  }),
  ok("top_label", {
    top: { name: "Label X", tracks: 30, label_id: 3, listens: 200 },
    runners_up: [{ name: "Label Y", tracks: 5, label_id: 4, listens: 50 }],
    unmatched: 0,
  }),
  ok("top_channel", {
    top: {
      platform: "youtube",
      name: "Channel Z",
      label: null,
      artist: null,
      channel_id: 1,
      listens: 80,
    },
    runners_up: [{ platform: "soundcloud", name: "Cloud Q", listens: 20 }],
    unmatched: 0,
  }),
  ok("top_remixer", {
    top: { name: "Remixer R", remixer: "Remixer R", listens: 12 },
    runners_up: [],
    unmatched: 0,
  }),
  ok("festival", {
    top: {
      name: "Fest F",
      secs: 36000,
      estimated: false,
      editions: [2024, 2025],
      festival: "Fest F",
      listens: 15,
    },
    runners_up: [],
    unmatched: 0,
  }),
  ok("time_travel", {
    oldest: { festival: "Fest F", year: 2009 },
    newest: { festival: "Fest G", year: 2025 },
    editions: 7,
    unmatched: 0,
  }),
  ok("show", {
    top: { name: "Show S", secs: 7200, show: "Show S", listens: 4 },
    runners_up: [],
    unmatched: 0,
  }),
  ok("forms", {
    forms: [
      { form: "track", listens: 800 },
      { form: "set", listens: 100 },
    ],
    unmatched: 0,
  }),
  ok("bpm", {
    average: 162.4,
    months: [
      { month: "2026-01", average: 160 },
      { month: "2026-02", average: 170 },
    ],
    unmatched: 0,
  }),
  ok("bpm_extremes", {
    fastest: { ...track(4, "Fast One", "Artist F"), bpm: 250 },
    slowest: { ...track(5, "Slow One", "Artist S"), bpm: 70 },
    unmatched: 0,
  }),
  ok("taste_vs_shelf", {
    buckets: [
      { bpm: 150, listens_share: 0.2, shelf_share: 0.4 },
      { bpm: 170, listens_share: 0.6, shelf_share: 0.1 },
    ],
    unmatched: 0,
  }),
  ok("clock", {
    hours: Array.from({ length: 24 }, (_, h) => (h === 22 ? 90 : h)),
    weekdays: [1, 2, 3, 4, 50, 6, 7],
  }),
  ok("heatmap", {
    matrix: Array.from({ length: 7 }, (_, d) =>
      Array.from({ length: 24 }, (_, h) => (d === 5 && h === 23 ? 99 : 1)),
    ),
  }),
  ok("night_shift", { listens: 200, share: 0.25 }),
  ok("busiest_day", { date: "2026-03-14", listens: 140 }),
  ok("first_last", {
    first: { at: "2026-01-01T00:05:00", linked: true, ...track(6, "First Song", "Artist A") },
    last: { at: "2026-11-10T22:00:00", linked: true, ...track(7, "Last Song", "Artist B") },
  }),
  ok("months", {
    months: [
      { month: "2026-01", linked: 100, unmatched: 20 },
      { month: "2026-02", linked: 300, unmatched: 0 },
    ],
  }),
  ok("streak", { days: 41, first: "2026-02-01", last: "2026-03-13" }),
  ok("session", {
    start: "2026-04-01T20:00:00",
    end: "2026-04-02T03:00:00",
    listens: 60,
    duration_secs: 25200,
  }),
  ok("origins", {
    origins: [
      { origin: "phone", listens: 500, measured_secs: 100 },
      { origin: "car", listens: 100, measured_secs: 0 },
    ],
    car_secs: 7200,
  }),
  ok("release_years", {
    oldest: { ...track(8, "Old Song", "Artist O"), year: 1993 },
    newest: { ...track(9, "New Song", "Artist N"), year: 2026 },
    decades: [
      { decade: 1990, listens: 10 },
      { decade: 2020, listens: 90 },
    ],
    unknown: 0,
    unmatched: 0,
  }),
  ok("fresh_vs_stock", { fresh: 400, known: 1000, share: 0.4 }),
  ok("long_wait", {
    ...track(10, "Waiting Song", "Artist W"),
    arrived_at: "2020-01-01",
    first_play: "2026-01-01",
    wait_secs: 6 * 365 * 86400,
  }),
  ok("impulse", { median_secs: 5400, tracks: 30 }),
  ok("untouched", { played: 2100, library: 50000, share: 0.042, unmatched: 0 }),
  ok("new_genres", { genres: [{ genre: "Frenchcore", listens: 30 }], count: 1 }),
  ok("discovery", {
    artist_id: 8,
    artist: "Artist D",
    listens: 45,
    first_listen: "2026-05-01",
    unmatched: 0,
  }),
  ok("loyal", { artist_id: 9, artist: "Artist L", months: 11, listens: 99 }),
  ok("one_hit", { artist_id: 10, artist: "Artist H", date: "2026-06-06", listens: 12 }),
  ok("ratings", {
    given: 120,
    stars: [
      { stars: 5, count: 40 },
      { stars: 4, count: 80 },
    ],
    five_star_play_share: 0.3,
    rebuilt_before_period: true,
  }),
  ok("contradiction", { ...track(11, "Guilty Song", "Artist G"), rating: 1, listens: 25 }),
  ok("word", { word: "night", count: 31, runners_up: [{ word: "power", count: 20 }] }),
  ok("unidentified", { listens: 3000, distinct: 900 }),
  ok("only_you", {
    track: { ...track(12, "Mine Alone", "Artist M"), listens: 9 },
    only_you: 300,
    shared_tracks: 1800,
    tracks: 2100,
  }),
  ok("most_shared", { ...track(13, "Shared Song", "Artist S"), listeners: 3 }),
  ok("festival_editions", { sets: 40, festivals: [{ festival: "Fest F", sets: 25 }] }),
  ok("releases_of_year", { tracks: 300, labels: [{ label_id: 3, label: "Label X", tracks: 120 }] }),
  ok("downloads", {
    total: 800,
    months: [{ month: "2026-01", soundcloud: 30, youtube: 10 }],
    top_channel: { platform: "soundcloud", channel: "Cloud Q", downloads: 90 },
    undated: 5,
  }),
  ok("growth", {
    tracks: 1200,
    sources: [
      { source: "label", tracks: 800 },
      { source: "youtube", tracks: 400 },
    ],
    unknown_arrival: 30,
  }),
  ok("shelf", {
    buckets: [
      { bpm: 150, tracks: 10 },
      { bpm: 170, tracks: 90 },
    ],
    genres: [{ genre: "Hardcore", tracks: 400 }],
  }),
  ok("start_now", { total_secs: 3 * 365 * 86400, finish: "2029-11-12" }),
  ok("unplayed", { unplayed: 30000, library: 50000, share: 0.6 }),
  ok("system", { bpm_measured: 40000, bulletins: 300, ratings: 1200, criticals: 2 }),
];

/** A full payload around a list of cards. */
export function payloadWith(cards, extra = {}) {
  return {
    scope: "user",
    format: 2,
    tz: "Europe/Amsterdam",
    period: {
      key: "2026",
      from: "2026-01-01",
      to: "2026-12-31",
      year: 2026,
      running: true,
      data_until: "2026-11-12",
    },
    generated_at: "2026-11-12T10:00:00",
    coverage: {
      listens: 12000,
      linked: 9000,
      unmatched: 3000,
      measured_share: 0.04,
      origin_known_share: 0.8,
      bpm_share: 0.7,
      release_year_share: 0.5,
      arrival_share: null,
      left_out: [
        { id: "top_remixer", status: "blocked", reason: "no_remixer_credits" },
        { id: "streak", status: "below_minimum", reason: null },
      ],
    },
    cards,
    ...extra,
  };
}
