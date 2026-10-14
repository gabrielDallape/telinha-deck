import { useDraggable } from '@dnd-kit/core'
import { useMemo, useState } from 'react'
import { api, type ItemBib } from './api'
import { Glifo, useCatalogo } from './comum'

// Ordem em que as categorias aparecem: do que mais se usa ao que menos se usa
const ORDEM = ['Claude Code', 'Áudio', 'Mídia', 'Apps e atalhos', 'Live', 'Informação', 'Sistema',
               'Navegação', 'Pacotes de apps']

export function itemDeApp(nome: string): ItemBib {
  return {
    id: `app:${nome}`, nome, descricao: 'Abre o app, ou traz para a frente se já estiver aberto.',
    categoria: 'Seus apps', icone_app: nome,
    botao: { aparencia: { widget: 'icone', icon_app: nome, label: '', color: '#3E63DD' },
             toque: [{ type: 'focus_or_launch', target: nome }] },
  }
}

type Props = { apps: string[]; onAdicionar: (item: ItemBib) => void }

export default function Biblioteca({ apps, onAdicionar }: Props) {
  const cat = useCatalogo()
  const [busca, setBusca] = useState('')
  const [aba, setAba] = useState<'widgets' | 'apps'>('widgets')
  const q = busca.trim().toLowerCase()

  const grupos = useMemo(() => {
    const itens = (cat?.biblioteca ?? []).filter(i =>
      !q || i.nome.toLowerCase().includes(q) || i.descricao.toLowerCase().includes(q))
    const por = new Map<string, ItemBib[]>()
    for (const i of itens) por.set(i.categoria, [...(por.get(i.categoria) ?? []), i])
    return [...por.entries()].sort((a, b) => {
      const ia = ORDEM.indexOf(a[0]), ib = ORDEM.indexOf(b[0])
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
    })
  }, [cat, q])

  const appsFiltrados = useMemo(
    () => apps.filter(a => !q || a.toLowerCase().includes(q)).slice(0, 80), [apps, q])

  return (
    <div className="biblioteca">
      <div className="bib-topo">
        <h2>Adicionar</h2>
        <p className="fraco">Arraste para um quadrado da placa, ou clique para pôr no primeiro livre.</p>
        <input className="busca" placeholder={aba === 'widgets' ? 'Buscar widget' : 'Buscar app instalado'}
               value={busca} onChange={e => setBusca(e.target.value)} />
        <div className="abas" role="tablist">
          <button role="tab" aria-selected={aba === 'widgets'} className={aba === 'widgets' ? 'on' : ''}
                  onClick={() => setAba('widgets')}>Widgets</button>
          <button role="tab" aria-selected={aba === 'apps'} className={aba === 'apps' ? 'on' : ''}
                  onClick={() => setAba('apps')}>Seus apps ({apps.length})</button>
        </div>
      </div>

      <div className="bib-lista">
        {aba === 'widgets' && grupos.map(([nome, itens]) => (
          <section key={nome}>
            <h3>{nome}</h3>
            <div className="ladrilhos">
              {itens.map(i => <Ladrilho key={i.id} item={i} onClique={() => onAdicionar(i)} />)}
            </div>
          </section>
        ))}
        {aba === 'widgets' && !grupos.length && <p className="fraco">Nada com “{busca}”.</p>}
        {aba === 'apps' && (
          <div className="apps">
            {appsFiltrados.map(a => <LinhaApp key={a} nome={a} onClique={() => onAdicionar(itemDeApp(a))} />)}
            {!appsFiltrados.length && <p className="fraco">Nenhum app com “{busca}” no Menu Iniciar.</p>}
          </div>
        )}
      </div>
    </div>
  )
}

function Ladrilho({ item, onClique }: { item: ItemBib; onClique: () => void }) {
  const d = useDraggable({ id: `bib:${item.id}`, data: { tipo: 'bib', item } })
  const ap = item.botao.aparencia
  return (
    <button ref={d.setNodeRef} {...d.listeners} {...d.attributes} onClick={onClique}
            className={'ladrilho' + (d.isDragging ? ' saindo' : '')} title={item.descricao}>
      <span className="tinta" style={{ background: ap.color ?? '#3E63DD' }}>
        {item.icone_app
          ? <img src={api.iconeApp(item.icone_app)} alt="" />
          : <Glifo nome={item.icone ?? ap.icon} tam={22} />}
      </span>
      <span className="nome">{item.nome}</span>
      <span className="desc">{item.descricao}</span>
    </button>
  )
}

function LinhaApp({ nome, onClique }: { nome: string; onClique: () => void }) {
  const item = useMemo(() => itemDeApp(nome), [nome])
  const d = useDraggable({ id: `bib:app:${nome}`, data: { tipo: 'bib', item } })
  return (
    <button ref={d.setNodeRef} {...d.listeners} {...d.attributes} onClick={onClique}
            className={'linha-app' + (d.isDragging ? ' saindo' : '')}>
      <img src={api.iconeApp(nome)} alt="" loading="lazy"
           onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden' }} />
      <span>{nome}</span>
    </button>
  )
}
