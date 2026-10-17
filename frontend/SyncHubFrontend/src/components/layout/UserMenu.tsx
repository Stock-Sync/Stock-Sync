import { useCallback } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { LogOut, UserRound } from "lucide-react";
import { useAuth } from "../../auth/auth-context";
import { useDisclosure, useDismissOnOutside } from "../../hooks/use-disclosure";
import { paths } from "../../routes/paths";
import { Avatar } from "../ui/Avatar";

/**
 * Menu suspenso do avatar no topo (Imagem 8).
 *
 * Opções: Perfil e Sair.
 */
export function UserMenu() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const { isOpen, close, toggle } = useDisclosure();
  const containerRef = useDismissOnOutside(isOpen, close);

  const handleLogout = useCallback(() => {
    close();
    logout();
    navigate(paths.dashboard, { replace: true });
  }, [close, logout, navigate]);

  if (!isAuthenticated) {
    return (
      <NavLink
        to={paths.login}
        className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-brand-700 transition-colors hover:bg-brand-50"
      >
        Entrar
      </NavLink>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={toggle}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label="Menu do usuário"
        className="rounded-full transition-opacity hover:opacity-80"
      >
        <Avatar label={user?.username ?? ""} size="sm" />
      </button>

      {isOpen && (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-2 w-48 overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-pop"
        >
          <div className="border-b border-line px-4 py-2">
            <p className="truncate text-sm font-semibold text-slate-800">
              {user?.username}
            </p>
            <p className="truncate text-xs text-slate-500">
              {user?.email || "Sem e-mail"}
            </p>
          </div>

          <NavLink
            to={paths.profile}
            role="menuitem"
            onClick={close}
            className="flex items-center gap-2 px-4 py-2 text-sm text-slate-700 transition-colors hover:bg-slate-50"
          >
            <UserRound aria-hidden="true" className="h-4 w-4 text-slate-400" />
            Perfil
          </NavLink>

          <button
            type="button"
            role="menuitem"
            onClick={handleLogout}
            className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-slate-700 transition-colors hover:bg-slate-50"
          >
            <LogOut aria-hidden="true" className="h-4 w-4 text-slate-400" />
            Sair
          </button>
        </div>
      )}
    </div>
  );
}