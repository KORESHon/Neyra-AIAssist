import type { Config } from 'tailwindcss'
import typography from '@tailwindcss/typography'

export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: 'hsl(222 47% 7%)',
        foreground: 'hsl(210 40% 96%)',
        card: 'hsl(222 40% 11%)',
        muted: 'hsl(215 20% 65%)',
        border: 'hsl(222 25% 22%)',
        accent: 'hsl(197 92% 74%)',
      },
    },
  },
  plugins: [typography],
} satisfies Config
