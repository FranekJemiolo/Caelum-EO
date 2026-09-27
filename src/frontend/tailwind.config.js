/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        caelum: {
          bg: '#0a0e17',
          surface: '#101622',
          border: '#1e293b',
          accent: '#00f2fe',
          amber: '#f59e0b',
          crimson: '#f43f5e',
          purple: '#a855f7',
        }
      }
    },
  },
  plugins: [],
}
