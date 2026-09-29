import unittest

import pytest

from services.downloader.account_report import (
    BLANK,
    CLEAN,
    THROTTLED,
    UNAVAILABLE_TRACKS,
    AccountReport,
    classify_account,
    clean_message,
    detect_http_status,
    logged_level,
)

pytestmark = pytest.mark.mock_base('yt_dlp')


class DetectHttpStatusTest(unittest.TestCase):
    """The old check was `'403' in message`, which any track name could satisfy."""

    def test_a_forbidden_error_is_read_as_403(self):
        self.assertEqual(detect_http_status('ERROR: unable to download: HTTP Error 403: Forbidden'), 403)

    def test_a_too_many_requests_error_is_read_as_429(self):
        self.assertEqual(detect_http_status('HTTP Error 429: Too Many Requests'), 429)

    def test_a_bare_status_with_forbidden_is_recognised(self):
        self.assertEqual(detect_http_status('got 403 Forbidden from the api'), 403)

    def test_a_track_name_containing_the_number_is_not_a_status(self):
        self.assertIsNone(detect_http_status('[soundcloud] Downloading dj-403-live-set'))

    def test_a_byte_count_containing_the_number_is_not_a_status(self):
        self.assertIsNone(detect_http_status('[download] 403 bytes written'))

    def test_an_unrelated_message_has_no_status(self):
        self.assertIsNone(detect_http_status('[soundcloud] Extracting URL'))


class ClassifyAccountTest(unittest.TestCase):
    def test_an_account_with_no_trouble_is_clean(self):
        self.assertEqual(classify_account(extracted=12, forbidden=0, throttled=False), CLEAN)

    def test_a_429_outranks_everything_else(self):
        self.assertEqual(classify_account(extracted=12, forbidden=4, throttled=True), THROTTLED)

    def test_a_429_on_an_otherwise_empty_account_is_still_throttled(self):
        self.assertEqual(classify_account(extracted=0, forbidden=0, throttled=True), THROTTLED)

    def test_some_tracks_forbidden_among_extracted_ones_means_unavailable_tracks(self):
        self.assertEqual(classify_account(extracted=12, forbidden=3, throttled=False), UNAVAILABLE_TRACKS)

    def test_forbidden_with_nothing_extracted_is_blank(self):
        self.assertEqual(classify_account(extracted=0, forbidden=1, throttled=False), BLANK)

    def test_an_account_that_yielded_nothing_at_all_is_clean_not_blank(self):
        """An account whose tracks are all already archived extracts nothing and 403s nothing."""
        self.assertEqual(classify_account(extracted=0, forbidden=0, throttled=False), CLEAN)


class AccountReportTest(unittest.TestCase):
    def setUp(self):
        self.report = AccountReport()

    def test_a_fresh_report_is_clean(self):
        self.assertEqual(self.report.outcome, CLEAN)

    def test_an_error_line_with_a_403_records_a_forbidden_track(self):
        self.report.note_extracted('t1')
        self.report.error('ERROR: unable to download: HTTP Error 403: Forbidden')
        self.assertEqual(self.report.outcome, UNAVAILABLE_TRACKS)

    def test_the_forbidden_track_is_the_one_being_extracted(self):
        self.report.note_extracted('t1')
        self.report.error('HTTP Error 403: Forbidden')
        self.assertEqual(self.report.forbidden_tracks, ['t1'])

    def test_a_403_before_anything_was_extracted_leaves_the_account_blank(self):
        self.report.error('HTTP Error 403: Forbidden')
        self.assertEqual(self.report.outcome, BLANK)

    def test_a_blank_account_reports_no_track_to_remember(self):
        self.report.error('HTTP Error 403: Forbidden')
        self.assertEqual(self.report.forbidden_tracks, [])

    def test_a_429_in_a_warning_marks_the_report_throttled(self):
        self.report.warning('HTTP Error 429: Too Many Requests')
        self.assertEqual(self.report.outcome, THROTTLED)

    def test_a_track_name_with_the_number_does_not_trip_the_report(self):
        self.report.note_extracted('t1')
        self.report.error('ERROR: could not fetch dj-403-live-set')
        self.assertEqual(self.report.outcome, CLEAN)

    def test_each_forbidden_track_is_recorded_once(self):
        self.report.note_extracted('t1')
        self.report.error('HTTP Error 403: Forbidden')
        self.report.error('HTTP Error 403: Forbidden')
        self.assertEqual(self.report.forbidden_tracks, ['t1'])

    def test_later_tracks_are_attributed_to_themselves(self):
        self.report.note_extracted('t1')
        self.report.note_extracted('t2')
        self.report.error('HTTP Error 403: Forbidden')
        self.assertEqual(self.report.forbidden_tracks, ['t2'])


