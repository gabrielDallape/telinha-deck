// Conversa com o nucleo (telinha/api.py). O token vem na URL que o app abre.
const TOKEN = new URLSearchParams(location.search).get('token') ?? ''

export type BotaoLayout = { id: string; art: string; art_on: string; state_key: string }
export type Layout = {
  page: string; title: string; back: string
  grid: { cols: number; rows: number }
  buttons: BotaoLayout[]; _vivos: Record<string, string>
}
export type Passo = { type: string; [k: string]: unknown }
export type Aparencia = {
  widget?: string; icon?: string; icon_app?: string; label?: string; label_on?: string
  sub?: string; color?: string; estilo?: string; [k: string]: unknown
}
export type Botao = {
  id?: string
  aparencia: Aparencia
  toque: Passo[]
  aceso?: string
  depois?: string
  _fixo?: boolean
  [k: string]: unknown
}
export type PaginaInfo = {
  id: string; titulo: string; pacote: string; gerada: boolean; voltar: string; do_usuario: boolean
}
export type Tudo = {
  conectado: boolean; porta: string; fw: string; pagina: string; inicio: string
  layout: Layout; barra: string; estado: Record<string, unknown>
  paginas: PaginaInfo[]
  modulos: { id: string; nome: string; ligado: boolean; erro: string }[]
  pacotes: { id: string; nome: string; instalado: boolean; ativo: boolean }[]
  pode_desfazer: boolean; pode_refazer: boolean
}
export type PaginaDet = Layout & { botoes: (Botao | null)[]; gerar: string; pacote: string; do_usuario: boolean }
export type Campo = {
  tipo: 'texto' | 'numero' | 'bool' | 'app' | 'tecla' | 'pagina' | 'opcoes' | 'arquivo' | 'json' | 'lista' | 'pasta' | 'segredo' | 'grupo'
  rotulo: string; padrao?: unknown; opcoes?: [string, string][]
}
export type Acao = { id: string; modulo: string; rotulo: string; campos?: Record<string, Campo> | null }
export type ItemBib = {
  id: string; nome: string; descricao: string; categoria: string; modulo?: string
  icone?: string; icone_app?: string; pede?: string; pasta?: boolean; botao: Botao
}
export type Catalogo = {
  widgets: { id: string; modulo: string; nome: string }[]
  acoes: Acao[]
  icones: { nome: string; cp: number }[]
  biblioteca: ItemBib[]
}
export type ModuloInfo = {
  id: string; nome: string; versao: string; ligado: boolean; erro: string
  config: Record<string, Campo>; valores: Record<string, unknown>; itens: number
}

async function req<T>(caminho: string, corpo?: unknown): Promise<T> {
  const r = await fetch(caminho, {
    method: corpo === undefined ? 'GET' : 'POST',
    headers: { 'x-token': TOKEN, 'content-type': 'application/json' },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  })
  if (!r.ok) {
    let msg = `${r.status}`
    try { msg = (await r.json()).detail ?? msg } catch { /* corpo sem json */ }
    throw new Error(msg)
  }
  return r.json()
}

export const api = {
  tudo: () => req<Tudo>('/api/tudo'),
  pagina: (id: string) => req<PaginaDet>(`/api/pagina/${encodeURIComponent(id)}`),
  catalogo: () => req<Catalogo>('/api/catalogo'),
  apps: () => req<string[]>('/api/apps'),
  modulos: () => req<ModuloInfo[]>('/api/modulos'),
  toque: (pagina: string, botao: string) => req('/api/toque', { pagina, botao }),
  navegar: (pagina: string) => req('/api/navegar', { pagina }),
  salvar: (pagina: string, botao: Botao, pos?: number) =>
    req<{ ok: boolean; id: string }>('/api/botao', { pagina, botao, pos }),
  apagar: (pagina: string, botao: string) => req('/api/apagar', { pagina, botao }),
  mover: (pagina: string, botao: string, pos: number) => req('/api/mover', { pagina, botao, pos }),
  paraPasta: (pagina: string, botao: string, destino: string) => req('/api/para_pasta', { pagina, botao, destino }),
  pasta: (pagina: string, pos: number, titulo: string) =>
    req<{ ok: boolean; pagina: string; id: string }>('/api/pasta', { pagina, pos, titulo }),
  paginaNova: (titulo: string) => req<{ ok: boolean; pagina: string }>('/api/pagina_nova', { titulo }),
  paginaEditar: (pagina: string, mud: { titulo?: string; grade?: { cols: number; rows: number } }) =>
    req('/api/pagina_editar', { pagina, ...mud }),
  paginaApagar: (pagina: string) => req('/api/pagina_apagar', { pagina }),
  desfazer: () => req('/api/desfazer', {}),
  refazer: () => req('/api/refazer', {}),
  modulo: (id: string, cfg: Record<string, unknown>) => req('/api/modulo', { id, cfg }),
  pacote: (id: string, ativo: boolean) => req('/api/pacote', { id, ativo }),
  previa: async (pagina: string, botao: Botao, aceso = false) => {
    const r = await fetch('/api/previa', {
      method: 'POST', headers: { 'x-token': TOKEN, 'content-type': 'application/json' },
      body: JSON.stringify({ pagina, botao, aceso }),
    })
    if (!r.ok) throw new Error(String(r.status))
    return URL.createObjectURL(await r.blob())
  },
  arte: (c: string, v?: string) =>
    `/api/arte?c=${encodeURIComponent(c)}${v ? `&v=${encodeURIComponent(v)}` : ''}&token=${TOKEN}`,
  iconeApp: (nome: string) => `/api/icone_app?nome=${encodeURIComponent(nome)}&token=${TOKEN}`,
}

// Um botao "leva para uma pasta" quando o unico passo vai para uma pagina
// que tem esta como "voltar" - e o que o editor cria ao fazer uma pasta.
export function destinoPasta(b: Botao | null | undefined, paginas: PaginaInfo[], atual: string) {
  if (!b || b.toque.length !== 1 || b.toque[0].type !== 'page') return null
  const alvo = paginas.find(p => p.id === b.toque[0].page)
  return alvo && alvo.voltar === atual && alvo.do_usuario ? alvo.id : null
}
