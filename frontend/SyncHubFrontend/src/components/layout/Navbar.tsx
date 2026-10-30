import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { LogIn, Menu, UserPlus, X } from "lucide-react";
import logo from "../../assets/logo.png";
import { paths } from "../../routes/paths";


interface NavLinkItem {
  href: string;
  label: string;
}

/**
 * Barra de navegação da página inicial (landing).
 *
 * Contém o logotipo, links de âncora para as seções da página e as opções
 * "Entrar" e "Criar conta", que redirecionam para as páginas de autenticação.
 */
export function Navbar() {
  const [isOpen, setIsOpen] = useState(false);
  const location = useLocation();

  const sectionLinks: NavLinkItem[] = [
    { href: "#inicio", label: "Início" },
    { href: "#sobre", label: "Sobre" },
    { href: "#faq", label: "Perguntas" },
    { href: "#suporte", label: "Suporte" },
  ];

  const activeSection = sectionLinks.find(
    (item) => location.hash === item.href
  )?.label;

  const toggleMobileMenu = () => setIsOpen((prev) => !prev);

  return (
    <header className="sticky top-0 z-40 shrink-0 border-b border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      <div className="flex h-16 shrink-0 items-center justify-between gap-4 px-4 md:px-6">
        {/* Logotipo */}
        <Link
          to="#inicio"
          onClick={() => setIsOpen(false)}
          className="flex items-center gap-2 rounded-xl bg-brand-700 px-3 py-1.5 text-sm font-extrabold text-white transition-colors hover:bg-brand-800"
          aria-label="Stock Sync — página inicial"
        >
          <img src={logo} alt="Stock Sync" className="h-6 w-6 object-contain" />
          <span className="hidden md:inline">Stock Sync</span>
        </Link>

        {/* Links de seções (desktop) */}
        <nav className="hidden md:flex items-center gap-6" aria-label="Navegação principal">
          {sectionLinks.map((item) => (
            <Link
              key={item.href}
              to={item.href}
              onClick={() => setIsOpen(false)}
              className={`text-sm font-medium transition-colors ${
                activeSection === item.label
                  ? "text-brand-700"
                  : "text-slate-600 hover:text-brand-700"
              }`}
            >
              {item.label}
            </Link>
          ))}

          <div className="flex items-center gap-3">
            <Link
              to={paths.login}
              onClick={() => setIsOpen(false)}
              className="text-sm font-medium text-slate-600 transition-colors hover:text-brand-700"
            >
              <LogIn aria-hidden="true" className="h-4 w-4 mr-1" />
              Entrar
            </Link>
            <Link
              to={paths.register}
              onClick={() => setIsOpen(false)}
              className="rounded-xl bg-brand-700 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-brand-800"
            >
              <UserPlus aria-hidden="true" className="h-4 w-4 mr-1" />
              Criar conta
            </Link>
          </div>
        </nav>

        {/* Botão menu mobile */}
        <button
          type="button"
          onClick={toggleMobileMenu}
          className="md:hidden inline-flex items-center justify-center rounded-lg p-2 text-slate-600 hover:bg-slate-100"
          aria-label="Abrir menu"
          aria-expanded={isOpen}
        >
          {isOpen ? (
            <X aria-hidden="true" className="h-5 w-5" />
          ) : (
            <Menu aria-hidden="true" className="h-5 w-5" />
          )}
        </button>
      </div>

      {/* Menu mobile */}
      {isOpen && (
        <div className="md:hidden border-t border-line bg-surface px-4 pb-4">
          <div className="space-y-2">
            {sectionLinks.map((item) => (
              <Link
                key={item.href}
                to={item.href}
                onClick={() => setIsOpen(false)}
                className={`block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  activeSection === item.label
                    ? "bg-brand-50 text-brand-700"
                    : "text-slate-600 hover:bg-slate-50 hover:text-brand-700"
                }`}
              >
                {item.label}
              </Link>
            ))}
            <div className="border-t border-line pt-3 space-y-2">
              <Link
                to={paths.login}
                onClick={() => setIsOpen(false)}
                className="block rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50 hover:text-brand-700"
              >
                <LogIn aria-hidden="true" className="h-4 w-4 mr-2" />
                Entrar
              </Link>
              <Link
                to={paths.register}
                onClick={() => setIsOpen(false)}
                className="block rounded-xl bg-brand-700 px-3 py-2 text-sm font-semibold text-white text-center transition-colors hover:bg-brand-800"
              >
                <UserPlus aria-hidden="true" className="h-4 w-4 mr-2" />
                Criar conta
              </Link>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
