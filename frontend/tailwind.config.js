/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        luminous: {
          teal: "#28BDBF",
          dark: "#00A398",
          ink: "#141B2B",
          muted: "#667085",
          canvas: "#F9F9FF",
          panel: "#FFFFFF",
          line: "#E5E7EB",
          gold: "#E3BB42",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        work: ["Roboto", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        luminous: "0 18px 45px -28px rgba(0, 105, 107, 0.35)",
        composer: "0 -16px 42px -30px rgba(20, 27, 43, 0.4)",
      },
    },
  },
  plugins: [],
};
