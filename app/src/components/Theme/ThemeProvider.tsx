import { createContext, useContext, useEffect, useState } from 'react';
import { useApiStore } from '@/store/apiStore';

type Theme = 'light' | 'dark' | 'system';
type ColorTheme = 'default' | 'blue' | 'purple' | 'green' | 'orange' | 'pink';

interface ThemeContextType {
  theme: Theme;
  colorTheme: ColorTheme;
  setTheme: (theme: Theme) => void;
  setColorTheme: (colorTheme: ColorTheme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const colorThemes: Record<ColorTheme, { primary: string; primaryForeground: string; accent: string }> = {
  default: {
    primary: '240 5.9% 10%',
    primaryForeground: '0 0% 98%',
    accent: '240 4.8% 95.9%',
  },
  blue: {
    primary: '217 91% 60%',
    primaryForeground: '0 0% 100%',
    accent: '213 100% 96%',
  },
  purple: {
    primary: '270 60% 55%',
    primaryForeground: '0 0% 100%',
    accent: '270 50% 96%',
  },
  green: {
    primary: '142 76% 36%',
    primaryForeground: '0 0% 100%',
    accent: '142 60% 96%',
  },
  orange: {
    primary: '24 95% 53%',
    primaryForeground: '0 0% 100%',
    accent: '24 100% 96%',
  },
  pink: {
    primary: '330 80% 60%',
    primaryForeground: '0 0% 100%',
    accent: '330 80% 96%',
  },
};

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const storeTheme = useApiStore((state) => state.theme);
  const storeSetTheme = useApiStore((state) => state.setTheme);
  
  const [theme, setThemeState] = useState<Theme>(storeTheme);
  const [colorTheme, setColorThemeState] = useState<ColorTheme>('default');

  // 从localStorage加载颜色主题
  useEffect(() => {
    const savedColorTheme = localStorage.getItem('ai-assistant-color-theme') as ColorTheme;
    if (savedColorTheme && colorThemes[savedColorTheme]) {
      setColorThemeState(savedColorTheme);
    }
  }, []);

  // 同步store主题
  useEffect(() => {
    setThemeState(storeTheme);
  }, [storeTheme]);

  // 应用主题
  useEffect(() => {
    const root = window.document.documentElement;
    
    // 处理light/dark/system
    let effectiveTheme = theme;
    if (theme === 'system') {
      effectiveTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    
    root.classList.remove('light', 'dark');
    root.classList.add(effectiveTheme);
    
    // 应用颜色主题
    const colors = colorThemes[colorTheme];
    if (colors) {
      root.style.setProperty('--primary', colors.primary);
      root.style.setProperty('--primary-foreground', colors.primaryForeground);
      root.style.setProperty('--accent', colors.accent);
    }
  }, [theme, colorTheme]);

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    storeSetTheme(newTheme);
  };

  const setColorTheme = (newColorTheme: ColorTheme) => {
    setColorThemeState(newColorTheme);
    localStorage.setItem('ai-assistant-color-theme', newColorTheme);
  };

  return (
    <ThemeContext.Provider value={{ theme, colorTheme, setTheme, setColorTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
