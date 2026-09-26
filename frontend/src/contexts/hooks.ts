import { createContext, useContext } from "react";
import type { AuthContextType } from "./AuthContext";
import type { LanguageContextType } from "./LanguageContext";
import type { ThemeContextType } from "./ThemeContext";
import type { TaxProfileContextValue } from "./TaxProfileContext";
import type { AdvisorContextValue } from "./AdvisorContext";
import type { ChatHistoryContextType } from "./ChatHistoryContext";
import type { DocumentProcessingContextValue } from "./DocumentProcessingContext";

export const AuthContext = createContext<AuthContextType | undefined>(undefined);
export const LanguageContext = createContext<LanguageContextType | undefined>(undefined);
export const ThemeContext = createContext<ThemeContextType | undefined>(undefined);
export const TaxProfileContext = createContext<TaxProfileContextValue | null>(null);
export const AdvisorContext = createContext<AdvisorContextValue | undefined>(undefined);
export const ChatHistoryContext = createContext<ChatHistoryContextType | undefined>(undefined);
export const DocumentProcessingContext = createContext<DocumentProcessingContextValue | undefined>(undefined);

export function useAuth(): AuthContextType {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}

export function useLang(): LanguageContextType {
  const value = useContext(LanguageContext);
  if (!value) throw new Error("useLang must be used within a LanguageProvider");
  return value;
}

export function useTheme(): ThemeContextType {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used within a ThemeProvider");
  return value;
}

export function useTaxProfile(): TaxProfileContextValue {
  const value = useContext(TaxProfileContext);
  if (!value) throw new Error("useTaxProfile must be used within TaxProfileProvider");
  return value;
}

export function useAdvisor(): AdvisorContextValue {
  const value = useContext(AdvisorContext);
  if (!value) throw new Error("useAdvisor must be used within AdvisorProvider");
  return value;
}

export function useChatHistory(): ChatHistoryContextType {
  const value = useContext(ChatHistoryContext);
  if (!value) throw new Error("useChatHistory must be used within ChatHistoryProvider");
  return value;
}

export function useDocumentProcessing(): DocumentProcessingContextValue {
  const value = useContext(DocumentProcessingContext);
  if (!value) throw new Error("useDocumentProcessing must be used within DocumentProcessingProvider");
  return value;
}
