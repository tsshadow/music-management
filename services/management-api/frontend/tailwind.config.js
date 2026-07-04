/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{svelte,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        spotify: {
          green: '#1DB954',
          black: '#121212',
          dark: '#000000',
          gray: '#282828',
          lightgray: '#b3b3b3'
        }
      }
    },
  },
  plugins: [],
}
