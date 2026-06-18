# LMS Spotify-like UI

This is a modern, responsive web interface for LMS, built with **Svelte** and **Vite**.

## Development

### Prerequisites

- Node.js (v18+)
- npm

### Setup

```sh
npm install
```

### Running in Development Mode

```sh
npm run dev
```

By default, the development server runs on `http://localhost:5173`.
It is configured to proxy API requests to `http://localhost:5082`. Make sure your LMS backend is running and accessible at that address.

### Building for Production

```sh
npm run build
```

The build artifacts will be located in the `dist/` directory. These files are typically served by the LMS backend.

## Technical Considerations

This UI communicates with the LMS backend using the **Subsonic API**.
For more information on contributing, see the central [CONTRIBUTING.md](../../../../CONTRIBUTING.md).
