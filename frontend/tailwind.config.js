/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        base:    '#090b18',
        surface: '#0c0e1f',
        card:    '#111427',
        'card-2': '#171a30',
        border:  'rgba(255,255,255,0.07)',
        'border-2': 'rgba(255,255,255,0.12)',
        accent:  '#7c5cfc',
        'accent-2': '#9d7dff',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      animation: {
        'bounce-dot': 'bounceDot 1.2s infinite ease-in-out',
        'pulse-slow': 'pulse 3s infinite',
      },
      keyframes: {
        bounceDot: {
          '0%, 80%, 100%': { transform: 'translateY(0)', opacity: '0.4' },
          '40%':           { transform: 'translateY(-6px)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
