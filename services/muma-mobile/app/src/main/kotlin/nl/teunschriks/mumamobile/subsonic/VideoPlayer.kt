package nl.teunschriks.mumamobile.subsonic

import android.content.Context
import android.content.Intent
import android.net.Uri
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.util.Util

/**
 * This utility class helps starting video playback
 */
@Suppress("UtilityClassWithPublicConstructor")
class VideoPlayer {
    companion object {
        fun playVideo(context: Context, track: Track?) {
            if (!Util.hasUsableNetwork() || track == null) {
                Util.toast(R.string.select_album_no_network, true, context)
                return
            }
            try {
                val intent = Intent(Intent.ACTION_VIEW)
                val url = MusicServiceFactory.getMusicService().getStreamUrl(
                    track.id,
                    maxBitRate = null,
                    format = "raw"
                )
                intent.setDataAndType(
                    Uri.parse(url),
                    "video/*"
                )
                context.startActivity(intent)
            } catch (all: Exception) {
                Util.toast(all.toString(), false, context)
            }
        }
    }
}
