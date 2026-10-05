import type { ReactElement, ReactNode } from "react";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "../auth/AuthProvider";
import { ToastProvider } from "../components/ui/ToastProvider";

/**
 * QueryClient de teste.
 *
 * `retry: false` evita que uma asserção que depende de erro demore três
 * tentativas, e `staleTime: Infinity` impede re-fetch durante o teste.
 */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

export interface RenderWithProvidersOptions {
  route?: string;
  queryClient?: QueryClient;
}

/** Renderiza a tela dentro de uma rota com parâmetro `:id`. */
export function renderAtRoute(
  ui: ReactElement,
  { path, route = path, queryClient }: RenderWithProvidersOptions & {
    path: string;
  }
) {
  return renderWithProviders(
    <Routes>
      <Route path={path} element={ui} />
    </Routes>,
    { route, queryClient }
  );
}

export function renderWithProviders(
  ui: ReactElement,
  {
    route = "/",
    queryClient = createTestQueryClient(),
  }: RenderWithProvidersOptions = {}
) {
  const user = userEvent.setup();

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>
          <ToastProvider>{children}</ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );

  return { user, queryClient, ...render(ui, { wrapper }) };
}