/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './index.html',
    './src/**/*.{svelte,ts}',
    '../../apps/web/src/lib/ui/**/*.{svelte,ts}',
  ],
  theme: {
    extend: {
      colors: {
        accent: '#7c4dff',
        'accent-soft': 'rgba(124, 77, 255, 0.16)',
        danger: '#ff6b6b',
        success: '#2dd4bf',
        'color-border-subtle': 'rgba(255, 255, 255, 0.08)',
        'color-border-strong': 'rgba(255, 255, 255, 0.18)',
        'color-text-primary': '#f2f2f7',
        'color-text-muted': 'rgba(242, 242, 247, 0.72)',
        'color-text-soft': 'rgba(242, 242, 247, 0.6)',
      },
      backgroundImage: {
        app: 'radial-gradient(circle at top, rgba(42, 46, 74, 0.9), rgba(17, 17, 28, 0.95))',
        hero: 'linear-gradient(135deg, rgba(124, 77, 255, 0.35), rgba(56, 189, 248, 0.25))',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
      },
      boxShadow: {
        app: '0 10px 25px rgba(8, 11, 30, 0.25)',
        card: '0 16px 35px rgba(8, 11, 30, 0.32)',
        'card-lg': '0 20px 45px rgba(8, 11, 30, 0.38)',
      },
      keyframes: {
        'progress-slide': {
          '0%': { transform: 'translateX(-100%)' },
          '50%': { transform: 'translateX(0%)' },
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'progress-slide': 'progress-slide 1.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
