import { useState } from "react";

// Validação de TypeScript: Interface tipada para o painel de dependências
interface DependencyStatus {
  name: string;
  version: string;
  description: string;
  isConfigured: boolean;
}

export default function App() {
  // Validação de React + TypeScript: Estado tipado
  const [count, setCount] = useState<number>(0);

  // Lista para validar a renderização das ferramentas no layout Tailwind
  const dependencies: DependencyStatus[] = [
    {
      name: "React 18+",
      version: "Library",
      description: "Estado e ciclo de vida do componente operacionais",
      isConfigured: true,
    },
    {
      name: "TypeScript",
      version: "v5+",
      description: "Interfaces, tipos genéricos e checagem estática ativos",
      isConfigured: true,
    },
    {
      name: "Tailwind CSS",
      version: "v3/v4",
      description: "Classes utilitárias, temas e gradientes aplicados",
      isConfigured: true,
    },
    {
      name: "ESLint",
      version: "Linter",
      description: "Regras de código e boas práticas sintáticas validadas",
      isConfigured: true,
    },
    {
      name: "Prettier",
      version: "Formatter",
      description: "Padrão de formatação, aspas e indentação consistentes",
      isConfigured: true,
    },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-4 sm:p-6">
      {/* Card principal */}
      <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-2xl space-y-6">
        {/* Cabeçalho */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-semibold uppercase tracking-wider">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Environment Check
          </div>

          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 via-indigo-400 to-emerald-400 bg-clip-text text-transparent">
            StockSync Frontend
          </h1>

          <p className="text-slate-400 text-sm">
            Painel de validação da stack principal de desenvolvimento.
          </p>
        </div>

        {/* Teste Interativo (React + TypeScript) */}
        <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80 space-y-3 text-center">
          <p className="text-xs uppercase tracking-widest text-slate-400 font-medium">
            Teste de Estado React + TypeScript
          </p>
          <div className="text-4xl font-black text-indigo-400">{count}</div>
          <div className="flex justify-center gap-2">
            <button
              type="button"
              onClick={() => setCount((prev) => prev - 1)}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 active:scale-95 text-slate-200 text-sm font-semibold rounded-lg border border-slate-700 transition-all duration-150"
            >
              -1
            </button>
            <button
              type="button"
              onClick={() => setCount(0)}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 active:scale-95 text-slate-400 text-sm font-semibold rounded-lg border border-slate-700 transition-all duration-150"
            >
              Reset
            </button>
            <button
              type="button"
              onClick={() => setCount((prev) => prev + 1)}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white text-sm font-semibold rounded-lg shadow-lg shadow-indigo-600/30 transition-all duration-150"
            >
              +1
            </button>
          </div>
        </div>

        {/* Checklist das Dependências (Tailwind + TS) */}
        <div className="space-y-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Dependências Verificadas
          </h2>
          <div className="space-y-2">
            {dependencies.map((item) => (
              <div
                key={item.name}
                className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-slate-700/40 text-left"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-slate-200">
                      {item.name}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 font-mono">
                      {item.version}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {item.description}
                  </p>
                </div>
                <div className="text-emerald-400 font-bold text-sm">✓</div>
              </div>
            ))}
          </div>
        </div>

        {/* Instalação do Linter/Formatter */}
        <div className="text-xs text-slate-500 border-t border-slate-800 pt-4 text-center">
          Execute <code className="text-slate-400">npx eslint .</code> e{" "}
          <code className="text-slate-400">npx prettier --check .</code> no
          terminal para validar o ESLint e o Prettier.
        </div>
      </div>
    </div>
  );
}
