import { useEffect, useState } from 'react'
import { api, type ModuloInfo, type PaginaInfo, type Tudo } from './api'
import { CampoForm } from './Campos'
import { useAviso } from './comum'

type Props = { tudo: Tudo; apps: string[]; paginas: PaginaInfo[] }

export default function Modulos({ tudo, apps, paginas }: Props) {
  const [mods, setMods] = useState<ModuloInfo[]>([])
  const avisar = useAviso()
  const recarrega = () => api.modulos().then(setMods).catch(e => avisar(String(e), 'erro'))
  useEffect(() => { recarrega() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="modulos">
      <section>
        <h2>Pacotes de apps</h2>
        <p className="fraco">Cada pacote traz as páginas e os atalhos de um app. A página abre sozinha quando o app vem para a frente.</p>
        <div className="pacotes">
          {tudo.pacotes.map(p => (
            <label key={p.id} className="pacote">
              <span className="pacote-nome">{p.nome}</span>
              <span className="fraco pequeno">{p.instalado ? 'instalado neste PC' : 'não encontrado neste PC'}</span>
              <span className="interruptor">
                <input type="checkbox" checked={p.ativo}
                       onChange={e => api.pacote(p.id, e.target.checked)
                         .then(() => avisar(e.target.checked ? `${p.nome} ligado` : `${p.nome} desligado`))
                         .catch(err => avisar(String(err), 'erro'))} />
                <span className="trilho" />
              </span>
            </label>
          ))}
        </div>
      </section>

      <section>
        <h2>Módulos</h2>
        <p className="fraco">Um módulo liga sozinho quando algum botão usa algo dele.</p>
        <div className="lista-mods">
          {mods.map(m => <CartaoModulo key={m.id} m={m} apps={apps} paginas={paginas} onSalvo={recarrega} />)}
        </div>
      </section>
    </div>
  )
}

function CartaoModulo({ m, apps, paginas, onSalvo }: { m: ModuloInfo; apps: string[]; paginas: PaginaInfo[]; onSalvo: () => void }) {
  const avisar = useAviso()
  const [vals, setVals] = useState<Record<string, unknown>>(m.valores)
  const campos = Object.entries(m.config)
  const mudou = JSON.stringify(vals) !== JSON.stringify(m.valores)
  const estado = m.erro ? 'erro' : m.ligado ? 'ok' : 'off'
  return (
    <article className="cartao-mod">
      <header>
        <span className={`bola ${estado}`} />
        <h3>{m.nome}</h3>
        <span className="fraco pequeno">{m.erro ? m.erro : m.ligado ? 'em uso' : 'sem uso no painel'}</span>
      </header>
      {campos.length > 0 && (
        <div className="cartao-campos">
          {campos.map(([k, c]) => (
            <CampoForm key={k} campo={c} valor={vals[k]} apps={apps} paginas={paginas}
                       onMuda={v => setVals(x => ({ ...x, [k]: v }))} />
          ))}
          <button className="primario" disabled={!mudou}
                  onClick={() => api.modulo(m.id, vals).then(() => { avisar(`${m.nome}: configuração salva`); onSalvo() })
                    .catch(e => avisar(String(e), 'erro'))}>
            Salvar configuração
          </button>
        </div>
      )}
    </article>
  )
}
