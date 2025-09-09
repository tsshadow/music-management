import logging

from yt_dlp.postprocessor import PostProcessor

from downloader.YoutubeArchive import YoutubeArchive
from postprocessing.Song.YoutubeSong import YoutubeSong


class YoutubeSongProcessor(PostProcessor):
    """Postprocessor that archives metadata and tags downloaded YouTube songs."""

    def run(self, info):
        path = info.get("filepath") or info.get("_filename")
        url = info.get("webpage_url")
        if not path or not url:
            logging.warning("Postprocessor: no path or URL found in info dict")
            return [], info

        logging.info(f"Postprocessing downloaded file: {path}")

        account = (
            info.get("uploader_id")
            or info.get("channel_id")
            or info.get("uploader")
            or info.get("channel")
        )
        video_id = info.get("id")
        title = info.get("title")

        if not YoutubeArchive.exists(account, video_id):
            YoutubeArchive.insert(account, video_id, path, url, title)
        else:
            logging.info(
                f"Track already in youtube_archive: {account}/{video_id} — skipping insert."
            )

        song = YoutubeSong(path)
        song.parse()
        return [], info

