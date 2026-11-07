-- radio_stations: the Dutch stations added in November 2026.
--
-- A database that has none of these slugs gets them once (an anti-join). After that this file does
-- nothing, so a station a curator removes stays removed. The sort order starts at 110, so SLAM,
-- Q-dance and 538 of the first seed stay at the top. Every address was measured on 2026-11-07:
-- https, audio, and a CORS header for the web player.

INSERT INTO radio_stations (slug, name, stream_url, sort_order)
SELECT s.slug, s.name, s.stream_url, s.sort_order
FROM (
    SELECT '100-nl' AS slug, '100%NL' AS name, 'https://stream.100p.nl/100pctnl.mp3' AS stream_url, 110 AS sort_order
    UNION ALL SELECT '100-nl-non-stop', '100%NL Non-Stop', 'https://stream.100p.nl/web02_mp3', 120
    UNION ALL SELECT '100-nl-feest', '100%NL Feest', 'https://stream.100p.nl/web01_mp3', 130
    UNION ALL SELECT '100-nl-90s-00s', '100%NL 90''s & 00''s', 'https://stream.100p.nl/web04_mp3', 140
    UNION ALL SELECT '538-90s', '538 90''s', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR21.mp3', 160
    UNION ALL SELECT '538-greatest-hits', '538 Greatest Hits', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR08.mp3', 170
    UNION ALL SELECT '538-ibiza', '538 Ibiza', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR19.mp3', 180
    UNION ALL SELECT '538-non-stop', '538 Non-Stop', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR09.mp3', 190
    UNION ALL SELECT '538-ochtendshow', '538 Ochtendshow', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR29.mp3', 200
    UNION ALL SELECT '538-zomer', '538 Zomer', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR06.mp3', 210
    UNION ALL SELECT '538-tomorrowland', '538 Tomorrowland One World Radio', 'https://playerservices.streamtheworld.com/api/livestream-redirect/OWR_WORLD_RADIO_NL.mp3', 220
    UNION ALL SELECT 'arrow-classic-rock', 'Arrow Classic Rock', 'https://stream.player.arrow.nl/arrow', 230
    UNION ALL SELECT 'arrow-bluesbox', 'Arrow Bluesbox', 'https://playerservices.streamtheworld.com/api/livestream-redirect/ARROWBLUESBOX.mp3', 240
    UNION ALL SELECT 'bnr', 'BNR Nieuwsradio', 'https://playerservices.streamtheworld.com/api/livestream-redirect/BNR_NIEUWSRADIO.mp3', 250
    UNION ALL SELECT 'bnr-business-beats', 'BNR Business Beats', 'https://playerservices.streamtheworld.com/api/livestream-redirect/BNR_BUSINESS_BEATS.mp3', 260
    UNION ALL SELECT 'candlelight', 'Candlelight Radio', 'https://playerservices.streamtheworld.com/api/livestream-redirect/CANDLELIGHT.mp3', 270
    UNION ALL SELECT 'classicnl', 'ClassicNL', 'https://classic.nl/streams/?s=main', 280
    UNION ALL SELECT 'decibel', 'Radio Decibel', 'https://playerservices.streamtheworld.com/api/livestream-redirect/RADIODECIBEL.mp3', 290
    UNION ALL SELECT 'efteling-kids', 'Efteling Kids Radio', 'https://media.hostin.live/audio/efteling.mp3', 300
    UNION ALL SELECT 'funx', 'NPO FunX', 'https://icecast.omroep.nl/funx-bb-mp3', 310
    UNION ALL SELECT 'gpr-sportradio', 'GPR Sportradio', 'https://playerservices.streamtheworld.com/api/livestream-redirect/GRAND_PRIX_RADIO.mp3', 320
    UNION ALL SELECT 'joe', 'Joe', 'https://stream.joe.nl/joe/mp3', 330
    UNION ALL SELECT 'joe-non-stop', 'Joe Non-Stop', 'https://stream.joe.nl/nonstop/mp3', 340
    UNION ALL SELECT 'kink', 'KINK', 'https://playerservices.streamtheworld.com/api/livestream-redirect/KINK.mp3', 350
    UNION ALL SELECT 'npo-radio-1', 'NPO Radio 1', 'https://icecast.omroep.nl/radio1-bb-mp3', 360
    UNION ALL SELECT 'npo-radio-2', 'NPO Radio 2', 'https://icecast.omroep.nl/radio2-bb-mp3', 370
    UNION ALL SELECT 'npo-3fm', 'NPO 3FM', 'https://icecast.omroep.nl/3fm-bb-mp3', 380
    UNION ALL SELECT 'npo-blend', 'NPO Blend', 'https://icecast.omroep.nl/npoblend-bb-mp3', 390
    UNION ALL SELECT 'npo-klassiek', 'NPO Klassiek', 'https://icecast.omroep.nl/radio4-bb-mp3', 400
    UNION ALL SELECT 'npo-radio-5', 'NPO Radio 5', 'https://icecast.omroep.nl/radio5-bb-mp3', 410
    UNION ALL SELECT 'npo-sterren-nl', 'NPO Sterren NL', 'https://icecast.omroep.nl/radio2-sterrennl-mp3', 420
    UNION ALL SELECT 'qmusic', 'Qmusic', 'https://stream.qmusic.nl/qmusic/mp3', 440
    UNION ALL SELECT 'qmusic-foute-uur', 'Qmusic Foute Uur', 'https://stream.qmusic.nl/fouteuur/mp3', 450
    UNION ALL SELECT 'qmusic-non-stop', 'Qmusic Non-Stop', 'https://stream.qmusic.nl/nonstop/mp3', 460
    UNION ALL SELECT 'qmusic-90s-00s', 'Qmusic 90''s & 00''s', 'https://stream.qmusic.nl/90s-00s/mp3', 470
    UNION ALL SELECT 'qmusic-easy', 'Qmusic Easy', 'https://stream.qmusic.nl/easy/mp3', 480
    UNION ALL SELECT 'qmusic-top-40', 'Qmusic Top 40', 'https://stream.qmusic.nl/top40/mp3', 490
    UNION ALL SELECT 'radio-10', 'Radio 10', 'https://playerservices.streamtheworld.com/api/livestream-redirect/RADIO10.mp3', 500
    UNION ALL SELECT 'radio-10-non-stop', 'Radio 10 Non-Stop', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR15.mp3', 510
    UNION ALL SELECT 'radio-10-60s-70s', 'Radio 10 60''s & 70''s', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR18.mp3', 520
    UNION ALL SELECT 'radio-10-80s', 'Radio 10 80''s', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR20.mp3', 530
    UNION ALL SELECT 'radio-10-90s', 'Radio 10 90''s', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR22.mp3', 540
    UNION ALL SELECT 'radio-10-disco', 'Radio 10 Disco Classics', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR23.mp3', 550
    UNION ALL SELECT 'radio-10-soul-jazz', 'Radio 10 Soul & Jazz', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR04.mp3', 560
    UNION ALL SELECT 'radio-10-top-4000', 'Radio 10 Top 4000', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR24.mp3', 570
    UNION ALL SELECT 'radio-noordzee', 'Radio Noordzee', 'https://playerservices.streamtheworld.com/api/livestream-redirect/TLPSTR17.mp3', 580
    UNION ALL SELECT 'sky-radio', 'Sky Radio', 'https://playerservices.streamtheworld.com/api/livestream-redirect/SKYRADIO.mp3', 590
    UNION ALL SELECT 'sky-radio-hits', 'Sky Radio Hits', 'https://playerservices.streamtheworld.com/api/livestream-redirect/SRGSTR01.mp3', 600
    UNION ALL SELECT 'sky-radio-work', 'Sky Radio Non-Stop@Work', 'https://playerservices.streamtheworld.com/api/livestream-redirect/SRGSTR24.mp3', 610
    UNION ALL SELECT 'sky-radio-christmas', 'Sky Radio Christmas', 'https://playerservices.streamtheworld.com/api/livestream-redirect/SRGSTR08.mp3', 620
    UNION ALL SELECT 'sky-radio-00s-10s', 'Sky Radio 00''s & 10''s', 'https://playerservices.streamtheworld.com/api/livestream-redirect/SRGSTR05.mp3', 630
    UNION ALL SELECT 'sky-radio-smooth-hits', 'Sky Radio Smooth Hits', 'https://playerservices.streamtheworld.com/api/livestream-redirect/SRGSTR15.mp3', 640
    UNION ALL SELECT 'sky-radio-love-songs', 'Sky Radio Love Songs', 'https://playerservices.streamtheworld.com/api/livestream-redirect/SRGSTR03.mp3', 650
    UNION ALL SELECT 'slam-boom-room', 'SLAM The Boom Room', 'https://stream.slam.nl/web12_mp3', 670
    UNION ALL SELECT 'slam-housuh', 'SLAM Housuh in de Pauzuh', 'https://stream.slam.nl/web16_mp3', 680
    UNION ALL SELECT 'slam-mix-marathon', 'SLAM Mix Marathon', 'https://stream.slam.nl/web13_mp3', 690
    UNION ALL SELECT 'slam-non-stop', 'SLAM Non-Stop', 'https://stream.slam.nl/web10_mp3', 700
    UNION ALL SELECT 'soul-radio', 'Soul Radio', 'https://playerservices.streamtheworld.com/api/livestream-redirect/SOULRADIO.mp3', 710
    UNION ALL SELECT 'sublime', 'Sublime', 'https://playerservices.streamtheworld.com/api/livestream-redirect/SUBLIME.mp3', 720
    UNION ALL SELECT 'veronica', 'Radio Veronica', 'https://playerservices.streamtheworld.com/api/livestream-redirect/VERONICA.mp3', 730
    UNION ALL SELECT 'veronica-80s', 'Veronica De Beste 80s', 'https://stream.radioveronica.nl/dab01_mp3', 740
    UNION ALL SELECT 'veronica-90s', 'Veronica De Beste 90s', 'https://stream.radioveronica.nl/dab02_mp3', 750
    UNION ALL SELECT 'veronica-rock', 'Veronica Rock', 'https://stream.radioveronica.nl/web07_mp3', 760
    UNION ALL SELECT 'veronica-top-3000', 'Veronica Top 3000 Allertijden', 'https://stream.radioveronica.nl/web06_mp3', 770
) AS s
LEFT JOIN (
    SELECT slug FROM radio_stations
    WHERE slug IN (
        '100-nl',
        '100-nl-non-stop',
        '100-nl-feest',
        '100-nl-90s-00s',
        '538-90s',
        '538-greatest-hits',
        '538-ibiza',
        '538-non-stop',
        '538-ochtendshow',
        '538-zomer',
        '538-tomorrowland',
        'arrow-classic-rock',
        'arrow-bluesbox',
        'bnr',
        'bnr-business-beats',
        'candlelight',
        'classicnl',
        'decibel',
        'efteling-kids',
        'funx',
        'gpr-sportradio',
        'joe',
        'joe-non-stop',
        'kink',
        'npo-radio-1',
        'npo-radio-2',
        'npo-3fm',
        'npo-blend',
        'npo-klassiek',
        'npo-radio-5',
        'npo-sterren-nl',
        'qmusic',
        'qmusic-foute-uur',
        'qmusic-non-stop',
        'qmusic-90s-00s',
        'qmusic-easy',
        'qmusic-top-40',
        'radio-10',
        'radio-10-non-stop',
        'radio-10-60s-70s',
        'radio-10-80s',
        'radio-10-90s',
        'radio-10-disco',
        'radio-10-soul-jazz',
        'radio-10-top-4000',
        'radio-noordzee',
        'sky-radio',
        'sky-radio-hits',
        'sky-radio-work',
        'sky-radio-christmas',
        'sky-radio-00s-10s',
        'sky-radio-smooth-hits',
        'sky-radio-love-songs',
        'slam-boom-room',
        'slam-housuh',
        'slam-mix-marathon',
        'slam-non-stop',
        'soul-radio',
        'sublime',
        'veronica',
        'veronica-80s',
        'veronica-90s',
        'veronica-rock',
        'veronica-top-3000'
    )
    LIMIT 1
) AS existing ON 1 = 1
WHERE existing.slug IS NULL;
