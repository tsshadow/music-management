# 🚀 Downloader Service

The Downloader Service is responsible for automatically fetching music from various online sources and keeping the library up-to-date.

## 📡 Supported Sources

### 📺 YouTube
- Monitors specific channels or playlists for new content.
- Uses `yt-dlp` for high-quality audio extraction.
- Maintains a local archive database to avoid duplicate downloads.

### ☁️ SoundCloud
- Downloads library_tracks from specific library_artists or URLs.
- Handles rate limiting and metadata extraction.

### 📱 Telegram
- Monitors configured Telegram channels or chats.
- Automatically downloads audio files shared in these chats.

## 📂 Structure

- `downloader_service.py`: Main entry point and worker loop.
- `youtube/`: YouTube-specific processing logic.
- `soundcloud/`: SoundCloud-specific processing logic.
- `telegram/`: Telegram-specific processing logic.

## 🛠 Configuration

See the root `.env.example` for source-specific settings (API keys, channel IDs, etc.).
