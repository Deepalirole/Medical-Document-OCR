/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#152822',
        evergreen: '#164c3b',
        mint: '#e7f2ed',
        linen: '#f5f2ea',
        amber: '#d99a32',
      },
      boxShadow: {
        panel: '0 18px 45px rgba(21, 40, 34, 0.08)',
      },
    },
  },
  plugins: [],
}

