import { NavLink } from "react-router-dom";
import { LogIn, LogOut } from "lucide-react";
import { useAuth } from "../../auth/auth-context";
import { paths } from "../../routes/paths";
import { cn } from "../../lib/cn";
import { Avatar } from "../ui/Avatar";
import { navItems } from "./nav-items";

/**
 * Navegação lateral fixa.
 *
 * No rodapé exibe o bloco de sessão: botão "Entrar" + avatar "G" (guest)
 * quando deslogado (Imagem 1), ou avatar "A" do usuário quando logado
 * (Imagens 3 e 6).
 */
export function Sidebar() {
  const { user, isAuthenticated, logout } = useAuth();

  return (
    <aside className="flex w-16 shrink-0 flex-col justify-between border-r border-line bg-surface md:w-64">
      <div className="flex flex-col items-center gap-6 py-5 md:items-stretch md:px-3">
        <nav aria-label="Navegação principal" className="w-full">
          <ul className="flex flex-col items-center gap-1 md:items-stretch">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === paths.dashboard}
                    title={item.label}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center justify-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors md:justify-start",
                        isActive
                          ? "bg-brand-50 text-brand-800"
                          : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                      )
                    }
                  >
                    <Icon aria-hidden="true" className="h-5 w-5 shrink-0" />
                    <span className="hidden md:inline">{item.label}</span>
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>

      <div className="border-t border-line p-3">
        {isAuthenticated ? (
          <div className="flex items-center justify-center gap-2 md:justify-start">
            <Avatar label={user?.username ?? ""} size="sm" />
            <span className="hidden min-w-0 flex-1 truncate text-sm font-medium text-slate-700 md:inline">
              {user?.username}
            </span>
            <button
              type="button"
              onClick={logout}
              title="Sair"
              aria-label="Sair"
              className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
            >
              <LogOut aria-hidden="true" className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 md:items-stretch">
            <NavLink
              to={paths.login}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-700 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
            >
              <LogIn aria-hidden="true" className="h-4 w-4" />
              <span className="hidden md:inline">Entrar</span>
            </NavLink>
            <div className="hidden items-center gap-2 md:flex">
              <Avatar label="Guest" size="sm" tone="neutral" />
              <span className="text-sm text-slate-500">Visitante</span>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}