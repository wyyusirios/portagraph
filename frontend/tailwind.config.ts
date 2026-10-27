import type { Config } from 'tailwindcss';

export default {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: { 50: '#eef4ff', 500: '#3b5bdb', 600: '#2f4ac0', 900: '#1b2559' },
        unique: '#f59f00',
      },
    },
  },
  plugins: [],
} satisfies Config;
