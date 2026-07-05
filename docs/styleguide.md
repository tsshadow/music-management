# 🎨 Style Guide

## Theme: Spotify Dark
The system follows a dark theme inspired by Spotify to provide a consistent and modern user experience.

## Colors
- **Primary Accent (Green)**: `#1DB954` (Spotify Green) - Use for primary actions, icons, and highlights.
- **Background (Main)**: `#121212` (Black) - The default background color for content.
- **Background (Sidebar)**: `#000000` (Pure Black) - For the sidebar navigation bar.
- **Surface (Cards/Buttons)**: `#282828` (Gray) - For cards, active menu items, and hover states.
- **Text (Primary)**: `#FFFFFF` (White) - For headings and important text.
- **Text (Secondary)**: `#B3B3B3` (Light Gray) - For secondary information and dimmed text.

## UI Components
- **Buttons**: Use rounded corners (`rounded-full`) for primary actions with a green background.
- **Inputs**: Dark background with a subtle border that turns green on focus.
- **Tabs**: The active tab gets a gray background (`bg-spotify-gray`) and white text.

## Guidelines
1. **No Blue**: Avoid using standard blue colors for links, focus states, or buttons. Everything must align with the green/black/gray palette.
2. **Consistency**: Always use the defined Tailwind colors (`spotify-green`, `spotify-gray`, etc.).
3. **Typography**: Use a sans-serif font for a modern look.
4. **Interaction**: Add subtle transitions (`transition-colors`, `hover:scale-105`) for a responsive feel.
