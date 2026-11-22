import { expect, test } from 'claude-code/testing'

const HITOS = `| ID | Hito | Semanas | Estado |
|---|---|---|---|
| S0 | Spike | 1 | pendiente |
| M0 | Fundaciones | 2 | hecho |
| M1 | Archivos | 4 | en-curso |
| M2 | Presupuestos | 3 | pendiente |
`
const ARCHIVOS: Record<string, string> = {
  'harness/hitos.md': HITOS,
  'harness/lotes/L-001-m1.md': '---\nid: L-001\ntitulo: Lote cerrado\nhito: M1\nestado: cerrado\n---\n| 1 | T-002 |\n| 2 | T-003 |\n',
  'harness/lotes/L-002-x.md': '---\nid: L-002\ntitulo: Pendientes de M1\nhito: M1\nestado: abierto\n---\n| 1 | T-004 |\n| 2 | T-005 |\n',
  'harness/tareas/T-002-a.md': '---\nid: T-002\ntitulo: Modelo\nestado: hecha\n---\n',
  'harness/tareas/T-003-b.md': '---\nid: T-003\ntitulo: Subida\nestado: hecha\n---\n',
  'harness/tareas/T-004-c.md': '---\nid: T-004\ntitulo: Documentador sin conexión\nestado: en-revision\npr: "#20"\n---\n',
  'harness/tareas/T-005-d.md': '---\nid: T-005\ntitulo: Limpieza\nestado: lista\n---\n',
}
const BAND = { plugin: 'avance-gsp', component: 'AbovePrompt', props: { hasSurvey: false } } as const

/** El kit resuelve las rutas contra la carpeta del mod; se compara la parte relativa. */
function rel(ruta: string): string {
  const normal = ruta.split('\\').join('/')
  const i = normal.lastIndexOf('/harness/')
  return i >= 0 ? normal.slice(i + 1) : normal
}

function entrada(nombre: string) {
  return { name: nombre, kind: 'file' as const, size: 1, mtimeMs: 0, isLink: false }
}

test('la barra muestra avance, dónde estamos y lo que falta', async ($, on) => {
  on('fs.exists', (_, e) => ({ value: rel(e.path) in ARCHIVOS || rel(e.path) === 'harness/lotes' || rel(e.path) === 'harness/tareas' }))
  on('fs.list', (_, e) => ({
    value: Object.keys(ARCHIVOS).filter(p => p.startsWith(rel(e.path) + '/')).map(p => entrada(p.split('/').pop()!)),
  }))
  on('fs.read', (_, e) => ({ value: ARCHIVOS[rel(e.path)] }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  const registro: unknown[] = []
  on('ui.log', (_, e) => {
    registro.push(e)
    return { value: undefined }
  })

  await $.session.start({ cwd: '/repo', surface: 'desktop', isInteractive: true })
  expect(registro).toEqual([])

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    // M0 hecho (2) + M1 a la mitad (4 * 2/4 = 2) sobre 10 semanas = 40 %.
    expect((await ui.find({ type: 'Text', text: /%/ }))?.text).toBe(' 40%')
    expect((await ui.find({ type: 'Text', text: /^Ahora:/ }))?.text)
      .toBe('Ahora: M1 Archivos › L-002 Pendientes de M1 › T-004 Documentador sin conexión (en-revision)')
    expect((await ui.find({ type: 'Text', text: /aprobadas/ }))?.text)
      .toBe('✓ 2 aprobadas · ◐ 1 en revisión · ○ 1 por hacer · faltan S0, M2')
    await ui.unmount()
  }
})

test('fuera del repo del GSP la barra no dibuja nada propio', async ($, on) => {
  on('fs.exists', () => ({ value: false }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })

  await $.session.start({ cwd: '/otro', surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /Avance/ })).toBeUndefined()
  await ui.unmount()
})
