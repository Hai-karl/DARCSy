import { useEffect, useRef, useState } from "react";
import { Chart } from "chart.js/auto";

export function useDark() {
  const q = () => (typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)") : null);
  const [dark, setDark] = useState(() => !!q()?.matches);
  useEffect(() => {
    const m = q();
    if (!m) return;
    const f = (e) => setDark(e.matches);
    m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, []);
  return dark;
}

/** `build(theme)` returns a Chart.js config. The chart is rebuilt when `deps` or the colour scheme change. */
export default function ChartCanvas({ build, deps, height = 280, label }) {
  const ref = useRef(null);
  const dark = useDark();
  useEffect(() => {
    const theme = { dark, text: dark ? "#93a8b0" : "#5b6f77", grid: dark ? "#2a3d45" : "#dbe3e6",
      brand: dark ? "#4fc3cf" : "#0f6e78", signal: dark ? "#ff9a4d" : "#d9610f", ok: dark ? "#5fd09a" : "#2b8a5a" };
    const chart = new Chart(ref.current, build(theme));
    return () => chart.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, dark]);
  return (
    <div style={{ height }} role="img" aria-label={label}>
      <canvas ref={ref} />
    </div>
  );
}
