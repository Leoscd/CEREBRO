import { atom, read, update } from 'claude-code'
import type { Engine, Register } from 'claude-code'

import type { Resumen } from '../types'

const resumen = atom({ plugin: 'avance-gsp', key: 'resumen' } as const, null)

const CELDAS = 24
const HITOS = 'harness/hitos.md'
const LOTES = 'harness/lotes'
const TAREAS = 'harness/tareas'

type Hito = { id: string; nombre: string; semanas: number; estado: string }
type Tarea = { id: string; titulo: string; estado: string }
type Lote = { id: string; titulo: string; hito: string; estado: string; tareas: string[] }

function frontmatter(texto: string): Record<string, string> {
  const m = texto.replace(/\r\n/g, '\n').match(/^---\n([\s\S]*?)\n---/)
  const datos: Record<string, string> = {}
  for (const linea of m ? m[1].split('\n') : []) {
    const i = linea.indexOf(':')
    if (i > 0) datos[linea.slice(0, i).trim()] = linea.slice(i + 1).replace(/\s+#.*$/, '').trim().replace(/^["']|["']$/g, '')
  }
  return datos
}

function leerHitos(texto: string): Hito[] {
  const hitos: Hito[] = []
  for (const linea of texto.replace(/\r\n/g, '\n').split('\n')) {
    const m = linea.match(/^\|\s*([SM]\d+)\s*\|\s*([^|]+?)\s*\|\s*([\d.]+)\s*\|\s*(hecho|en-curso|pendiente)\s*\|/)
    if (m) hitos.push({ id: m[1], nombre: m[2], semanas: Number(m[3]), estado: m[4] })
  }
  return hitos
}

function corto(texto: string, largo = 38): string {
  return texto.length > largo ? texto.slice(0, largo - 1) + '…' : texto
}

/** Calcula el resumen. Exportado para las pruebas. */
export function calcular(hitos: Hito[], lotes: Lote[], tareas: Tarea[]): Resumen | null {
  const total = hitos.reduce((s, h) => s + h.semanas, 0)
  if (!hitos.length || total <= 0) return null
  const porId = new Map(tareas.map(t => [t.id, t]))
  let hecho = 0
  let revision = 0
  for (const h of hitos) {
    if (h.estado === 'hecho') {
      hecho += h.semanas
      continue
    }
    if (h.estado !== 'en-curso') continue
    const ids = [...new Set(lotes.filter(l => l.hito === h.id).flatMap(l => l.tareas))]
    const suyas = ids.map(id => porId.get(id)).filter((t): t is Tarea => t !== undefined)
    if (!suyas.length) continue
    const n = suyas.length
    hecho += h.semanas * (suyas.filter(t => t.estado === 'hecha').length / n)
    revision += h.semanas * (suyas.filter(t => t.estado === 'en-revision' || t.estado === 'en-curso').length / n)
  }
  const actual = hitos.find(h => h.estado === 'en-curso') ?? hitos.find(h => h.estado === 'pendiente') ?? null
  const abiertos = lotes.filter(l => l.estado !== 'cerrado')
  const lote = abiertos.find(l => l.hito === actual?.id) ?? abiertos[0] ?? null
  const delLote = (lote?.tareas ?? []).map(id => porId.get(id)).filter((t): t is Tarea => t !== undefined)
  const tarea = ['en-curso', 'en-revision', 'lista', 'borrador']
    .map(estado => delLote.find(t => t.estado === estado))
    .find(t => t !== undefined) ?? null
  return {
    pct: Math.round((100 * hecho) / total),
    hecho: hecho / total,
    revision: revision / total,
    hito: actual?.id ?? null,
    hitoNombre: actual?.nombre ?? '',
    lote: lote?.id ?? null,
    loteTitulo: lote?.titulo ?? '',
    tarea: tarea?.id ?? null,
    tareaTitulo: tarea?.titulo ?? '',
    tareaEstado: tarea?.estado ?? '',
    aprobadas: tareas.filter(t => t.estado === 'hecha').length,
    enRevision: tareas.filter(t => t.estado === 'en-revision' || t.estado === 'en-curso').length,
    porHacer: tareas.filter(t => t.estado === 'lista' || t.estado === 'borrador').length,
    faltan: hitos.filter(h => h.estado === 'pendiente').map(h => h.id),
  }
}

async function leerResumen($: Engine): Promise<Resumen | null> {
  if (!(await $.fs.exists(HITOS))) return null
  const hitos = leerHitos(await $.fs.read(HITOS))
  const lotes: Lote[] = []
  if (await $.fs.exists(LOTES)) {
    for (const e of await $.fs.list(LOTES)) {
      if (e.kind !== 'file' || !/^L-\d+.*\.md$/.test(e.name)) continue
      const texto: string = await $.fs.read(`${LOTES}/${e.name}`)
      const fm = frontmatter(texto)
      const cuerpo = texto.replace(/\r\n/g, '\n').replace(/^---\n[\s\S]*?\n---/, '')
      lotes.push({
        id: fm.id ?? e.name.slice(0, 5), titulo: fm.titulo ?? '', hito: fm.hito ?? '', estado: fm.estado ?? 'abierto',
        tareas: [...new Set(cuerpo.match(/T-\d{3}/g) ?? [])],
      })
    }
  }
  const tareas: Tarea[] = []
  if (await $.fs.exists(TAREAS)) {
    for (const e of await $.fs.list(TAREAS)) {
      if (e.kind !== 'file' || !/^T-\d{3}.*\.md$/.test(e.name)) continue
      const fm = frontmatter(await $.fs.read(`${TAREAS}/${e.name}`))
      tareas.push({ id: fm.id ?? e.name.slice(0, 5), titulo: fm.titulo ?? '', estado: fm.estado ?? 'borrador' })
    }
  }
  return calcular(hitos, lotes, tareas)
}

/** El resumen actual, o null si este directorio no es el repo del GSP o algo no se pudo leer. */
async function calcularActual($: Engine): Promise<Resumen | null> {
  try {
    return await leerResumen($)
  } catch (error) {
    $.ui.log(`avance-gsp: no pude leer harness/ (${error instanceof Error ? error.message : String(error)})`)
    return null
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const r = await next(e)
    const nuevo = await calcularActual($)
    await update($, resumen, () => nuevo)
    return r
  })

  // Codex trabaja en paralelo: se relee también al mandar cada mensaje.
  on('prompt.submit', async ($, e, next) => {
    const nuevo = await calcularActual($)
    await update($, resumen, () => nuevo)
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const r = await next(e)
    const nuevo = await calcularActual($)
    await update($, resumen, () => nuevo)
    return r
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const r = await read($, resumen)
    if (e.props.hasSurvey || r === null) return next(e)

    const { Box, Text } = $.ui.resolve(e)
    const verdes = Math.min(CELDAS, Math.round(r.hecho * CELDAS))
    const amarillas = Math.min(CELDAS - verdes, Math.round(r.revision * CELDAS))
    const grises = CELDAS - verdes - amarillas
    const donde = [
      r.hito && `${r.hito} ${corto(r.hitoNombre, 30)}`,
      r.lote && `${r.lote} ${corto(r.loteTitulo, 30)}`,
      r.tarea && `${r.tarea} ${corto(r.tareaTitulo)} (${r.tareaEstado})`,
    ].filter(Boolean).join(' › ')
    const faltan = r.faltan.length ? ` · faltan ${r.faltan.join(', ')}` : ''

    return (
      <Box flexDirection="column">
        <Box flexDirection="row">
          <Text bold>Avance GSP </Text>
          <Text color="success">{'█'.repeat(verdes)}</Text>
          <Text color="warning">{'▓'.repeat(amarillas)}</Text>
          <Text color="subtle">{'░'.repeat(grises)}</Text>
          <Text bold>{` ${r.pct}%`}</Text>
          <Text dimColor> del plan</Text>
        </Box>
        <Text dimColor>{`Ahora: ${donde || "sin lote abierto"}`}</Text>
        <Text dimColor>
          {`✓ ${r.aprobadas} aprobadas · ◐ ${r.enRevision} en revisión · ○ ${r.porHacer} por hacer${faltan}`}
        </Text>
      </Box>
    )
  })
}
