import { useDraggable, useDroppable } from '@dnd-kit/core'
import { api, type BotaoLayout, type Tudo } from './api'

// Mesma geometria do firmware (telinha_p4.ino) e do compositor
const W = 1280, H = 720, BARRA = 72, M = 8
const pct = (v: number, t: number) => `${(v / t) * 100}%`

type Props = {
  tudo: Tudo
  editando: boolean
  selecionado: string | null
  arrastando: 'card' | 'bib' | null
  pastas: Set<string>               // ids de botoes que levam a uma pasta
  onClique: (pos: number, id: string | null) => void
  onDuplo: (id: string) => void
}

export default function Placa({ tudo, editando, selecionado, arrastando, pastas, onClique, onDuplo }: Props) {
  const l = tudo.layout
  const { cols, rows } = l.grid ?? { cols: 3, rows: 2 }
  const cw = W / cols, ch = (H - BARRA) / rows
  const n = cols * rows

  return (
    <div className={'aparelho' + (editando ? ' editando' : '')}>
      <div className="tela">
        <div className="barra" style={{ height: pct(BARRA, H) }}>
          {l.back
            ? <button className="voltar" onClick={() => api.navegar(l.back)} aria-label={`Voltar para ${l.back}`}>‹</button>
            : <span />}
          <span className="titulo">{l.title?.trim()}</span>
          <span className="relogio">{tudo.barra}</span>
        </div>
        {Array.from({ length: n }, (_, i) => {
          const b = l.buttons[i]
          const real = b && b.id !== '_vazio' ? b : null
          const caixa = {
            left: pct((i % cols) * cw + M, W), top: pct(BARRA + Math.floor(i / cols) * ch + M, H),
            width: pct(cw - 2 * M, W), height: pct(ch - 2 * M, H),
          }
          return (
            <Celula key={i} pos={i} caixa={caixa} botao={real} tudo={tudo} editando={editando}
                    selecionado={!!real && real.id === selecionado} arrastando={arrastando}
                    ehPasta={!!real && pastas.has(real.id)}
                    onClique={() => onClique(i, real?.id ?? null)}
                    onDuplo={() => real && onDuplo(real.id)} />
          )
        })}
      </div>
      <div className="queixo">
        <span className={'led' + (tudo.conectado ? ' on' : '')} />
        <span>{tudo.conectado ? `Conectada em ${tudo.porta}` : 'Sem placa: esta é a tela virtual'}</span>
      </div>
    </div>
  )
}

type CelulaProps = {
  pos: number; caixa: React.CSSProperties; botao: BotaoLayout | null; tudo: Tudo
  editando: boolean; selecionado: boolean; arrastando: 'card' | 'bib' | null; ehPasta: boolean
  onClique: () => void; onDuplo: () => void
}

function Celula({ pos, caixa, botao, tudo, editando, selecionado, arrastando, ehPasta, onClique, onDuplo }: CelulaProps) {
  const drop = useDroppable({ id: `cel:${pos}`, data: { pos, botao: botao?.id ?? null } })
  const drag = useDraggable({ id: `card:${botao?.id ?? 'x' + pos}`, data: { tipo: 'card', id: botao?.id, pos },
                              disabled: !editando || !botao })
  const sobre = drop.isOver && arrastando
  const classe = ['celula', botao ? '' : 'vazia', selecionado ? 'sel' : '', sobre ? 'sobre' : '',
                  sobre && ehPasta ? 'pasta' : '', drag.isDragging ? 'saindo' : '',
                  arrastando && !botao ? 'convida' : ''].filter(Boolean).join(' ')

  if (!botao) {
    if (!editando) return null
    return (
      <button ref={drop.setNodeRef} className={classe} style={caixa} onClick={onClique}
              aria-label={`Quadrado vazio ${pos + 1}: criar botão`}>
        <span className="mais">+</span>
      </button>
    )
  }
  const aceso = !!botao.state_key && tudo.estado[botao.state_key] === true && !!botao.art_on
  const chave = aceso ? botao.art_on : botao.art
  const versao = aceso ? undefined : tudo.layout._vivos?.[botao.art]
  const refs = (el: HTMLButtonElement | null) => { drop.setNodeRef(el); drag.setNodeRef(el) }
  return (
    <button ref={refs} className={classe} style={caixa} onClick={onClique} onDoubleClick={onDuplo}
            {...drag.listeners} {...drag.attributes} aria-label={botao.id}>
      <img src={api.arte(chave, versao)} alt="" draggable={false} />
      {sobre && ehPasta && <span className="selo">Pôr na pasta</span>}
    </button>
  )
}
