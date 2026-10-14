import { useEffect, useMemo, useState } from 'react'
import { api, type Campo, type PaginaInfo } from './api'

type Ctx = { apps: string[]; paginas: PaginaInfo[] }
type Props = Ctx & { campo: Campo; valor: unknown; onMuda: (v: unknown) => void }

// Um campo de formulario, do tipo que o modulo declarou no modulo.json
export function CampoForm({ campo, valor, onMuda, apps, paginas }: Props) {
  const v = valor ?? campo.padrao
  switch (campo.tipo) {
    case 'bool':
      return (
        <label className="interruptor">
          <input type="checkbox" checked={!!v} onChange={e => onMuda(e.target.checked)} />
          <span className="trilho" /> {campo.rotulo}
        </label>
      )
    case 'numero':
      return <Rotulado r={campo.rotulo}>
        <input type="number" value={v === undefined || v === null ? '' : String(v)}
               onChange={e => onMuda(e.target.value === '' ? undefined : Number(e.target.value))} />
      </Rotulado>
    case 'opcoes':
      return <Rotulado r={campo.rotulo}>
        <select value={String(v ?? '')} onChange={e => onMuda(e.target.value)}>
          {(campo.opcoes ?? []).map(([val, rot]) => <option key={val} value={val}>{rot}</option>)}
        </select>
      </Rotulado>
    case 'pagina':
      return <Rotulado r={campo.rotulo}>
        <select value={String(v ?? '')} onChange={e => onMuda(e.target.value)}>
          {paginas.map(p => <option key={p.id} value={p.id}>{p.titulo}</option>)}
        </select>
      </Rotulado>
    case 'app':
      return <Rotulado r={campo.rotulo}><EscolheApp valor={String(v ?? '')} apps={apps} onMuda={onMuda} /></Rotulado>
    case 'tecla':
      return <Rotulado r={campo.rotulo}><GravaTecla valor={String(v ?? '')} onMuda={onMuda} /></Rotulado>
    case 'json':
    case 'grupo':
      return <Rotulado r={campo.rotulo}><CampoJson valor={v} onMuda={onMuda} /></Rotulado>
    case 'lista':
      return <Rotulado r={campo.rotulo}>
        <input value={Array.isArray(v) ? v.join(', ') : String(v ?? '')}
               placeholder="separe por vírgula"
               onChange={e => onMuda(e.target.value.split(',').map(s => s.trim()).filter(Boolean))} />
      </Rotulado>
    case 'segredo':
      return <Rotulado r={campo.rotulo}>
        <input type="password" value={String(v ?? '')} onChange={e => onMuda(e.target.value)} />
      </Rotulado>
    default:
      return <Rotulado r={campo.rotulo}>
        <input value={String(v ?? '')} onChange={e => onMuda(e.target.value)} />
      </Rotulado>
  }
}

function Rotulado({ r, children }: { r: string; children: React.ReactNode }) {
  return <label className="campo"><span>{r}</span>{children}</label>
}

function CampoJson({ valor, onMuda }: { valor: unknown; onMuda: (v: unknown) => void }) {
  const [txt, setTxt] = useState(() => JSON.stringify(valor ?? {}, null, 1))
  const [ruim, setRuim] = useState(false)
  return (
    <textarea className={'mono' + (ruim ? ' ruim' : '')} rows={3} spellCheck={false} value={txt}
              onChange={e => {
                setTxt(e.target.value)
                try { onMuda(JSON.parse(e.target.value)); setRuim(false) } catch { setRuim(true) }
              }} />
  )
}

// Escolher um app instalado, com o icone de cada um
export function EscolheApp({ valor, apps, onMuda }: { valor: string; apps: string[]; onMuda: (v: string) => void }) {
  const [aberto, setAberto] = useState(false)
  const [q, setQ] = useState('')
  const lista = useMemo(() => apps.filter(a => a.toLowerCase().includes(q.toLowerCase())).slice(0, 40), [apps, q])
  return (
    <div className="escolhe-app">
      <button type="button" className="atual" onClick={() => setAberto(!aberto)}>
        {valor ? <img src={api.iconeApp(valor)} alt="" onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden' }} /> : null}
        <span>{valor || 'Escolher app'}</span>
      </button>
      {aberto && (
        <div className="pop">
          <input autoFocus placeholder="Buscar app" value={q} onChange={e => setQ(e.target.value)} />
          <div className="pop-lista">
            {lista.map(a => (
              <button type="button" key={a} onClick={() => { onMuda(a); setAberto(false) }}>
                <img src={api.iconeApp(a)} alt="" loading="lazy"
                     onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden' }} />
                {a}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// e.code para letras e numeros (e.key muda com o shift: "!" em vez de "1")
const NOMES: Record<string, string> = {
  Escape: 'esc', Enter: 'enter', Tab: 'tab', ' ': 'space', ArrowUp: 'up', ArrowDown: 'down',
  ArrowLeft: 'left', ArrowRight: 'right', Home: 'home', End: 'end', PageUp: 'pgup', PageDown: 'pgdn',
  Delete: 'del', Insert: 'ins', Backspace: 'backspace', PrintScreen: 'prtsc', CapsLock: 'capslock',
}

function tecla(e: KeyboardEvent): string | null {
  if (['Control', 'Shift', 'Alt', 'Meta', 'OS'].includes(e.key)) return null
  if (/^Key[A-Z]$/.test(e.code)) return e.code.slice(3).toLowerCase()
  if (/^Digit\d$/.test(e.code)) return e.code.slice(5)
  if (/^F\d{1,2}$/.test(e.key)) return e.key.toLowerCase()
  return NOMES[e.key] ?? (e.key.length === 1 ? e.key.toLowerCase() : null)
}

// Aperte as teclas e o atalho fica gravado
export function GravaTecla({ valor, onMuda }: { valor: string; onMuda: (v: string) => void }) {
  const [gravando, setGravando] = useState(false)
  useEffect(() => {
    if (!gravando) return
    const ouve = (e: KeyboardEvent) => {
      e.preventDefault(); e.stopPropagation()
      const k = tecla(e)
      if (!k) return
      const partes = [e.ctrlKey && 'ctrl', e.shiftKey && 'shift', e.altKey && 'alt', e.metaKey && 'win', k]
      onMuda(partes.filter(Boolean).join('+'))
      setGravando(false)
    }
    window.addEventListener('keydown', ouve, true)
    return () => window.removeEventListener('keydown', ouve, true)
  }, [gravando, onMuda])
  // a tecla Windows o proprio Windows engole (abre o Iniciar): para ela, digitar
  const [manual, setManual] = useState(false)
  return (
    <div className="grava-tecla">
      {manual
        ? <input className="mono" autoFocus value={valor} placeholder="win+shift+s"
                 onChange={e => onMuda(e.target.value.replace(/\s/g, '').toLowerCase())}
                 onBlur={() => setManual(false)} />
        : <div className="teclas" aria-live="polite" onClick={() => setManual(true)}
               title="Clique para digitar (ex.: win+shift+s)">
            {gravando ? <span className="fraco">Aperte as teclas…</span>
              : valor ? valor.split('+').map((t, i) => <kbd key={i}>{t}</kbd>)
              : <span className="fraco">Nenhuma tecla</span>}
          </div>}
      <button type="button" className={gravando ? 'gravando' : ''} onClick={() => setGravando(!gravando)}>
        {gravando ? 'Cancelar' : 'Gravar'}
      </button>
    </div>
  )
}
