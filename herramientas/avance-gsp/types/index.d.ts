/** Lo que la barra dibuja, calculado desde harness/hitos.md, harness/lotes/ y harness/tareas/. */
export type Resumen = {
  /** Avance total del plan, de 0 a 100 (hitos hechos + parte hecha del hito en curso). */
  pct: number
  /** Fracción del plan hecha y aprobada (0..1). */
  hecho: number
  /** Fracción del plan en revisión o en curso (0..1). */
  revision: number
  hito: string | null
  hitoNombre: string
  lote: string | null
  loteTitulo: string
  tarea: string | null
  tareaTitulo: string
  tareaEstado: string
  aprobadas: number
  enRevision: number
  porHacer: number
  faltan: string[]
}

declare module 'claude-code' {
  interface PluginState {
    'avance-gsp': { resumen: Resumen | null }
  }
}
