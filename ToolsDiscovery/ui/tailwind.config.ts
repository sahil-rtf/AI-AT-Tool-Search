import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0f1117",
        card: "#1e2130",
        "card-border": "#2d3148",
        "cat-bg": "#262b40",
        "cat-border": "#343a54",
        "input-bg": "#0f1117",
        "input-border": "#3d4466",
        "total-bg": "#1a1f33",
      },
      fontFamily: {
        mono: ["Cascadia Code", "Fira Code", "Consolas", "monospace"],
      },
      animation: {
        pulse: "pulse 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
