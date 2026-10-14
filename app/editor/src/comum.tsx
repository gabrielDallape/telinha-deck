import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import type { Catalogo } from './api'

// Catalogo (icones, acoes, biblioteca) disponivel para todos os componentes
export const CatalogoCtx = createContext<Catalogo | null>(null)
export const useCatalogo = () => useContext(CatalogoCtx)

// Um glifo da Phosphor Fill, a mesma fonte que desenha os cards na placa
export function Glifo({ nome, cor, tam = 20 }: { nome?: string; cor?: string; tam?: number }) {
  const cat = useCatalogo()
  const cp = cat?.icones.find(i => i.nome === nome)?.cp
  if (!cp) return <span className="glifo vazio" style={{ width: tam, height: tam }} />
  return <span className="glifo" style={{ fontSize: tam, color: cor }}>{String.fromCodePoint(cp)}</span>
}

// Avisos curtos no canto: o que acabou de acontecer, ou o que deu errado
export type Aviso = { id: number; texto: string; tipo: 'ok' | 'erro' }
const AvisoCtx = createContext<(texto: string, tipo?: Aviso['tipo']) => void>(() => {})
export const useAviso = () => useContext(AvisoCtx)

export function Avisos({ children }: { children: ReactNode }) {
  const [lista, setLista] = useState<Aviso[]>([])
  const avisar = useCallback((texto: string, tipo: Aviso['tipo'] = 'ok') => {
    const id = Date.now() + Math.random()
    setLista(l => [...l.slice(-2), { id, texto, tipo }])
    setTimeout(() => setLista(l => l.filter(a => a.id !== id)), tipo === 'erro' ? 6000 : 2600)
  }, [])
  return (
    <AvisoCtx.Provider value={avisar}>
      {children}
      <div className="avisos" role="status" aria-live="polite">
        {lista.map(a => <div key={a.id} className={`aviso ${a.tipo}`}>{a.texto}</div>)}
      </div>
    </AvisoCtx.Provider>
  )
}

// Cores prontas: as mesmas famílias que os cards da placa usam
export const PALETA = ['#5B6572', '#3E63DD', '#7C66DC', '#8E4EC6', '#D6409F', '#E5484D',
                       '#F76B15', '#F5A524', '#30A46C', '#12A594', '#5865F2', '#D97757']
