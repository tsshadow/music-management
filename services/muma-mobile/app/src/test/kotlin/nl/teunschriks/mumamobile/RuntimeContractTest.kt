package nl.teunschriks.mumamobile

import nl.teunschriks.mumamobile.service.PlaybackService
import nl.teunschriks.mumamobile.util.Constants
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test

/**
 * These strings are cross-process and persisted contracts, not code identifiers:
 * broadcast actions held by the system in existing PendingIntents, media session
 * custom commands, and notification channel IDs whose user-visible settings are
 * keyed by the ID.
 *
 * They deliberately keep the historical "org.moire.ultrasonic" prefix even though
 * the Kotlin package is now nl.teunschriks.mumamobile. Changing them orphans the
 * user's notification channel settings and breaks media buttons after an in-place
 * upgrade.
 *
 * If this test fails, do not update the expected values - fix the code that changed them.
 */
class RuntimeContractTest {

    @Test
    fun `broadcast action strings keep their historical prefix`() {
        Constants.CMD_PROCESS_KEYCODE shouldBeEqualTo "org.moire.ultrasonic.CMD_PROCESS_KEYCODE"
        Constants.CMD_PLAY shouldBeEqualTo "org.moire.ultrasonic.CMD_PLAY"
        Constants.CMD_RESUME_OR_PLAY shouldBeEqualTo "org.moire.ultrasonic.CMD_RESUME_OR_PLAY"
        Constants.CMD_TOGGLEPAUSE shouldBeEqualTo "org.moire.ultrasonic.CMD_TOGGLEPAUSE"
        Constants.CMD_PAUSE shouldBeEqualTo "org.moire.ultrasonic.CMD_PAUSE"
        Constants.CMD_STOP shouldBeEqualTo "org.moire.ultrasonic.CMD_STOP"
        Constants.CMD_PREVIOUS shouldBeEqualTo "org.moire.ultrasonic.CMD_PREVIOUS"
        Constants.CMD_NEXT shouldBeEqualTo "org.moire.ultrasonic.CMD_NEXT"
        Constants.INTENT_SHOW_PLAYER shouldBeEqualTo "org.moire.ultrasonic.SHOW_PLAYER"
        Constants.INTENT_PLAY_RANDOM_SONGS shouldBeEqualTo "org.moire.ultrasonic.CMD_RANDOM_SONGS"
    }

    @Test
    fun `media session custom commands keep their historical prefix`() {
        PlaybackService.CUSTOM_COMMAND_CYCLE_RATING shouldBeEqualTo
            "org.moire.ultrasonic.CYCLE_RATING"
        PlaybackService.EXTRA_CURRENT_RATING shouldBeEqualTo "org.moire.ultrasonic.CURRENT_RATING"
        PlaybackService.CUSTOM_COMMAND_SHUFFLE shouldBeEqualTo "org.moire.ultrasonic.SHUFFLE"
        PlaybackService.CUSTOM_COMMAND_PLACEHOLDER shouldBeEqualTo
            "org.moire.ultrasonic.PLACEHOLDER"
        PlaybackService.CUSTOM_COMMAND_REPEAT_MODE shouldBeEqualTo
            "org.moire.ultrasonic.REPEAT_MODE"
    }

    /**
     * The Subsonic client identifier is sent as `c=` on every API call and is what the
     * server records against sessions and scrobbles. It is a server-side contract, so it
     * outlives the app's own name.
     */
    @Test
    fun `the subsonic client id is unchanged`() {
        Constants.REST_CLIENT_ID shouldBeEqualTo "Ultrasonic"
    }
}
