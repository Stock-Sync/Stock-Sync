import { createContext, use } from "react";

export type ToastTone = "success" | "error" | "info";

export interface Toast {
  id: number;
  title: string;
  description?: string;
  tone: ToastTone;
}

export interface ToastContextValue {
  toasts: Toast[];
  notify: (toast: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const context = use(ToastContext);
  if (!context) {
    throw new Error("useToast precisa estar dentro de <ToastProvider>.");
  }
  return context;
}