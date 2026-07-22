/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Design tokens placeholder — replace with the provided UI design system.
      colors: {
        brand: { DEFAULT: "#e4572e", dark: "#b8431f" },
      },
    },
  },
  plugins: [],
};
