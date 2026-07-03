# 🖥️ Music Management Frontends

This project contains two primary web interfaces built with Svelte and Vite.

## 📂 Frontends

### 1. Music Management UI (`frontend/music-management`)
This is the administrative dashboard for the library management system.
- **Purpose**: Monitor import/tagger workers, manage jobs, and view library status.
- **Tech Stack**: SvelteKit, Vite.
- **Key Features**:
    - Real-time job monitoring via WebSockets.
    - Matrix-style background (because why not).
    - Step-by-step progress tracking for audio processing.

### 2. Scrobbler UI (`frontend/scrobbler`)
The listener-facing dashboard for the Scrobbler service.
- **Purpose**: View listening history, analytics, and library insights.
- **Tech Stack**: Svelte, Vite.
- **Key Features**:
    - "Hype Graph" for listening trends.
    - Leaderboards for library_artists/library_tracks/rules_genres.
    - Integration with the media library for enriched metadata.

## 🚀 Development

To run a frontend in development mode:

```bash
cd frontend/<project-name>/frontend
npm install
npm run dev
```

## 🐳 Docker Integration

In production, these frontends are built and served as static assets by their respective backend APIs (FastAPI).
