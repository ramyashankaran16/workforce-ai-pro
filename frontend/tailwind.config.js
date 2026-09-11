/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#f8fafc", 100: "#f1f5f9", 200: "#e2e8f0", 300: "#cbd5e1",
          400: "#94a3b8", 500: "#64748b", 600: "#475569", 700: "#334155",
          800: "#1e293b", 900: "#0f172a",
        },
        brand: {
          50: "#eef2ff", 100: "#e0e7ff", 300: "#a5b4fc",
          500: "#6366f1", 600: "#4f46e5", 700: "#4338ca",
        },
        risk: {
          low: "#10b981", medium: "#f59e0b", high: "#f97316", critical: "#ef4444",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(0 0 0 / 0.04), 0 1px 6px -1px rgb(0 0 0 / 0.06)",
      },
    },
  },
  plugins: [],
};
