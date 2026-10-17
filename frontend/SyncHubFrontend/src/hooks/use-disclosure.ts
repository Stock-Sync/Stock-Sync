import { useEffect, useRef, useState } from "react";

/**
 * Fecha um popover ao clicar fora ou pressionar Escape.
 *
 * Usado pelo menu do usuário e pela busca global. Mantido como hook para não
 * duplicar a lógica de listener nos dois componentes.
 */
export function useDismissOnOutside(
  isOpen: boolean,
  onDismiss: () => void
) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const onPointerDown = (event: MouseEvent) => {
      const node = containerRef.current;
      if (node && !node.contains(event.target as Node)) {
        onDismiss();
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onDismiss();
      }
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [isOpen, onDismiss]);

  return containerRef;
}

/** Estado booleano com o par de setters, para abrir/fechar popovers. */
export function useDisclosure(initial = false) {
  const [isOpen, setIsOpen] = useState(initial);
  return {
    isOpen,
    open: () => setIsOpen(true),
    close: () => setIsOpen(false),
    toggle: () => setIsOpen((current) => !current),
  };
}