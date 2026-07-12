/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        // Echelle "iris" remappee sur le BLEU de marque Gilbert (#1E43E5).
        // (nom conserve pour compat des classes existantes text-iris-*, bg-iris-*)
        iris: {
          50: "#eef2ff",
          100: "#e0e7fe",
          200: "#c6d2fd",
          300: "#a3b5fb",
          400: "#7089f6",
          500: "#4560ee",
          600: "#1E43E5",
          700: "#1a37c0",
          800: "#1c3299",
          900: "#1e2f79",
          950: "#141c46",
        },
        // Bleu de marque Gilbert (alias explicite).
        gilbert: {
          50: "#eef2ff",
          100: "#e0e7fe",
          400: "#4560ee",
          500: "#1E43E5",
          600: "#1a37c0",
          navy: "#101422",
        },
        // Vert medical Lexia (#0A7C5A) pour statuts/sante.
        vert: {
          50: "#E4F5EE",
          100: "#c9ecdd",
          400: "#17a874",
          500: "#0A7C5A",
          600: "#086b4e",
          700: "#0a5a42",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ['"Inter"', "system-ui", "-apple-system", "sans-serif"],
        heading: ['"Bricolage Grotesque"', '"Inter"', "system-ui", "sans-serif"],
        display: ['"Bricolage Grotesque"', '"Inter"', "sans-serif"],
        hand: ['"Caveat"', "cursive"],
        serif: ['"Instrument Serif"', "Georgia", "serif"],
        medical: ['"Inter"', "Arial", "sans-serif"],
        mono: ['"JetBrains Mono"', "Consolas", "Monaco", "monospace"],
      },
      keyframes: {
        "pulse-glow": {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "1" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(1)", opacity: "0.5" },
          "100%": { transform: "scale(2)", opacity: "0" },
        },
        "float": {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-6px)" },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-right": {
          from: { transform: "translateX(100%)" },
          to: { transform: "translateX(0)" },
        },
        "toast-in": {
          from: { transform: "translateX(120%)", opacity: "0" },
          to: { transform: "translateX(0)", opacity: "1" },
        },
        "breathe": {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.04)" },
        },
        "pulse-brain": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.55", transform: "scale(0.9)" },
        },
      },
      animation: {
        "pulse-glow": "pulse-glow 1.5s ease-in-out infinite",
        "pulse-ring": "pulse-ring 1.5s ease-out infinite",
        "float": "float 6s ease-in-out infinite",
        "fade-in": "fade-in 0.3s ease-out forwards",
        "slide-right": "slide-right 0.25s ease-out forwards",
        "toast-in": "toast-in 0.3s ease-out forwards",
        "breathe": "breathe 4s ease-in-out infinite",
        "pulse-brain": "pulse-brain 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
