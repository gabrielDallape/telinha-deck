import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type Acao, type Botao, type Campo, type PaginaInfo, type Passo } from './api'
import { CampoForm, EscolheApp } from './Campos'
import { Glifo, PALETA, useAviso, useCatalogo } from './comum'

const WIDGETS: Record<string, string> = {
  icone: 'Ícone e texto', musica: 'Tocando agora', relogio: 'Relógio', clima: 'Clima',
  agenda: 'Próximas reuniões', sistema: 'CPU e RAM', foco: 'Pomodoro', projeto: 'Projeto',
}
const ESTILOS: Record<string, [string, string][]> = {
  musica: [['', 'Capa'], ['player', 'Player grande'], ['controle', 'Só o botão play/pausa']],
  relogio: [['', 'Normal'], ['grande', 'Grande (descanso)']],
  clima: [['', 'Normal'], ['grande', 'Grande (descanso)']],
}
const ESTADOS: Record<string, string> = {
  mic_muted: 'Microfone mudo', sys_muted: 'Som do PC mudo', sp_curtida: 'Faixa curtida no Spotify',
  sp_aleatorio: 'Spotify no aleatório', sp_repetir: 'Spotify repetindo', obs_live: 'Ao vivo no OBS',
  obs_rec: 'Gravando no OBS', obs_pausa: 'Gravação pausada no OBS',
}

type Props = {
  pagina: string; botao: Botao; gerado: boolean; pasta: string | null
  apps: string[]; paginas: PaginaInfo[]; estado: Record<string, unknown>
  onApagar: () => void; onFechar: () => void
}

