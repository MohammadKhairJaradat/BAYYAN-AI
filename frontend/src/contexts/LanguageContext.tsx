import React, { useEffect, useState } from "react";
import { STRINGS, fill, type Lang, type Dir, type Strings } from "../i18n/strings";
import { LanguageContext } from "./hooks";

export interface LanguageContextType {
  lang: Lang;
  dir: Dir;
  /** Active strings object for the current language (use as t.landing.heroLine1). */
  t: Strings;
  setLang: (lang: Lang) => void;
  toggleLang: () => void;
  /** Interpolate {token} placeholders within a string. */
  fill: typeof fill;
}

function readInitialLang(): Lang {
  const saved = localStorage.getItem("bayyan-lang");
  return saved === "ar" ? "ar" : "en";
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLang] = useState<Lang>(readInitialLang);
  const dir: Dir = STRINGS[lang].dir;

  useEffect(() => {
    localStorage.setItem("bayyan-lang", lang);
    document.documentElement.setAttribute("dir", dir);
    document.documentElement.setAttribute("lang", lang);
  }, [lang, dir]);

  const toggleLang = () => setLang((prev) => (prev === "en" ? "ar" : "en"));

  return (
    <LanguageContext.Provider value={{ lang, dir, t: STRINGS[lang], setLang, toggleLang, fill }}>
      {children}
    </LanguageContext.Provider>
  );
}
