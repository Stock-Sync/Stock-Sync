import { Navigate, Outlet, useLocation } from "react-router-dom";
import { paths } from "../routes/paths";
import { useAuth } from "./auth-context";

/**
 * Guarda de rota.
 *
 * Sem sessão, redireciona para `/login` guardando a rota pretendida em
 * `location.state.from`. O `LoginPage` lê esse estado para devolver o usuário ao
 * destino original — é o que reproduz o fluxo "Criar Produto → Login → Criar
 * Produto" da Imagem 3.
 *
 * Rotas liberadas sem sessão (dashboard, produtos e login) não usam este
 * componente; ver `routes/index.tsx`.
 */
export function RequireAuth() {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return (
      <Navigate to={paths.login} replace state={{ from: location }} />
    );
  }

  return <Outlet />;
}