export default function Inspector({ pagina, botao, gerado, pasta, apps, paginas, estado, onApagar, onFechar }: Props) {
  const cat = useCatalogo()
  const avisar = useAviso()
  const [b, setB] = useState<Botao>(botao)
  const [previa, setPrevia] = useState('')
  const [verAceso, setVerAceso] = useState(false)
  const [salvo, setSalvo] = useState<'salvo' | 'salvando' | 'erro'>('salvo')
  const [icones, setIcones] = useState(false)
  const original = useRef(JSON.stringify(botao))
  const ap = b.aparencia

  // preview na hora, salvamento quando voce para de mexer
  useEffect(() => {
    const t = setTimeout(() => {
      api.previa(pagina, b, verAceso).then(url => {
        setPrevia(old => { if (old) URL.revokeObjectURL(old); return url })
      }).catch(() => {})
    }, 120)
    return () => clearTimeout(t)
  }, [b, pagina, verAceso])

  useEffect(() => {
    const atual = JSON.stringify(b)
    if (atual === original.current || gerado) return
    setSalvo('salvando')
    const t = setTimeout(() => {
      api.salvar(pagina, limpa(b)).then(() => { original.current = atual; setSalvo('salvo') })
        .catch(e => { setSalvo('erro'); avisar(`Não salvou: ${e.message}`, 'erro') })
    }, 650)
    return () => clearTimeout(t)
  }, [b, pagina, gerado, avisar])

  const setAp = (mud: Partial<Botao['aparencia']>) => setB(x => ({ ...x, aparencia: { ...x.aparencia, ...mud } }))
  const setPasso = (i: number, p: Passo) => setB(x => ({ ...x, toque: x.toque.map((q, k) => k === i ? p : q) }))

  const acoesPorModulo = useMemo(() => {
    const g = new Map<string, Acao[]>()
    for (const a of cat?.acoes ?? []) g.set(a.modulo || 'painel', [...(g.get(a.modulo || 'painel') ?? []), a])
    return [...g.entries()]
  }, [cat])

  const chaves = useMemo(() => {
    const ks = new Set(Object.keys(estado).filter(k => typeof estado[k] === 'boolean'))
    if (b.aceso) ks.add(b.aceso)
    return [...ks].sort()
  }, [estado, b.aceso])

  const widget = ap.widget ?? 'icone'
  const titulo = ap.label || WIDGETS[widget] || 'Botão'

  return (
    <div className="inspector">
      <div className="insp-topo">
        <button className="voltar-bib" onClick={onFechar} aria-label="Voltar para a biblioteca">‹ Adicionar</button>
        <span className={'salvo ' + salvo}>
          {salvo === 'salvo' ? 'Salvo na placa' : salvo === 'salvando' ? 'Salvando…' : 'Erro ao salvar'}
        </span>
      </div>

      <div className="previa">
        {previa ? <img src={previa} alt={`Como o botão ${titulo} aparece na placa`} /> : <div className="previa-vazia" />}
        {b.aceso && (
          <label className="interruptor mini">
            <input type="checkbox" checked={verAceso} onChange={e => setVerAceso(e.target.checked)} />
            <span className="trilho" /> Ver aceso
          </label>
        )}
      </div>
      <h2 className="insp-titulo">{titulo}</h2>

      {gerado ? (
        <p className="fraco">Este botão é criado sozinho pela página (os arquivos de uma pasta, as cenas do OBS).
          Para mudar, mude a origem.</p>
      ) : (<>
        <section>
          <h3>Aparência</h3>
          <label className="campo"><span>Tipo</span>
            <select value={widget} onChange={e => setAp({ widget: e.target.value, estilo: undefined })}>
              {(cat?.widgets ?? []).map(w => <option key={w.id} value={w.id}>{WIDGETS[w.id] ?? w.id}</option>)}
            </select>
          </label>
          {ESTILOS[widget] && (
            <div className="segmentos">
              {ESTILOS[widget].map(([v, r]) => (
                <button key={v} className={(ap.estilo ?? '') === v ? 'on' : ''}
                        onClick={() => setAp({ estilo: v || undefined })}>{r}</button>
              ))}
            </div>
          )}
          <div className="dupla">
            <label className="campo"><span>Rótulo</span>
              <input value={ap.label ?? ''} onChange={e => setAp({ label: e.target.value })} placeholder="sem texto" />
            </label>
            <label className="campo"><span>Linha de baixo</span>
              <input value={ap.sub ?? ''} onChange={e => setAp({ sub: e.target.value })} placeholder="opcional" />
            </label>
          </div>
          <div className="campo"><span>Cor</span>
            <div className="paleta">
              {PALETA.map(c => (
                <button key={c} className={'amostra' + (ap.color?.toLowerCase() === c.toLowerCase() ? ' on' : '')}
                        style={{ background: c }} onClick={() => setAp({ color: c })} aria-label={`Cor ${c}`} />
              ))}
              <input type="color" value={ap.color ?? '#3E63DD'} onChange={e => setAp({ color: e.target.value })}
                     aria-label="Outra cor" />
            </div>
          </div>
          <div className="dupla">
            <div className="campo"><span>Ícone</span>
              <button className="escolhe-icone" onClick={() => setIcones(!icones)}>
                <Glifo nome={ap.icon} tam={22} cor={ap.color} /> <span>{ap.icon || 'nenhum'}</span>
              </button>
            </div>
            <div className="campo"><span>Ou o logo de um app</span>
              <div className="com-limpar">
                <EscolheApp valor={ap.icon_app ?? ''} apps={apps} onMuda={v => setAp({ icon_app: v })} />
                {ap.icon_app && <button className="limpar" onClick={() => setAp({ icon_app: undefined })}
                                        aria-label="Tirar o logo">×</button>}
              </div>
            </div>
          </div>
          {icones && <GradeIcones atual={ap.icon} cor={ap.color} onEscolhe={i => { setAp({ icon: i }); setIcones(false) }} />}
        </section>

        <section>
          <h3>Ao tocar</h3>
          {pasta && (
            <div className="nota">
              Leva para a pasta <b>{paginas.find(p => p.id === pasta)?.titulo}</b>.
              <button className="link" onClick={() => api.navegar(pasta)}>Abrir a pasta</button>
            </div>
          )}
          {b.toque.map((p, i) => {
            const acao = cat?.acoes.find(a => a.id === p.type)
            return (
              <div key={i} className="passo">
                <div className="passo-topo">
                  <select value={p.type} onChange={e => {
                    const nova = cat?.acoes.find(a => a.id === e.target.value)
                    setPasso(i, { type: e.target.value, ...padroes(nova?.campos) })
                  }}>
                    {acoesPorModulo.map(([mod, lista]) => (
                      <optgroup key={mod} label={mod}>
                        {lista.map(a => <option key={a.id} value={a.id}>{a.rotulo}</option>)}
                      </optgroup>
                    ))}
                  </select>
                  <button className="limpar" aria-label="Tirar este passo"
                          onClick={() => setB(x => ({ ...x, toque: x.toque.filter((_, k) => k !== i) }))}>×</button>
                </div>
                {acao?.campos
                  ? Object.entries(acao.campos).map(([k, c]) => (
                      <CampoForm key={k} campo={c} valor={p[k]} apps={apps} paginas={paginas}
                                 onMuda={v => setPasso(i, { ...p, [k]: v })} />))
                  : !acao && <p className="fraco">Ação de um módulo desligado: {p.type}</p>}
              </div>
            )
          })}
          <button className="secundario" onClick={() => setB(x => ({ ...x, toque: [...x.toque, { type: 'key', target: '' }] }))}>
            Adicionar passo
          </button>
          {b.toque.length > 1 && <p className="fraco pequeno">Os passos rodam em ordem, um depois do outro.</p>}
        </section>

        <section>
          <h3>Mais</h3>
          <label className="campo"><span>Acende quando</span>
            <select value={b.aceso ?? ''} onChange={e => setB(x => ({ ...x, aceso: e.target.value || undefined }))}>
              <option value="">Nunca</option>
              {chaves.map(k => <option key={k} value={k}>{ESTADOS[k] ?? k}</option>)}
            </select>
          </label>
          {b.aceso && (
            <label className="campo"><span>Rótulo quando aceso</span>
              <input value={ap.label_on ?? ''} onChange={e => setAp({ label_on: e.target.value })} placeholder="o mesmo" />
            </label>
          )}
          <label className="campo"><span>Depois de tocar, ir para</span>
            <select value={b.depois ?? ''} onChange={e => setB(x => ({ ...x, depois: e.target.value || undefined }))}>
              <option value="">Ficar nesta página</option>
              {paginas.map(p => <option key={p.id} value={p.id}>{p.titulo}</option>)}
            </select>
          </label>
        </section>
      </>)}

      <div className="insp-rodape">
        <button className="primario" onClick={() => b.id && api.toque(pagina, b.id)}>Testar</button>
        {!gerado && <button className="perigo" onClick={onApagar}>Apagar botão</button>}
      </div>
    </div>
  )
}

