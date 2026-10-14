import { useEffect, useRef, useState } from 'react'

type Diag = { nome: string; ok: boolean; detalhe: string; ms: number }
type Layout = { cols: number; rows: number; w: number; h: number; n: number }

const TELA_W = 1280, TELA_H = 720, BARRA_H = 72, MARGEM = 8
const params = new URLSearchParams(location.search)
const TOKEN = params.get('token') ?? ''
const AUTO = params.get('auto') === '1'

function celula(l: Layout, i: number) {
  const cw = TELA_W / l.cols, ch = (TELA_H - BARRA_H) / l.rows
  return { x: (i % l.cols) * cw + MARGEM, y: BARRA_H + Math.floor(i / l.cols) * ch + MARGEM }
}

export default function App() {
  const [diag, setDiag] = useState<Diag[]>([])
  const [status, setStatus] = useState('conectando...')
  const canvas = useRef<HTMLCanvasElement>(null)
  const ws = useRef<WebSocket | null>(null)
  const layout = useRef<Layout | null>(null)

  useEffect(() => {
    fetch('/api/diag').then(r => r.json()).then(setDiag)
  }, [])

  useEffect(() => {
    const ctx = canvas.current!.getContext('2d')!
    ctx.fillStyle = '#0e1116'; ctx.fillRect(0, 0, TELA_W, TELA_H)
    ctx.fillStyle = '#e6edf3'; ctx.font = '600 26px Segoe UI'
    ctx.fillText('placa virtual', 24, 46)

    const t0 = performance.now()
    let proximo = -1, desenhados = 0, msPrimeiro = 0, msTodos = 0
    const sock = new WebSocket(`ws://${location.host}/ws/placa?token=${TOKEN}`)
    sock.binaryType = 'blob'
    ws.current = sock

    sock.onmessage = async ev => {
      if (typeof ev.data !== 'string') {
        const i = proximo
        const bmp = await createImageBitmap(ev.data as Blob)
        const { x, y } = celula(layout.current!, i)
        ctx.drawImage(bmp, x, y)
        desenhados++
        if (desenhados === 1) msPrimeiro = performance.now() - t0
        if (desenhados === layout.current!.n) {
          msTodos = performance.now() - t0
          setStatus(`${desenhados} cards em ${msTodos.toFixed(0)} ms - toque num card`)
          if (AUTO) sock.send(JSON.stringify({ toque: 0, t: performance.now() }))
        }
        return
      }
      const msg = JSON.parse(ev.data)
      if (msg.ev === 'layout') layout.current = msg
      else if (msg.ev === 'img') proximo = msg.i
      else if (msg.ev === 'eco') {
        const ms = performance.now() - msg.t
        setStatus(`toque no card ${msg.i}: ida e volta em ${ms.toFixed(1)} ms`)
        if (AUTO) sock.send(JSON.stringify({ relatorio: {
          ok: desenhados === layout.current!.n, cards: desenhados,
          ms_primeiro_card: Math.round(msPrimeiro), ms_todos: Math.round(msTodos),
          ms_toque_ida_volta: Number(ms.toFixed(1)), navegador: navigator.userAgent,
        } }))
      }
    }
    sock.onclose = () => setStatus('desconectado')
    return () => sock.close()
  }, [])

  function toque(e: React.MouseEvent<HTMLCanvasElement>) {
    const l = layout.current
    if (!l || !ws.current) return
    const r = e.currentTarget.getBoundingClientRect()
    const x = (e.clientX - r.left) * TELA_W / r.width
    const y = (e.clientY - r.top) * TELA_H / r.height - BARRA_H
    if (y < 0) return
    const i = Math.floor(y / ((TELA_H - BARRA_H) / l.rows)) * l.cols + Math.floor(x / (TELA_W / l.cols))
    ws.current.send(JSON.stringify({ toque: i, t: performance.now() }))
  }

  return (
    <div className="app">
      <aside className="lado">
        <h2>Diagnóstico das peças</h2>
        {diag.map(d => (
          <div className="item" key={d.nome}>
            <span className="bola" style={{ background: d.ok ? 'var(--ok)' : 'var(--erro)' }} />
            <span>{d.nome}</span>
            <span className="status">{d.ms} ms</span>
            <small>{d.detalhe}</small>
          </div>
        ))}
      </aside>
      <main className="palco">
        <canvas ref={canvas} className="placa" width={TELA_W} height={TELA_H} onClick={toque} />
        <div className="status">{status}</div>
      </main>
    </div>
  )
}
