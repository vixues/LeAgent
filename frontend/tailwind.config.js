import typography from '@tailwindcss/typography';

/** @type {import('tailwindcss').Config} */
// JIT scans `content` only for static substrings. Avoid `className={\`bg-${tone}-500\`}`; use string-literal maps or `safelist`.
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        /** Brand primary — Tailwind `sky` scale (cyan-blue; no violet). */
        primary: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
          950: '#082f49',
        },
        peach: {
          50: '#fff7ed',
          100: '#ffedd5',
          200: '#fed7aa',
          300: '#fdba74',
          400: '#fb923c',
          500: '#f97316',
          600: '#ea580c',
          700: '#c2410c',
          800: '#9a3412',
          900: '#7c2d12',
          950: '#431407',
        },
        mint: {
          50: '#ecfdf5',
          100: '#d1fae5',
          200: '#a7f3d0',
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
          800: '#065f46',
          900: '#064e3b',
          950: '#022c22',
        },
        rose: {
          50: '#fff1f2',
          100: '#ffe4e6',
          200: '#fecdd3',
          300: '#fda4af',
          400: '#fb7185',
          500: '#f43f5e',
          600: '#e11d48',
          700: '#be123c',
          800: '#9f1239',
          900: '#881337',
          950: '#4c0519',
        },
        /** Semantic tokens — rgb tuples from globals.css (:root / .dark) */
        background: 'rgb(var(--color-background) / <alpha-value>)',
        surface: 'rgb(var(--color-surface) / <alpha-value>)',
        'surface-elevated': 'rgb(var(--color-surface-elevated) / <alpha-value>)',
        'surface-sunken': 'rgb(var(--color-surface-sunken) / <alpha-value>)',
        foreground: 'rgb(var(--color-text) / <alpha-value>)',
        'muted-foreground': 'rgb(var(--color-text-secondary) / <alpha-value>)',
        'muted-foreground-tertiary': 'rgb(var(--color-text-tertiary) / <alpha-value>)',
        border: 'rgb(var(--color-border) / <alpha-value>)',
        'border-subtle': 'rgb(var(--color-border-subtle) / <alpha-value>)',
      },
      fontFamily: {
        sans: [
          'Inter',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
        mono: [
          'JetBrains Mono',
          'Fira Code',
          'Consolas',
          'Monaco',
          'monospace',
        ],
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'pulse-slow': 'pulseSlow 3s ease-in-out infinite',
        'typing': 'typing 1s ease-in-out infinite',
        'bounce-gentle': 'bounceGentle 1s ease-in-out infinite',
        'wiggle': 'wiggle 0.8s ease-in-out infinite',
        'float': 'float 2.5s ease-in-out infinite',
        'sparkle': 'sparkle 1.5s ease-in-out infinite',
        'blink': 'blink 3s ease-in-out infinite',
        'progress-wave': 'progressWave 1.5s ease-in-out infinite',
        'orbit': 'orbit 4s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        pulseSlow: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.6' },
        },
        typing: {
          '0%, 60%, 100%': { opacity: '1' },
          '30%': { opacity: '0.3' },
        },
        bounceGentle: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-6px)' },
        },
        wiggle: {
          '0%, 100%': { transform: 'rotate(0deg)' },
          '25%': { transform: 'rotate(-3deg)' },
          '75%': { transform: 'rotate(3deg)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-4px)' },
        },
        sparkle: {
          '0%, 100%': { opacity: '0.4', transform: 'scale(0.8)' },
          '50%': { opacity: '1', transform: 'scale(1)' },
        },
        blink: {
          '0%, 45%, 55%, 100%': { transform: 'scaleY(1)' },
          '50%': { transform: 'scaleY(0.1)' },
        },
        progressWave: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(200%)' },
        },
        orbit: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
      },
      boxShadow: {
        'glow': '0 0 20px rgba(2, 132, 199, 0.24)',
        'glow-lg': '0 0 40px rgba(2, 132, 199, 0.34)',
        'peach': '0 0 20px rgba(251, 146, 60, 0.2)',
        'soft': '0 2px 8px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.03)',
      },
    },
  },
  plugins: [
    typography,
  ],
};
