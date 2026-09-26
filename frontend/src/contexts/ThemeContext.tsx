import React, { useEffect, useState } from 'react';
import { ThemeContext } from './hooks';

export type Theme = 'dark' | 'light';

export interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

function readInitialTheme(): Theme {
  // Bayyan key first, then the legacy `theme` key, else light (Bayyan default).
  const saved = localStorage.getItem('bayyan-theme') ?? localStorage.getItem('theme');
  return saved === 'dark' ? 'dark' : 'light';
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(readInitialTheme);

  useEffect(() => {
    localStorage.setItem('bayyan-theme', theme);
    document.documentElement.setAttribute('data-theme', theme);
    // Clean up the legacy body class from the old dark-glass theme.
    document.body.classList.remove('light-theme');
  }, [theme]);

  const toggleTheme = () => setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
