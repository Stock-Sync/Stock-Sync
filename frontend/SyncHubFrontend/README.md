# StockSync — Frontend

Painel web do StockSync: gestão de catálogo, lojas (marketplaces) e anúncios.
Faz parte do monorepo `frontend_06`, junto dos microservices FastAPI em
`../../services/`.

React 19 · TypeScript · Vite 8 · Tailwind CSS v4 · React Query · React Router

---

## Como rodar

```bash
npm install
npm run dev      # http://localhost:8000
```

| Script | O que faz |
|---|---|
| `npm run dev` | Servidor de desenvolvimento na porta **8000** |
| `npm run build` | `tsc -b` + build de produção em `dist/` |
| `npm run preview` | Serve o `dist/` na porta 8000 |
| `npm run typecheck` | Só `tsc -b` |
| `npm run lint` / `lint:fix` | ESLint (configuração flat) |
| `npm test` | Vitest, uma passada |
| `npm run test:watch` | Vitest em modo watch |
| `npm run format` / `format:check` | Prettier |

Não há variáveis de ambiente ainda: a aplicação roda inteiramente sobre dados
mockados (ver [Estado atual](#estado-atual)).

---

## Estado atual

**A aplicação roda 100% sobre dados mockados no navegador.** Não existe chamada
de rede para o backend. Isso é uma decisão consciente de sequência de trabalho,
não um esquecimento — ver [Roadmap](#roadmap).

O que já existe no backend (`../../services/catalog-service`) cobre apenas
produtos, SKUs e mapeamentos de plataforma. Autenticação, lojas, pedidos e
notificações **não têm** endpoint, então foram simulados no frontend.

### O que funciona hoje

- Navegação completa entre as telas, com sidebar e topo fixos
- Cadastro, edição, busca, visualização em grade/tabela e apagar produto
- Persistência em `localStorage`: o que você cria sobrevive ao recarregamento
- Fluxo de login com guarda de rota e retorno à rota original
- Tabelas de lojas, anúncios e pedidos com estados vazios tratados
- Busca global no topo filtrando produtos, lojas e anúncios
- "Sincronizar Tudo" e "Anunciar agora" gerando anúncios simulados
- Toasts de feedback, diálogo de confirmação antes de apagar, estados de carga

### O que ainda NÃO funciona (e por quê)

| Área | Situação | Causa |
|---|---|---|
| Login | Qualquer usuário/senha não-vazio entra; e-mail sempre vazio | Sem endpoint de autenticação |
| Sessão | `localStorage`, some ao limpar o navegador | Idem |
| Lojas | CRUD local, sem conexão OAuth com marketplace | Sem entidade `Store` no backend |
| Anúncios | Criados pelo mock ao sincronizar, não publicados de verdade | `sync-service` só tem `/health` |
| Pedidos | Tabela somente leitura com um registro de exemplo | `sales-service` só tem `/health` |
| Notificações | Sempre vazias (estado "Nenhuma notificação recente") | Não existe entidade no backend |
| Busca global | Filtra os dados já carregados, sem debounce nem paginação | Sem endpoint de busca |
| Exclusão de loja | Existe no mock, sem botão na UI | Depende de confirmação de produto |
| Métricas do dashboard | Contagens reais sobre o mock, não vendas do dia | `SaleMetric` não tem rota |
| Paginação | Todos os endpoints mockados devolvem a lista inteira | Backend também não pagina |
| i18n | Textos pt-BR fixos no JSX | Segue a convenção atual do repositório |

---

## Arquitetura

```
src/
├─ App.tsx              # QueryClientProvider + HashRouter + AuthProvider
├─ main.tsx
├─ index.css            # Design system: tokens @theme do Tailwind v4
│
├─ routes/              # paths.ts (constantes) + index.tsx (rotas)
│
├─ types/               # Tipos que ESPELHAM os schemas do backend
│  ├─ catalog.ts        #   Product, SKU, PlatformMapping, Platform
│  ├─ entities.ts       #   Store, Order, Notification (ainda sem backend)
│  ├─ user.ts           #   User
│  ├─ view-models.ts    #   ProductView + tipos de formulário
│  └─ api.ts            #   ApiError (envelope de erro do backend)
│
├─ lib/
│  ├─ api/client.ts     # CONTRATO do cliente de dados (interface ApiClient)
│  ├─ storage.ts        # localStorage namespaced "stocksync:*"
│  ├─ format.ts         # moeda BRL, datas pt-BR, iniciais
│  └─ cn.ts             # clsx + tailwind-merge
│
├─ mock/                # Implementação do ApiClient sobre dados em memória
│  ├─ db.ts             #   Seed (produto "rafael", usuário "amoras")
│  └─ handlers.ts       #   CRUD + persistência + sync simulado
│
├─ auth/                # Sessão mockada
│  ├─ auth-context.ts   #   Context + useAuth (sem JSX)
│  ├─ AuthProvider.tsx  #   Provider
│  └─ RequireAuth.tsx   #   Guarda de rota
│
├─ components/
│  ├─ ui/               # Button, Input, Select, Textarea, Card, Table,
│  │                    # Badge, Avatar, EmptyState, ConfirmDialog, Fab,
│  │                    # Spinner, PageHeader, Toast
│  └─ layout/           # AppShell, Sidebar, Topbar, UserMenu, GlobalSearch
│
├─ features/            # Uma pasta por área de tela
│  ├─ auth/             #   LoginPage
│  ├─ dashboard/        #   DashboardPage + queries de pedidos/notificações
│  ├─ products/         #   lista, formulário, detalhe + queries
│  ├─ stores/           #   StoresPage, StoreFormPage, StoresTable
│  ├─ listings/         #   ListingsPage
│  ├─ orders/           #   OrdersPage
│  ├─ profile/          #   ProfilePage
│
├─ hooks/               # use-disclosure (popovers)
└─ test/                # setup.ts + utils.tsx (helpers de render)
```

### Decisões que valem explicar

**Types espelham o backend, telas não.** O backend separa `Product`
(`name`, `description`) de `SKU` (`internal_sku`, `price`), mas as telas mostram
tudo em um registro. `types/view-models.ts` tem o `ProductView` achatado e a
função `toProductView()` que faz a junção. O Benefit: quando o cliente HTTP
real entrar, ele devolve `Product` e `SKU` separados e nada na camada de tela
muda.

**`lib/api/client.ts` é o ponto de troca.** Nenhuma tela importa o mock
diretamente — todas dependem da interface `ApiClient`. Hoje `mock/handlers.ts`
a implementa; amanhã um `http-client.ts` faz o mesmo com `fetch`. O envelope de
erro (`ApiError`) já segue o formato de `app/api/handlers.py` dos serviços, com
`not_found`, `conflict`, `validation_error`.

**HashRouter.** As telas de referência usam `localhost:8000/#`. Com hash, o
build funciona em qualquer servidor estático sem regra de rewrite.

**Context separado de Provider.** A regra `react-refresh/only-export-components`
proíbe exportar hooks junto de componentes, então `auth-context.ts` e
`toast-context.ts` ficam em arquivos `.ts` próprios.

**`camelcase` desligada em arquivos de dados.** `eslint.config.js` tem um bloco
de override para `types/`, `mock/` e `queries.ts`: eles usam `snake_case` de
propósito, para espelhar os schemas Python. Renomear quebraria a troca pelo
cliente real.

**Formulário de produto.** `ProductFormPage` monta `ProductFormFields` com uma
`key` que muda quando o produto carrega, em vez de sincronizar estado por
efeito. Evita o padrão de `setState` dentro de `useEffect`.

---

## Telas

| Rota | Arquivo | Situação |
|---|---|---|
| `/` | `features/dashboard/DashboardPage` | Completa (métricas sobre mock) |
| `/login` | `features/auth/LoginPage` | Completa (validação, sem backend) |
| `/products` | `features/products/ProductsListPage` | Completa |
| `/products/new` | `features/products/ProductFormPage` | Completa |
| `/products/:id` | `features/products/ProductDetailPage` | Completa |
| `/products/:id/edit` | `features/products/ProductFormPage` | Completa |
| `/profile` | `features/profile/ProfilePage` | Completa (e-mail vazio) |
| `/stores` | `features/stores/StoresPage` | Lista; sem remover |
| `/stores/new` | `features/stores/StoreFormPage` | Completa |
| `/listings` | `features/listings/ListingsPage` | Funcional sobre mock |
| `/orders` | `features/orders/OrdersPage` | Somente leitura |

Sidebar (de cima para baixo): Início, Produtos, Lojas, Anúncios. Existe um
quinto ícone no design original cuja função ainda não foi definida — não foi
implementado.

Rotas liberadas sem sessão: `/`, `/login`, `/products`, `/products/:id`. As
demais passam por `RequireAuth`, que redireciona para o login guardando o
destino em `location.state.from`; após autenticar, o usuário volta para onde
ia.

---

## Testes

29 testes em 5 arquivos, cobrindo o fluxo que quebraria primeiro se regredisse:

- `routes/routes.test.tsx` — rotas liberadas vs. protegidas, estado de visitante
  vs. autenticado, redirecionamento de rota inexistente
- `auth/RequireAuth.test.tsx` — guarda com e sem sessão
- `features/auth/LoginPage.test.tsx` — validação, persistência da sessão e
  retorno à rota original
- `features/products/ProductFormPage.test.tsx` — campos obrigatórios, preço
  negativo, SKU duplicado, criação e edição, hidratação do storage
- `features/products/ProductsListPage.test.tsx` — seed, filtro, alternância
  de visão e confirmação de exclusão

Helpers em `src/test/utils.tsx`: `renderWithProviders` (QueryClient + Router +
providers) e `renderAtRoute` (para rotas com `:id`). O `db` do mock é um
singleton de módulo e o Vitest roda com `isolate: false`, então cada suíte
chama `resetDatabase()` no `beforeEach`.

---

## Roadmap

### 1. Backend — o que precisa existir

Ordem sugerida, cada item desbloqueia a linha correspondente.

**Autenticação.** Modelo de usuário, `POST /auth/login` (JWT), `GET /auth/me`,
`POST /auth/logout`. Enquanto isso não existir, `AuthProvider.login()` continua
aceitando qualquer credencial.

**CORS.** Nenhum serviço configura `CORSMiddleware`, então chamadas
cross-origin de `localhost:8000` vão falhar. Alternativa: `server.proxy` no
`vite.config.ts`.

**Lojas.** Entidade `Store` + rotas CRUD. Hoje `Store` existe só em
`types/entities.ts`.

**Sincronização.** `sync-service` e `integrations-service` só têm `/health`;
faltam as rotas de `SyncEvent` e publicação real nos marketplaces.

**Pedidos e métricas.** `sales-service` precisa expor `Order` e `SaleMetric`
para a tabela de pedidos virar leitura real e o dashboard mostrar vendas do dia.

**Paginação e busca.** Todos os endpoints devolvem a lista inteira. Com volume
real isso quebra a listagem e a busca global.

### 2. Frontend — trocas necessárias

**Trocar o cliente de dados.** O passo principal. Escrever a implementação
HTTP de `ApiClient` em `lib/api/http-client.ts` e apontar `api` em
`mock/handlers.ts` para ela. Nenhuma tela muda. Considerar axios, já que o
`fetch` puro exige wrapper de interceptador para o `Authorization`.

**Revogar o mock.** Depois da troca, `mock/db.ts` e `mock/handlers.ts` saem —
exceto `hydrate()`/`clearPersisted()`, que viram lixo. Atualizar
`test/setup.ts` e os testes que dependem do seed.

**VARIÁVEIS DE AMBIENTE.** `VITE_API_URL` por ambiente. Hoje não há `.env`
nenhum; criar `.env.example`.

**Modelo de usuário no perfil.** `user.email` está fixo como string vazia; com
`GET /auth/me` passa a vir do servidor.

**Camada de visão.** Se `ProductView` deixar de servir, mover a junção
Product+SKU para um `select` do backend e tratar `GET /products` como
paginado.

**Estados de erro reais.** As telas já tractam `error` das queries, mas não há
tela 404 nem retry. O `ApiError.code` permite diferenciar `conflict` de
`validation_error`.

**Acessibilidade pendente.** Faltam rótulos em alguns cliques por ícone
(`Sidebar` usa `title`, não `aria-label`), navegação por teclado nos popovers e
`aria-current` nos itens da sidebar.

**Testes que faltam.** Telas de loja, anúncio, pedido e dashboard; busca global;
menu do usuário; `Toasts`.

**Qualidade.** `strict` está desligado no `tsconfig.app.json` (escolha atual).
`format:check` falha em vários arquivos — Prettier com `printWidth: 80` versus o
estilo do código. Alinhar um dos dois. `noUncheckedIndexedAccess` e alias `@/`
também não estão ativados.

**Infraestrutura.** Não há CI, apesar de o README raiz mencionar GitHub
Actions. Sem `.github/workflows` hoje. Também falta um serviço do frontend no
`docker-compose.yml` (hoje só Postgres e os 4 serviços Python), e o
`REDIS_URL` referenciado pelo `sync-service` não tem serviço correspondente.

### 3. Design

**Definir o quinto ícone** da sidebar.

**Fidelidade visual.** O layout foi montado a partir de descrição em texto dos
mockups, não dos arquivos de imagem. Espaçamento, tom exato do teal e ícones
ainda precisam de conferência contra o design — e de um_tokens de espaçamento no
`@theme`.

**Responsividade.** Sidebar colapsa para 64px abaixo de `md`. Avaliar se vira
drawer no mobile.

**Estados de carregamento.** Hoje são blocos genéricos; vale um skeleton por
tipo de tela.