function padroes(campos?: Record<string, Campo> | null) {
  return Object.fromEntries(Object.entries(campos ?? {})
    .filter(([, c]) => c.padrao !== undefined && c.padrao !== '').map(([k, c]) => [k, c.padrao]))
}

function limpa(b: Botao): Botao {
  const ap = Object.fromEntries(Object.entries(b.aparencia).filter(([, v]) => v !== undefined && v !== ''))
  const toque = b.toque.map(p => Object.fromEntries(Object.entries(p).filter(([, v]) => v !== undefined)) as Passo)
  const { _fixo: _f, ...resto } = b
  void _f
  const out: Botao = { ...resto, aparencia: ap, toque }
  if (!out.aceso) delete out.aceso
  if (!out.depois) delete out.depois
  return out
}

function GradeIcones({ atual, cor, onEscolhe }: { atual?: string; cor?: string; onEscolhe: (n: string) => void }) {
  const cat = useCatalogo()
  const [q, setQ] = useState('')
  const lista = (cat?.icones ?? []).filter(i => i.nome.includes(q.toLowerCase()))
  return (
    <div className="grade-icones">
      <input autoFocus placeholder="Buscar ícone" value={q} onChange={e => setQ(e.target.value)} />
      <div className="icones">
        {lista.map(i => (
          <button key={i.nome} className={i.nome === atual ? 'on' : ''} title={i.nome} onClick={() => onEscolhe(i.nome)}>
            <Glifo nome={i.nome} tam={22} cor={i.nome === atual ? cor : undefined} />
          </button>
        ))}
      </div>
    </div>
  )
}
