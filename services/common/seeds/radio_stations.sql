-- radio_stations: the live stations a new database starts with (issue #213).
--
-- Only when the table is empty. INSERT IGNORE would bring back a station a curator removed, on
-- each start. The addresses are StreamTheWorld's, because the redirect of stream.slam.nl has no
-- CORS header and the web player needs one.

INSERT INTO radio_stations (slug, name, stream_url, sort_order)
SELECT s.slug, s.name, s.stream_url, s.sort_order
FROM (
    SELECT 'slam' AS slug, 'SLAM' AS name,
           'https://playerservices.streamtheworld.com/api/livestream-redirect/SLAM_MP3.mp3' AS stream_url,
           10 AS sort_order
    UNION ALL
    SELECT 'q-dance', 'Q-dance',
           'https://playerservices.streamtheworld.com/api/livestream-redirect/Q_DANCE.mp3', 20
    UNION ALL
    SELECT '538', '538',
           'https://playerservices.streamtheworld.com/api/livestream-redirect/RADIO538.mp3', 30
) AS s
LEFT JOIN (SELECT slug FROM radio_stations LIMIT 1) AS existing ON 1 = 1
WHERE existing.slug IS NULL;
