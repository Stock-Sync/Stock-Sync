import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/auth-context";
import { Button } from "../../components/ui/Button";
import { Card, CardBody } from "../../components/ui/Card";
import { paths } from "../../routes/paths";
import {
  Check,
  ChevronDown,
  Mail,
  Phone,
  ShieldCheck,
  UserPlus,
  LogIn,
  Menu,
  X,
} from "lucide-react";

/**
 * Componente Navbar integrado com Scroll Spy, Links âncora ajustados,
 * espaçamento aprimorado, logo customizado e menu mobile otimizado.
 */
function Navbar() {
  const [isOpen, setIsOpen] = useState(false);
  const [activeLink, setActiveLink] = useState("#inicio");

  const navLinks = [
    { name: "Início", href: "#inicio" },
    { name: "Sobre", href: "#sobre" },
    { name: "Avaliações", href: "#comentarios" },
    { name: "FAQ", href: "#faq" },
    { name: "Suporte", href: "#suporte" },
  ];

  // Identifica qual seção está visível na tela para mudar o link ativo
  useEffect(() => {
    const handleScroll = () => {
      let current = "#inicio";
      for (const link of navLinks) {
        const el = document.getElementById(link.href.substring(1));
        if (el) {
          const rect = el.getBoundingClientRect();
          if (rect.top <= 150) {
            current = link.href;
          }
        }
      }
      setActiveLink(current);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleLinkClick = (e: React.MouseEvent<HTMLAnchorElement>, href: string) => {
    e.preventDefault();
    setActiveLink(href);
    setIsOpen(false);
    const el = document.querySelector(href);
    if (el) {
      el.scrollIntoView({ behavior: "smooth" });
    }
  };

  return (
    <nav className="sticky top-0 z-50 w-full bg-surface/90 backdrop-blur border-b border-line">
      <div className="mx-auto max-w-7xl px-4 md:px-6">
        <div className="flex h-16 items-center justify-between">
          {/* Logo da Navbar */}
          <div className="flex items-center gap-3">
            <img
              src="/assets/logo.png"
              alt="Stock Sync Logo"
              className="h-8 w-auto object-contain"
            />
            <span className="text-lg font-bold text-slate-900">Stock Sync</span>
          </div>

          {/* Desktop Nav */}
          <div className="hidden md:flex items-center gap-10 h-full">
            {navLinks.map((link) => (
              <a
                key={link.name}
                href={link.href}
                onClick={(e) => handleLinkClick(e, link.href)}
                className={`relative h-full flex items-center text-sm font-medium transition-colors hover:text-brand-700 ${
                  activeLink === link.href ? "text-brand-700" : "text-slate-600"
                }`}
              >
                {link.name}
                {/* Barra indicadora da seção ativa */}
                {activeLink === link.href && (
                  <span className="absolute bottom-0 left-0 w-full h-0.5 bg-brand-700 rounded-t-full" />
                )}
              </a>
            ))}
          </div>

          {/* Desktop Auth Buttons */}
          <div className="hidden md:flex items-center gap-4">
            <Link
              to={paths.login}
              className="text-sm font-semibold text-slate-700 hover:text-brand-700 transition-colors"
            >
              Entrar
            </Link>
            <Link
              to={paths.register}
              className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
            >
              Criar conta
            </Link>
          </div>

          {/* Botão Hamburger (Mobile) */}
          <div className="md:hidden flex items-center">
            <button
              onClick={() => setIsOpen(!isOpen)}
              className="text-slate-600 hover:text-slate-900 focus:outline-none"
            >
              {isOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
            </button>
          </div>
        </div>
      </div>

      {/* Menu Mobile */}
      {isOpen && (
        <div className="md:hidden border-t border-line bg-surface px-4 py-4 space-y-4 shadow-lg">
          <div className="flex flex-col space-y-3">
            {navLinks.map((link) => (
              <a
                key={link.name}
                href={link.href}
                onClick={(e) => handleLinkClick(e, link.href)}
                className={`block px-2 py-1 text-base font-medium ${
                  activeLink === link.href
                    ? "text-brand-700 border-l-2 border-brand-700 pl-3"
                    : "text-slate-600"
                }`}
              >
                {link.name}
              </a>
            ))}
          </div>
          <div className="flex flex-col gap-3 pt-4 border-t border-line">
            <Link
              to={paths.login}
              className="w-full flex justify-center items-center rounded-lg border border-line bg-surface px-4 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50"
            >
              Entrar
            </Link>
            <Link
              to={paths.register}
              className="w-full flex justify-center items-center rounded-lg bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
            >
              Criar conta
            </Link>
          </div>
        </div>
      )}
    </nav>
  );
}

/**
 * Página inicial (landing) do Stock Sync.
 */
export function LandingPage() {
  const { isLoading } = useAuth();
  const navigate = useNavigate();
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  // Atualização dinâmica do Favicon para logo.png
  useEffect(() => {
    let link: HTMLLinkElement | null = document.querySelector("link[rel*='icon']");
    if (!link) {
      link = document.createElement("link");
      link.rel = "shortcut icon";
      document.getElementsByTagName("head")[0].appendChild(link);
    }
    link.type = "image/png";
    link.href = "/assets/logo.png";
  }, []);

  const toggleFaq = (index: number) => {
    setOpenFaq((prev) => (prev === index ? null : index));
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-10">
        <div className="flex items-center gap-2 text-slate-500">
          <div className="animate-spin rounded-full h-5 w-5 border-2 border-brand-500 border-t-transparent" />
          <span>Verificando sessão...</span>
        </div>
      </div>
    );
  }

  const faqs = [
    {
      q: "O que é o Stock Sync?",
      a: "É um sistema de orquestração e centralização de estoque para vendedores que operam em múltiplos marketplaces. Unifica o controle de SKU, estoque e métricas de vendas entre canais, reduzindo o risco de overselling e underselling.",
    },
    {
      q: "Como funciona a sincronização de estoque?",
      a: "O catálogo é a fonte da verdade. Todo ajuste de estoque publica um evento no stream Redis; o sync-service consome esses eventos, deduz o estoque das vendas e faz o flush em lote (a cada 3s) da quantidade ao marketplace, com dedupe, retries e dead-letter.",
    },
    {
      q: "Quais marketplaces são suportados?",
      a: "No MVP, o foco é a integração com Mercado Livre e Shopee via API, OAuth e webhook receiver. Outros canais podem ser adicionados por meio do catálogo de mapeamento de plataformas.",
    },
    {
      q: "Preciso de cartão de crédito para começar?",
      a: "Não. O acesso à plataforma é feito por meio de cadastro com e-mail e senha. Você pode começar a usar o catálogo e gerenciar seus produtos imediatamente após criar a conta.",
    },
    {
      q: "Posso cancelar a qualquer momento?",
      a: "Sim. Sua conta pode ser desativada quando desejar. Os dados do catálogo e do histórico de vendas permanecem acessíveis conforme a política de privacidade do serviço.",
    },
  ];

  const comments = [
    {
      author: "Carla M.",
      role: "Vendedora no Mercado Livre e Shopee",
      text: "Finalmente consigo ver o estoque unificado em todos os canais. O overselling sumiu do meu dia a dia.",
      rating: 5,
    },
    {
      author: "Roberto L.",
      role: "E-commerce de eletrônicos",
      text: "A sincronização automática com o ML economiza horas de trabalho manual por semana.",
      rating: 4,
    },
    {
      author: "Fernanda T.",
      role: "Loja de moda",
      text: "Implantação simples e suporte atencioso. Recomendo para quem vende em mais de um marketplace.",
      rating: 5,
    },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-canvas">
      <Navbar />

      <main className="flex-1">
        {/* ==================== HERO ==================== */}
        <section id="inicio" className="relative px-4 py-12 md:px-6 lg:py-20 overflow-hidden">
          <div className="mx-auto max-w-7xl">
            <div className="grid lg:grid-cols-2 gap-12 items-center">
              {/* Coluna de Texto */}
              <div className="text-center lg:text-left">
                <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold text-slate-900 tracking-tight leading-tight">
                  Estoque unificado,<br />
                  vendas sem surpresa.
                </h1>
                <p className="mt-6 text-lg md:text-xl text-slate-600 leading-relaxed max-w-2xl mx-auto lg:mx-0">
                  Sistema de orquestração e centralização de estoque para
                  vendedores que operam em múltiplos marketplaces. Controle SKU,
                  estoque e métricas de vendas em um só lugar, reduzindo o
                  risco de overselling e underselling.
                </p>
                <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center lg:justify-start">
                  <Link
                    to={paths.register}
                    onClick={() => navigate(paths.register)}
                    className="rounded-xl bg-brand-700 px-6 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-800 flex items-center justify-center gap-2"
                  >
                    <UserPlus aria-hidden="true" className="h-4 w-4" />
                    Criar conta grátis
                  </Link>
                  <Link
                    to={paths.login}
                    onClick={() => navigate(paths.login)}
                    className="rounded-xl bg-surface border border-line px-6 py-3 text-sm font-semibold text-slate-700 shadow-sm transition-colors hover:bg-slate-50 flex items-center justify-center gap-2"
                  >
                    <LogIn aria-hidden="true" className="h-4 w-4" />
                    Entrar
                  </Link>
                </div>
              </div>

              {/* Coluna da Imagem (Stock Image) */}
              <div className="relative flex justify-center lg:justify-end">
                <img
                  src="/assets/stockimage.jpeg"
                  alt="Ilustração de gestão e controle de estoque"
                  className="w-full max-w-lg lg:max-w-none h-auto rounded-2xl shadow-xl border border-line/50 object-cover"
                />
              </div>
            </div>
          </div>

          {/* Decorative grid background */}
          <div className="absolute inset-0 overflow-hidden pointer-events-none">
            <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-brand-100 blur-[120px] -z-10" />
            <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-slate-200/50 blur-[120px] -z-10" />
          </div>
        </section>

        {/* ==================== SOBRE ==================== */}
        <section id="sobre" className="px-4 py-16 md:px-6 lg:py-24 bg-surface">
          <div className="mx-auto max-w-3xl text-center md:text-left">
            <h2 className="text-3xl font-bold text-slate-900">Sobre o Stock Sync</h2>
            <p className="mt-4 text-lg text-slate-600 leading-relaxed">
              Vendedores que operam em mais de um canal de vendas enfrentam
              dois problemas recorrentes:
            </p>
            <div className="flex justify-center md:justify-start">
              <ul className="mt-6 space-y-3 text-slate-600 leading-relaxed text-left inline-block">
                <li className="flex items-start gap-3">
                  <Check className="h-5 w-5 text-brand-500 shrink-0 mt-0.5" />
                  <span>
                    <strong>Overselling:</strong> uma venda é feita sem
                    estoque disponível em outros canais.
                  </span>
                </li>
                <li className="flex items-start gap-3">
                  <Check className="h-5 w-5 text-brand-500 shrink-0 mt-0.5" />
                  <span>
                    <strong>Underselling:</strong> o estoque é mantido
                    excessivamente reservado e impede vendas em outros
                    marketplaces.
                  </span>
                </li>
              </ul>
            </div>
            <p className="mt-6 text-slate-600 leading-relaxed">
              O projeto nasceu para reduzir esse ruído operacional e dar
              uma visão unificada do estoque e da performance comercial,
              permitindo decisões operacionais com menos risco.
            </p>
          </div>
        </section>

        {/* ==================== COMENTÁRIOS (mock) ==================== */}
        <section id="comentarios" className="px-4 py-16 md:px-6 lg:py-24 bg-canvas">
          <div className="mx-auto max-w-7xl">
            <div className="text-center mb-12">
              <h2 className="text-2xl md:text-3xl font-bold text-slate-900">
                O que dizem quem já usa
              </h2>
              <p className="mt-3 text-slate-600">
                Depoimentos de vendedores que centralizaram o estoque com o
                Stock Sync.
              </p>
            </div>

            <div className="grid md:grid-cols-3 gap-6">
              {comments.map((comment, idx) => (
                <Card key={idx} className="p-5">
                  <CardBody className="p-0 pb-4">
                    <div className="flex items-center gap-2 text-yellow-400 mb-3">
                      {[1, 2, 3, 4, 5].map((star) => (
                        <span key={star} className="text-xs" aria-hidden="true">
                          {star <= comment.rating ? "★" : "☆"}
                        </span>
                      ))}
                    </div>
                    <p className="text-sm text-slate-600 leading-relaxed mb-4">
                      "{comment.text}"
                    </p>
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100">
                        <span className="text-xs font-semibold text-slate-700">
                          {comment.author.split(" ").map((n) => n[0]).join("")}
                        </span>
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-slate-900">
                          {comment.author}
                        </div>
                        <div className="text-xs text-slate-500">{comment.role}</div>
                      </div>
                    </div>
                  </CardBody>
                </Card>
              ))}
            </div>
          </div>
        </section>

        {/* ==================== FAQ ==================== */}
        <section id="faq" className="px-4 py-16 md:px-6 lg:py-24 bg-surface">
          <div className="mx-auto max-w-3xl">
            <div className="text-center mb-12">
              <h2 className="text-2xl md:text-3xl font-bold text-slate-900">
                Perguntas frequentes
              </h2>
              <p className="mt-3 text-slate-600">
                Tudo o que você precisa saber antes de começar.
              </p>
            </div>

            <div className="space-y-3">
              {faqs.map((faq, idx) => (
                <Card key={idx} className="overflow-hidden">
                  <CardBody className="p-0">
                    <button
                      onClick={() => toggleFaq(idx)}
                      className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition-colors hover:bg-slate-50"
                      aria-expanded={openFaq === idx}
                      aria-controls={`faq-panel-${idx}`}
                    >
                      <span className="text-sm font-medium text-slate-900">
                        {faq.q}
                      </span>
                      <ChevronDown
                        className={`h-4 w-4 shrink-0 transition-transform ${
                          openFaq === idx ? "rotate-180" : ""
                        } text-slate-400`}
                      />
                    </button>
                    {openFaq === idx && (
                      <div
                        id={`faq-panel-${idx}`}
                        className="px-5 pb-4"
                        aria-hidden={openFaq !== idx}
                      >
                        <p className="text-sm text-slate-600 leading-relaxed">
                          {faq.a}
                        </p>
                      </div>
                    )}
                  </CardBody>
                </Card>
              ))}
            </div>
          </div>
        </section>

        {/* ==================== SUPORTE (mock) ==================== */}
        <section id="suporte" className="px-4 py-16 md:px-6 lg:py-24 bg-canvas">
          <div className="mx-auto max-w-3xl">
            <div className="text-center mb-12">
              <h2 className="text-2xl md:text-3xl font-bold text-slate-900">
                Precisa de ajuda?
              </h2>
              <p className="mt-3 text-slate-600">
                Nossa equipe está à disposição para tirar suas dúvidas.
              </p>
            </div>

            <Card className="p-6 md:p-8">
              <CardBody className="p-0">
                <div className="grid md:grid-cols-2 gap-8">
                  <div className="space-y-6">
                    <div className="flex items-start gap-4">
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-100 text-brand-700 shrink-0">
                        <Mail className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="text-base font-semibold text-slate-900">
                          E-mail de suporte
                        </h3>
                        <p className="mt-1 text-sm text-slate-600">
                          suporte@stocksync.com.br
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-4">
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-100 text-brand-700 shrink-0">
                        <Phone className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="text-base font-semibold text-slate-900">
                          Telefone
                        </h3>
                        <p className="mt-1 text-sm text-slate-600">
                          (11) 3000-0000
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-4">
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-100 text-brand-700 shrink-0">
                        <ShieldCheck className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="text-base font-semibold text-slate-900">
                          Centro de ajuda
                        </h3>
                        <p className="mt-1 text-sm text-slate-600">
                          Documentação e tutoriais de integração.
                        </p>
                      </div>
                    </div>
                  </div>

                  <div>
                    <h3 className="text-base font-semibold text-slate-900 mb-4">
                      Fale conosco
                    </h3>
                    <p className="text-sm text-slate-600 mb-6">
                      Envie sua mensagem e retornaremos em até 1 dia útil.
                    </p>
                    <form className="space-y-4" noValidate onSubmit={(e) => e.preventDefault()}>
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-slate-700">
                          Seu e-mail
                        </label>
                        <input
                          type="email"
                          className="rounded-lg border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                          placeholder="seu@email.com"
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-slate-700">
                          Mensagem
                        </label>
                        <textarea
                          rows={4}
                          className="rounded-lg border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                          placeholder="Como podemos ajudar?"
                        />
                      </div>
                      <Button type="submit" className="w-full rounded-full">
                        Enviar mensagem
                      </Button>
                    </form>
                  </div>
                </div>
              </CardBody>
            </Card>
          </div>
        </section>
      </main>

      <footer className="border-t border-line bg-surface px-4 py-8 md:px-6">
        <div className="mx-auto max-w-7xl flex flex-col items-center justify-center gap-4">
          <div className="flex items-center gap-2">
            <img
              src="/assets/logo.png"
              alt="Stock Sync Logo"
              className="h-5 w-auto object-contain"
            />
            <span className="text-sm font-semibold text-slate-900">Stock Sync</span>
          </div>
          <p className="text-xs text-slate-500 text-center">
            Orquestração e centralização de estoque para marketplaces.
          </p>
        </div>
      </footer>
    </div>
  );
}