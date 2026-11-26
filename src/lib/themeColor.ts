import { useTheme } from '../context/ThemeContext';

/** Reads a theme token ("R G B" triplet on :root) as an rgb() colour for SVG charts, which cannot use CSS var(). */
export function themeColor(token: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  const raw = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  return raw ? `rgb(${raw.split(/[\s,]+/).join(' ')})` : fallback;
}

/** Chart text, grid and emphasis colours for the active theme (re-read whenever the theme changes). */
export function useChartInk() {
  const { theme } = useTheme();
  void theme;
  return {
    text: themeColor('--content-primary', '#142A43'),
    muted: themeColor('--content-secondary', '#667085'),
    grid: themeColor('--surface-border', '#E1E7ED'),
  };
}
