import { DndContext, DragOverlay, PointerSensor, useSensor, useSensors,
         type DragEndEvent, type DragStartEvent } from '@dnd-kit/core'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, destinoPasta, type Botao, type Catalogo, type ItemBib, type PaginaDet, type Tudo } from './api'
import Biblioteca from './Biblioteca'
import { Avisos, CatalogoCtx, Glifo, useAviso } from './comum'
import Inspector from './Inspector'
import Modulos from './Modulos'
import Placa from './Placa'

const GRADES: [number, number][] = [[3, 2], [4, 2], [4, 3], [5, 3], [5, 4]]

export default function App() {
  return <Avisos><Janela /></Avisos>
}

type Arrasto = { tipo: 'card'; id: string; art: string } | { tipo: 'bib'; item: ItemBib }

function Janela() {
  const avisar = useAviso()
  const [tudo, setTudo] = useState<Tudo | null>(null)
  const [semNucleo, setSemNucleo] = useState(false)
  const [cat, setCat] = useState<Catalogo | null>(null)
  const [apps, setApps] = useState<string[]>([])
  const [vista, setVista] = useState<'painel' | 'modulos'>('painel')
  const [editando, setEditando] = useState(true)
  const [det, setDet] = useState<PaginaDet | null>(null)
  const [sel, setSel] = useState<string | null>(null)
  const [arrasto, setArrasto] = useState<Arrasto | null>(null)
  const sensores = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))

  // a janela espelha a placa: o nucleo e consultado o tempo todo
  useEffect(() => {
    let vivo = true
    const puxa = () => api.tudo()
      .then(t => { if (vivo) { setTudo(t); setSemNucleo(false) } })
      .catch(() => vivo && setSemNucleo(true))
    puxa()
    const id = setInterval(puxa, 600)
    return () => { vivo = false; clearInterval(id) }
  }, [])

  const chaveCat = tudo ? JSON.stringify([tudo.modulos.map(m => m.ligado), tudo.pacotes.map(p => p.ativo)]) : ''
  useEffect(() => { if (chaveCat) api.catalogo().then(setCat).catch(() => {}) }, [chaveCat])
  useEffect(() => { api.apps().then(setApps).catch(() => {}) }, [])

  const pagina = tudo?.pagina ?? ''
  const assinatura = tudo ? pagina + tudo.layout.buttons.map(b => b.art).join() : ''
  const recarregaDet = useCallback(() => {
    if (pagina) api.pagina(pagina).then(setDet).catch(() => setDet(null))
  }, [pagina])
  useEffect(() => { recarregaDet() }, [assinatura, recarregaDet])
  useEffect(() => { setSel(null) }, [pagina])

  const botaoSel = sel ? det?.botoes.find(b => b?.id === sel) ?? null : null
  useEffect(() => { if (sel && det && !botaoSel) setSel(null) }, [sel, det, botaoSel])

  const pastas = useMemo(() => {
    const s = new Set<string>()
    for (const b of det?.botoes ?? []) if (b?.id && destinoPasta(b, tudo?.paginas ?? [], pagina)) s.add(b.id)
    return s
  }, [det, tudo, pagina])

  const erro = useCallback((e: unknown) => avisar(e instanceof Error ? e.message : String(e), 'erro'), [avisar])

  const desfazer = useCallback(() => api.desfazer().then(() => avisar('Desfeito')).catch(erro), [avisar, erro])
  const refazer = useCallback(() => api.refazer().then(() => avisar('Refeito')).catch(erro), [avisar, erro])

  // atalhos: Ctrl+Z, Ctrl+Y, Delete, Esc (fora de campos de texto)
  useEffect(() => {
    const ouve = (e: KeyboardEvent) => {
      const alvo = e.target as HTMLElement
      if (alvo.closest('input, textarea, select')) return
      if (e.ctrlKey && e.key.toLowerCase() === 'z' && !e.shiftKey) { e.preventDefault(); desfazer() }
      else if (e.ctrlKey && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z'))) { e.preventDefault(); refazer() }
      else if (e.key === 'Escape') setSel(null)
      else if (e.key === 'Delete' && sel && botaoSel?._fixo) {
        api.apagar(pagina, sel).then(() => { avisar('Botão apagado. Ctrl+Z desfaz.'); setSel(null) }).catch(erro)
      }
    }
    window.addEventListener('keydown', ouve)
    return () => window.removeEventListener('keydown', ouve)
  }, [desfazer, refazer, sel, botaoSel, pagina, avisar, erro])

  async function poe(item: ItemBib, pos: number) {
    try {
      if (item.pasta) {
        const r = await api.pasta(pagina, pos, 'Pasta')
        setSel(r.id); avisar('Pasta criada. Solte botões em cima dela para guardar lá dentro.')
      } else {
        const r = await api.salvar(pagina, structuredClone(item.botao) as Botao, pos)
        setSel(r.id); avisar(`${item.nome} adicionado`)
      }
    } catch (e) { erro(e) }
  }

  function adicionar(item: ItemBib) {
    if (!tudo) return
    const { cols, rows } = tudo.layout.grid
    const livre = Array.from({ length: cols * rows }, (_, i) => i)
      .find(i => !tudo.layout.buttons[i] || tudo.layout.buttons[i].id === '_vazio')
    if (livre === undefined) { avisar('Esta página está cheia. Aumente a grade ou apague um botão.', 'erro'); return }
    poe(item, livre)
  }

  function comecou(e: DragStartEvent) {
    const d = e.active.data.current as { tipo: string; item?: ItemBib; id?: string }
    if (d.tipo === 'bib' && d.item) setArrasto({ tipo: 'bib', item: d.item })
    if (d.tipo === 'card' && d.id) {
      const art = tudo?.layout.buttons.find(b => b.id === d.id)?.art ?? ''
      setArrasto({ tipo: 'card', id: d.id, art })
    }
  }

  function soltou(e: DragEndEvent) {
    const a = arrasto
    setArrasto(null)
    const sobre = e.over?.data.current as { pos: number; botao: string | null } | undefined
    if (!a || !sobre) return
    if (a.tipo === 'bib') {
      if (!sobre.botao) poe(a.item, sobre.pos)
      else avisar('Solte num quadrado vazio.', 'erro')
      return
    }
    if (sobre.botao === a.id) return
    const destino = sobre.botao && pastas.has(sobre.botao)
      ? destinoPasta(det?.botoes.find(b => b?.id === sobre.botao), tudo?.paginas ?? [], pagina) : null
    if (destino) {
      api.paraPasta(pagina, a.id, destino).then(() => avisar('Guardado na pasta')).catch(erro)
    } else {
      api.mover(pagina, a.id, sobre.pos).catch(erro)
    }
  }

  if (!tudo) {
    return <div className="carregando">{semNucleo
      ? 'O TELINHA não está rodando. Ligue pelo ícone da bandeja e esta janela conecta sozinha.'
      : 'Conectando ao TELINHA…'}</div>
  }

  const paginaInfo = tudo.paginas.find(p => p.id === pagina)
  const suas = tudo.paginas.filter(p => !p.pacote)
  const dePacotes = tudo.paginas.filter(p => p.pacote)
  const grade = tudo.layout.grid

  return (
    <CatalogoCtx.Provider value={cat}>
      <DndContext sensors={sensores} onDragStart={comecou} onDragEnd={soltou} onDragCancel={() => setArrasto(null)}>
        <div className={'app' + (vista === 'modulos' ? ' sem-lado' : '')}>
          <header className="topo">
            <div className="marca"><span className="marca-t">T</span>TELINHA</div>
            <nav className="vistas">
              <button className={vista === 'painel' ? 'on' : ''} onClick={() => setVista('painel')}>Painel</button>
              <button className={vista === 'modulos' ? 'on' : ''} onClick={() => setVista('modulos')}>Módulos</button>
            </nav>
            <div className="espaco" />
            {semNucleo && <span className="alerta">Sem resposta do núcleo</span>}
            {vista === 'painel' && (<>
              <div className="historico">
                <button onClick={desfazer} disabled={!tudo.pode_desfazer} title="Desfazer (Ctrl+Z)" aria-label="Desfazer">↶</button>
                <button onClick={refazer} disabled={!tudo.pode_refazer} title="Refazer (Ctrl+Y)" aria-label="Refazer">↷</button>
              </div>
              <div className="modo" role="group" aria-label="Modo">
                <button className={editando ? 'on' : ''} onClick={() => setEditando(true)}>Editar</button>
                <button className={!editando ? 'on' : ''} onClick={() => { setEditando(false); setSel(null) }}>Usar</button>
              </div>
            </>)}
          </header>

          {vista === 'modulos' ? (
            <main className="palco-mod"><Modulos tudo={tudo} apps={apps} paginas={tudo.paginas} /></main>
          ) : (<>
            <aside className="lado">
              <ListaPaginas titulo="Suas páginas" paginas={suas} atual={pagina} />
              {dePacotes.length > 0 && <ListaPaginas titulo="De pacotes" paginas={dePacotes} atual={pagina} />}
              <button className="nova-pagina" onClick={() => api.paginaNova('Página nova')
                .then(r => { api.navegar(r.pagina); avisar('Página criada') }).catch(erro)}>
                Nova página
              </button>
            </aside>

            <main className="bancada">
              <div className="pagina-barra">
                <EditaTitulo key={pagina} valor={paginaInfo?.titulo ?? pagina}
                             onSalva={t => api.paginaEditar(pagina, { titulo: t }).catch(erro)} />
                {det?.gerar && <span className="etiqueta">Botões gerados automaticamente</span>}
                <div className="espaco" />
                <label className="grade-sel">Grade
                  <select value={`${grade.cols}x${grade.rows}`} onChange={e => {
                    const [c, r] = e.target.value.split('x').map(Number)
                    api.paginaEditar(pagina, { grade: { cols: c, rows: r } }).catch(erro)
                  }}>
                    {GRADES.map(([c, r]) => <option key={`${c}x${r}`} value={`${c}x${r}`}>{c} × {r}</option>)}
                    {!GRADES.some(([c, r]) => c === grade.cols && r === grade.rows) &&
                      <option value={`${grade.cols}x${grade.rows}`}>{grade.cols} × {grade.rows}</option>}
                  </select>
                </label>
                {paginaInfo?.do_usuario && pagina !== tudo.inicio && pagina !== 'descanso' && (
                  <button className="discreto" onClick={() => {
                    if (confirm(`Apagar a página “${paginaInfo.titulo}” e os botões que levam a ela?`))
                      api.paginaApagar(pagina).then(() => avisar('Página apagada. Ctrl+Z desfaz.')).catch(erro)
                  }}>Apagar página</button>
                )}
              </div>
              <Placa tudo={tudo} editando={editando} selecionado={sel} pastas={pastas}
                     arrastando={arrasto?.tipo ?? null}
                     onClique={(_pos, id) => {
                       if (!editando) { if (id) api.toque(pagina, id); return }
                       setSel(id)
                     }}
                     onDuplo={id => api.toque(pagina, id)} />
              <p className="dica">
                {editando
                  ? 'Clique para editar e dê duplo clique para testar. Arraste para trocar de lugar ou guardar numa pasta.'
                  : 'Clicar num botão é o mesmo que tocar na placa.'}
              </p>
            </main>

            <aside className="direita">
              {botaoSel && editando
                ? <Inspector key={botaoSel.id} pagina={pagina} botao={botaoSel}
                             gerado={!!det?.gerar && !botaoSel._fixo}
                             pasta={destinoPasta(botaoSel, tudo.paginas, pagina)}
                             apps={apps} paginas={tudo.paginas} estado={tudo.estado}
                             onFechar={() => setSel(null)}
                             onApagar={() => api.apagar(pagina, botaoSel.id!)
                               .then(() => { avisar('Botão apagado. Ctrl+Z desfaz.'); setSel(null) }).catch(erro)} />
                : <Biblioteca apps={apps} onAdicionar={adicionar} />}
            </aside>
          </>)}
        </div>

        <DragOverlay dropAnimation={null}>
          {arrasto?.tipo === 'card' && <img className="fantasma-card" src={api.arte(arrasto.art)} alt="" />}
          {arrasto?.tipo === 'bib' && (
            <div className="fantasma-bib" style={{ borderColor: arrasto.item.botao.aparencia.color }}>
              {arrasto.item.icone_app
                ? <img src={api.iconeApp(arrasto.item.icone_app)} alt="" />
                : <Glifo nome={arrasto.item.icone ?? arrasto.item.botao.aparencia.icon} tam={30}
                         cor={arrasto.item.botao.aparencia.color} />}
              <span>{arrasto.item.nome}</span>
            </div>
          )}
        </DragOverlay>
      </DndContext>
    </CatalogoCtx.Provider>
  )
}

function ListaPaginas({ titulo, paginas, atual }: { titulo: string; paginas: Tudo['paginas']; atual: string }) {
  return (
    <section className="lista-paginas">
      <h3>{titulo}</h3>
      {paginas.map(p => (
        <button key={p.id} className={'pagina-item' + (p.id === atual ? ' atual' : '')}
                aria-current={p.id === atual} onClick={() => api.navegar(p.id)}>
          <span>{p.titulo}</span>
          {p.gerada && <small>automática</small>}
        </button>
      ))}
    </section>
  )
}

function EditaTitulo({ valor, onSalva }: { valor: string; onSalva: (t: string) => void }) {
  const [t, setT] = useState(valor)
  useEffect(() => setT(valor), [valor])
  return (
    <input className="titulo-pagina" value={t} aria-label="Nome da página"
           onChange={e => setT(e.target.value)}
           onBlur={() => t.trim() && t !== valor && onSalva(t.trim())}
           onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }} />
  )
}