class NewestTimestampTest(unittest.TestCase):
    """The run's own answer to 'when did this account last upload?'."""

    def setUp(self):
        self.report = AccountReport()

    def test_a_report_that_saw_nothing_has_no_date(self):
        self.assertIsNone(self.report.newest_timestamp)

    def test_a_track_without_a_timestamp_leaves_it_unset(self):
        self.report.note_extracted('t1')
        self.assertIsNone(self.report.newest_timestamp)

    def test_the_newest_of_several_tracks_wins(self):
        self.report.note_extracted('t1', 1000)
        self.report.note_extracted('t2', 3000)
        self.report.note_extracted('t3', 2000)
        self.assertEqual(self.report.newest_timestamp, 3000)

    def test_a_track_without_a_timestamp_does_not_erase_a_known_one(self):
        self.report.note_extracted('t1', 3000)
        self.report.note_extracted('t2')
        self.assertEqual(self.report.newest_timestamp, 3000)


if __name__ == '__main__':
    unittest.main()


class YtDlpLineCleanupTest(unittest.TestCase):
    """yt-dlp's ``\\r`` left the event log titled ``root: ERROR: `` (bug report 130)."""

    LINE = "ERROR: \r[download] Got error: 4695519 bytes read, 5740658 more expected"

    def test_the_carriage_return_is_taken_out(self):
        self.assertEqual(
            'ERROR: [download] Got error: 4695519 bytes read, 5740658 more expected', clean_message(self.LINE)
        )

    def test_the_first_line_carries_the_failure(self):
        self.assertIn('Got error', clean_message(self.LINE).splitlines()[0])

    def test_a_real_line_break_is_kept(self):
        self.assertEqual('one\ntwo', clean_message('one\r\ntwo'))

    def test_the_logged_line_is_the_cleaned_one(self):
        with self.assertLogs(level='ERROR') as logs:
            AccountReport().error(self.LINE)

        self.assertEqual(
            ['ERROR:root:ERROR: [download] Got error: 4695519 bytes read, 5740658 more expected'], logs.output
        )

    def test_a_status_behind_a_carriage_return_is_still_counted(self):
        report = AccountReport()
        report.error('ERROR: \r[download] Got error: HTTP Error 429: Too Many Requests')

        self.assertTrue(report.throttled)


class BenignMessageTest(unittest.TestCase):
    """A short allowlist of expected yt-dlp lines is logged at INFO, not pushed as an alert."""

    def test_the_webm_to_mkv_notice_is_info(self):
        self.assertEqual(
            'info', logged_level('warning', "webm doesn't support embedding a thumbnail, mkv will be used")
        )

    def test_a_missing_soundcloud_stream_is_info(self):
        self.assertEqual('info', logged_level('warning', '[soundcloud] 2394393894: http_mp3 format not found'))
        self.assertEqual('info', logged_level('warning', '[soundcloud] 2394393894: hls_mp3 format not found'))

    def test_a_drm_refusal_is_info(self):
        self.assertEqual('info', logged_level('error', 'ERROR: [soundcloud] 2394393894: This video is DRM protected'))

    def test_an_unknown_warning_stays_a_warning(self):
        self.assertEqual('warning', logged_level('warning', 'Unable to download webpage: HTTP Error 404: Not Found'))

    def test_an_unknown_error_stays_an_error(self):
        self.assertEqual('error', logged_level('error', 'ERROR: [download] Got error: Read timed out.'))

    def test_a_debug_line_is_never_touched(self):
        self.assertEqual('debug', logged_level('debug', 'http_mp3 format not found'))

    def test_the_report_logs_a_benign_warning_at_info(self):
        with self.assertLogs(level='INFO') as logs:
            AccountReport().warning("webm doesn't support embedding a thumbnail, mkv will be used")

        self.assertEqual(["INFO:root:webm doesn't support embedding a thumbnail, mkv will be used"], logs.output)


class DrmTracksTest(unittest.TestCase):
    """A DRM refusal names the track, so the downloader can write it off."""

    def test_the_refused_track_is_recorded(self):
        report = AccountReport()
        report.error('ERROR: [soundcloud] 2394393894: This video is DRM protected')

        self.assertEqual(['2394393894'], report.drm_tracks)

    def test_each_track_is_recorded_once(self):
        report = AccountReport()
        report.error('ERROR: [soundcloud] 1: This video is DRM protected')
        report.error('ERROR: [soundcloud] 1: This video is DRM protected')
        report.error('ERROR: [soundcloud] 2: This video is DRM protected')

        self.assertEqual(['1', '2'], report.drm_tracks)

    def test_a_drm_refusal_is_not_a_forbidden_track(self):
        report = AccountReport()
        report.note_extracted('t1')
        report.error('ERROR: [soundcloud] 2394393894: This video is DRM protected')

        self.assertEqual(CLEAN, report.outcome)

    def test_an_info_line_mentioning_drm_records_nothing(self):
        report = AccountReport()
        report.info('[soundcloud] 1: This video is DRM protected')

        self.assertEqual([], report.drm_tracks)


class NoteListedTest(unittest.TestCase):
    def test_a_403_belongs_to_the_entry_being_extracted(self):
        report = AccountReport()
        report.note_extracted('t1')
        report.note_listed('t2')
        report.error('HTTP Error 403: Forbidden')

        self.assertEqual(['t2'], report.forbidden_tracks)

    def test_listing_an_entry_does_not_count_as_extracting_it(self):
        report = AccountReport()
        report.note_listed('t1')
        report.error('HTTP Error 403: Forbidden')

        self.assertEqual(BLANK, report.outcome)
