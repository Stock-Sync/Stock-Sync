import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import { ToastProvider } from "./components/ui/ToastProvider";
import { ToastViewport } from "./components/ui/ToastViewport";
import { hydrate } from "./mock/handlers";
import { AppRoutes } from "./routes";

/**
 * QueryClient compartilhado.
 *
 * `staleTime` curto porque os dados são mockados e mudam a cada ação; quando o
 * backend real entrar, ajuste para reflecting real-time dos endpoints.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

// Recupera o que ficou salvo em execuções anteriores antes do primeiro render.
hydrate();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <AuthProvider>
          <ToastProvider>
            <AppRoutes />
            <ToastViewport />
          </ToastProvider>
        </AuthProvider>
      </HashRouter>
    </QueryClientProvider>
  );
}

export default App;