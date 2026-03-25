import { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'light' | 'dark' | 'system';
type ColorTheme = 'default' | 'graphite' | 'moss' | 'teal' | 'brick' | 'amber';

interface ThemeContextType {
  theme: Theme;
  colorTheme: ColorTheme;
  setTheme: (theme: Theme) => void;
  setColorTheme: (colorTheme: ColorTheme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const colorThemes: Record<ColorTheme, { primary: string; primaryForeground: string; accent: string }> = {
  default: {
    primary: '21 72% 46%',
    primaryForeground: '36 33% 97%',
    accent: '32 100% 95%',
  },
  graphite: {
    primary: '217 14% 24%',
    primaryForeground: '30 17% 95%',
    accent: '220 18% 93%',
  },
  moss: {
    primary: '90 31% 38%',
    primaryForeground: '54 27% 96%',
    accent: '92 34% 92%',
  },
  teal: {
    primary: '185 57% 34%',
    primaryForeground: '180 30% 96%',
    accent: '182 39% 91%',
  },
  brick: {
    primary: '9 68% 49%',
    primaryForeground: '24 29% 97%',
    accent: '18 100% 94%',
  },
  amber: {
    primary: '39 85% 47%',
    primaryForeground: '33 48% 12%',
    accent: '44 100% 91%',
  },
};

const legacyColorThemeMap: Record<string, ColorTheme> = {
  blue: 'teal',
  purple: 'graphite',
  green: 'moss',
  orange: 'amber',
  pink: 'brick',
};

function getStoredTheme(): Theme {
  if (typeof window === 'undefined') return 'system';
  const savedTheme = localStorage.getItem('kam-lite-theme');
  return savedTheme === 'light' || savedTheme === 'dark' || savedTheme === 'system' ? savedTheme : 'system';
}

function getStoredColorTheme(): ColorTheme {
  if (typeof window === 'undefined') return 'default';
  const savedColorTheme = localStorage.getItem('kam-lite-color-theme');
  return (savedColorTheme && colorThemes[savedColorTheme as ColorTheme] && (savedColorTheme as ColorTheme)) ||
    (savedColorTheme ? legacyColorThemeMap[savedColorTheme] : undefined) ||
    'default';
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getStoredTheme);
  const [colorTheme, setColorThemeState] = useState<ColorTheme>(getStoredColorTheme);

  useEffect(() => {
    const root = window.document.documentElement;
    let effectiveTheme = theme;

    if (theme === 'system') {
      effectiveTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    root.classList.remove('light', 'dark');
    root.classList.add(effectiveTheme);

    const colors = colorThemes[colorTheme];
    root.style.setProperty('--primary', colors.primary);
    root.style.setProperty('--primary-foreground', colors.primaryForeground);
    root.style.setProperty('--accent', colors.accent);
    root.style.setProperty('--ring', colors.primary);
  }, [theme, colorTheme]);

  const setTheme = (nextTheme: Theme) => {
    setThemeState(nextTheme);
    localStorage.setItem('kam-lite-theme', nextTheme);
  };

  const setColorTheme = (nextColorTheme: ColorTheme) => {
    setColorThemeState(nextColorTheme);
    localStorage.setItem('kam-lite-color-theme', nextColorTheme);
  };

  return (
    <ThemeContext.Provider value={{ theme, colorTheme, setTheme, setColorTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
