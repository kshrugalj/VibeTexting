/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ghost: {
          900: '#0a0a0c',
          800: '#121214',
          700: '#1c1c20',
          600: '#2a2a30',
          500: '#3f3f46',
          vibe: '#d946ef', // Magenta
        }
      }
    },
  },
  plugins: [],
}
