import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { ToastContext } from "./toast-context";
import type { Toast, ToastContextValue } from "./toast-context";

const AUTO_DISMISS_MS = 4000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const notify = useCallback(
    (toast: Omit<Toast, "id">) => {
      nextId.current += 1;
      const id = nextId.current;
      setToasts((current) => [...current, { ...toast, id }]);
      setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss]
  );

  const value = useMemo<ToastContextValue>(
    () => ({ toasts, notify, dismiss }),
    [toasts, notify, dismiss]
  );

  return <ToastContext value={value}>{children}</ToastContext>;
}