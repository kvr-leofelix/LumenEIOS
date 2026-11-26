import React, { createContext, useContext, useMemo, useState } from 'react';

export const THEMES = [
  {
    id: 'light',
    label: 'Light',
    hint: 'Green and blue',
    swatches: ['#142A43', '#16A085', '#F3F6F8'],
  },
  {
    id: 'dark',
    label: 'Dark',
    hint: 'Green and blue',
    swatches: ['#0C1626', '#16A085', '#122032'],
  },
  {
    id: 'presentation',
    label: 'Presentation',
    hint: 'Ink, ivory, and brass',
    swatches: ['#16130F', '#E7B15A', '#F7F1E6'],
  },
] as const;

export const UI_MODES = [
  { id: 'classic', label: 'Current interface', hint: 'The existing LumenEIOS screens' },
  { id: 'presentation', label: 'Presentation interface', hint: 'Serif headlines and rounded rooms' },
  { id: 'analytics', label: 'Analytics platform', hint: 'Navy, slate, and print-ready reports' },
] as const;

export type ThemeId = (typeof THEMES)[number]['id'];
export type UiMode = (typeof UI_MODES)[number]['id'];

const STORAGE_KEY = 'lumeneios_theme';
const UI_STORAGE_KEY = 'lumeneios_ui';

export function isThemeId(value: string | null): value is ThemeId {
  return THEMES.some((theme) => theme.id === value);
}

export function isUiMode(value: string | null): value is UiMode {
  return value === 'classic' || value === 'presentation' || value === 'analytics';
}

export function readStoredTheme(): ThemeId {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (isThemeId(saved)) return saved;
    if (saved === 'midnight') return 'dark';
  } catch {
    /* storage can be unavailable in private contexts */
  }
  return 'light';
}

export function readStoredUi(): UiMode {
  try {
    const saved = localStorage.getItem(UI_STORAGE_KEY);
    if (isUiMode(saved)) return saved;
  } catch {
    /* storage can be unavailable in private contexts */
  }
  return 'classic';
}

export function applyTheme(theme: ThemeId) {
  document.documentElement.dataset.theme = theme;
}

export function applyUi(mode: UiMode) {
  document.documentElement.dataset.ui = mode;
}

applyTheme(readStoredTheme());
applyUi(readStoredUi());

interface ThemeContextValue {
  theme: ThemeId;
  setTheme: (theme: ThemeId) => void;
  uiMode: UiMode;
  setUiMode: (mode: UiMode) => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<ThemeId>(readStoredTheme);
  const [uiMode, setUiModeState] = useState<UiMode>(readStoredUi);

  const setTheme = (next: ThemeId) => {
    applyTheme(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage can be unavailable in private contexts */
    }
    setThemeState(next);
  };

  const setUiMode = (next: UiMode) => {
    applyUi(next);
    try {
      localStorage.setItem(UI_STORAGE_KEY, next);
    } catch {
      /* storage can be unavailable in private contexts */
    }
    setUiModeState(next);
  };

  const value = useMemo(() => ({ theme, setTheme, uiMode, setUiMode }), [theme, uiMode]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}

export interface ChartPalette {
  border: string;
  card: string;
  secondary: string;
  ink: string;
  accent: string;
  muted: string;
}

function channel(style: CSSStyleDeclaration, name: string, fallback: string) {
  const value = style.getPropertyValue(name).trim();
  return value ? `rgb(${value})` : fallback;
}

export function useChartPalette(): ChartPalette {
  const { theme, uiMode } = useTheme();

  return useMemo(() => {
    const style = getComputedStyle(document.documentElement);
    const analytics = uiMode === 'analytics';
    return {
      border: analytics ? '#E2E8F0' : channel(style, '--surface-border', '#E1E7ED'),
      card: channel(style, '--surface-card', '#FFFFFF'),
      secondary: analytics ? '#475569' : channel(style, '--content-secondary', '#667085'),
      ink: analytics ? '#0F172A' : channel(style, '--ink-navy-800', '#142A43'),
      accent: analytics ? '#1E3A8A' : channel(style, '--bg-teal-500', '#16A085'),
      muted: analytics ? '#64748B' : channel(style, '--content-muted', '#98A2B3'),
    };
  }, [theme, uiMode]);
}
