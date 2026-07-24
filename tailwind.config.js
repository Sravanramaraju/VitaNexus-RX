/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        background: '#F8FAFC', card: '#FFFFFF', primary: '#2563EB', accent: '#14B8A6',
        success: '#22C55E', warning: '#F59E0B', danger: '#EF4444', text: '#0F172A', border: '#E5E7EB',
      },
    },
  },
  plugins: [],
}
