# Recorrido en el VPS — cierre de M1, M2 y M3

M1, M2 y M3 tienen el código completo y las pruebas en verde, pero todo lo que depende de servicios reales se probó con dobles.
Este recorrido es lo que falta para pasarlos a `hecho` en `harness/hitos.md`. Se hace una vez, en el VPS, con datos de prueba
(nada de clientes reales) y anotando el resultado de cada paso en la tabla del final.

Tiempo estimado: 2 a 3 horas. Costo de OpenAI: centavos de dólar (unas pocas consultas y embeddings de 3 o 4 archivos).

## 0. Qué necesitás antes de empezar
- Acceso SSH al VPS y el repo en `/opt/gestor` (o donde esté), en `main` actualizado (`git pull`).
- Dos subdominios con registro A al VPS: `proyectos.<dominio>` y `docs.<dominio>` (ONLYOFFICE).
- La clave de OpenAI de la organización con retención mínima y los modelos que quieras por agente.
- Archivos de prueba en tu PC:
  - un DOCX y un XLSX cualquiera (sin datos de clientes) con una **frase rara** en el texto, por ejemplo "basamento ultramarino";
  - un PDF de 2 o más páginas;
  - un DXF exportado de AutoCAD con capas y textos;
  - un IFC exportado de Revit (un modelo chico, menos de 50 MB);
  - un GLB (puede ser cualquier modelo de ejemplo).
- Un celular con el navegador, para el parte diario.

## 1. Configuración
1. `.env` (partí de `.env.example`):
   - `SECRET_KEY` y `POSTGRES_PASSWORD` largos y aleatorios; `URL_PUBLICA=https://proyectos.<dominio>`.
   - `OPENAI_API_KEY`, `EMBEDDINGS_PROVEEDOR=openai`, `MODELO_EMBEDDINGS` (con `EMBEDDINGS_DIMENSIONES=384`).
   - `AGENTES_PROVEEDOR=openai`, `MODELO_DOCUMENTADOR`, `MODELO_PRESUPUESTOS`, `MODELO_OBRA`.
   - `TRANSCRIPCION_PROVEEDOR=openai` y `MODELO_TRANSCRIPCION`.
   - `ONLYOFFICE_URL=https://docs.<dominio>` y `ONLYOFFICE_JWT_SECRET` (32 bytes o más, aleatorio). Dejá `ONLYOFFICE_URL_INTERNA=http://onlyoffice` por ahora (ver paso 4.6).
   - SMTP real si querés probar las invitaciones por correo.
2. `Caddyfile`: reemplazá `proyectos.tudominio.com` y `docs.tudominio.com` por tus subdominios.
3. Levantá el gestor. Con `ONLYOFFICE_URL` configurada en `.env`, el script incluye el perfil `onlyoffice` y muestra los perfiles elegidos.
   ```bash
   ./scripts/deploy.sh
   docker compose ps          # todos "running"/"healthy"; onlyoffice tarda 1-2 minutos la primera vez
   ```
4. Si es la primera vez, creá dos empresas de prueba (la segunda es para el aislamiento):
   ```bash
   docker compose exec app python -m scripts.crear_empresa "Estudio Prueba" prueba tu@email "Tu Nombre"
   docker compose exec app python -m scripts.crear_empresa "Otra Empresa" otra otro@email "Otro Admin"
   ```
5. Ingresá con el admin de "Estudio Prueba", activá el 2FA y creá un proyecto de prueba con una persona más del equipo.

**Pasa si:** `https://proyectos.<dominio>/salud` responde, el certificado HTTPS es válido y `https://docs.<dominio>/healthcheck` devuelve `true`.

## 2. M1 — archivos, búsqueda y Documentador (clave real)
1. Subí el PDF. Esperá unos segundos y abrí la ficha: se ve en el visor y en "Página 2" se lee la página 2.
2. Buscá una palabra del PDF en el buscador del proyecto. **Pasa si** aparece con cita `#page=N` correcta.
3. Preguntale al Documentador algo que solo responda ese PDF. **Pasa si** contesta en rioplatense con cita `[archivo, pág. N]`.
4. `docker compose exec postgres psql -U gsp -c "select count(*) from chunks where embedding is not null"` → **mayor que 0** (embeddings reales).

## 3. M1 — visores nuevos (L-005)
1. **DOCX con Gotenberg:** para esta prueba, apagá ONLYOFFICE un momento (`ONLYOFFICE_URL=` en `.env` y `docker compose up -d app`).
   Subí el DOCX. **Pasa si** la ficha muestra "Preparando la vista previa…" y al recargar se ve como PDF, y la búsqueda encuentra la frase rara.
   Volvé a poner `ONLYOFFICE_URL` y `docker compose up -d app`.
2. **DXF:** subí el DXF. **Pasa si** se ve el plano con zoom y paneo, la lista de capas coincide con AutoCAD y un texto del plano aparece en la búsqueda.
3. **IFC de Revit:** subí el IFC. **Pasa si** la tabla muestra los pisos de Revit con sus elevaciones, la cantidad de muros/puertas/ventanas es razonable y el área de muros se parece a la planilla de Revit (anotá los dos números).
   Además el visor 3D muestra el modelo y "Encuadrar" funciona.
4. **GLB:** subí el GLB. **Pasa si** se ve en 3D y se puede orbitar.
5. **Memoria del worker:** mientras procesa el IFC, `docker stats --no-stream` → anotá el uso de memoria del worker (el límite es 1 GB).
6. **ONLYOFFICE lectura y edición:**
   - Abrí el XLSX con el admin. **Pasa si** se abre en ONLYOFFICE en modo edición.
   - Cambiá una celda, cerrá la pestaña y esperá 10-20 segundos. **Pasa si** en el historial del archivo aparece una versión nueva con tu nombre y el registro de auditoría tiene `archivo.version_onlyoffice`.
   - Si **no** aparece: `docker compose logs app | grep onlyoffice/callback`. Si el callback llegó con `{"error": 1}`, mirá en los logs de onlyoffice qué URL de descarga anunció y poné ese origen exacto (esquema + host) en `ONLYOFFICE_URL_INTERNA`; `docker compose up -d app` y repetí.
   - Abrí el mismo XLSX con un usuario cliente con acceso. **Pasa si** se abre en modo lectura, sin poder editar.

## 4. M2 — presupuestos con el agente (clave real)
1. En un presupuesto de prueba, pedile al agente de Presupuestos que agregue un ítem. **Pasa si** aparece la **tarjeta de aprobación**, al aprobar se agrega el ítem y al rechazar no cambia nada.
2. Exportá el presupuesto a Excel. **Pasa si** los totales coinciden con la pantalla al centavo.

## 5. M3 — obra desde el celular (clave real)
1. Desde el celular, abrí la obra del proyecto y cargá el parte del día: clima automático, una foto y un **dictado por audio**. **Pasa si** la transcripción llega como propuesta.
2. Pedile al agente de Obra "registrá un avance del 25 % en <tarea>". **Pasa si** aparece la tarjeta, al aprobar queda en el borrador del parte y al pedir "cerrá el parte" (con lo mínimo completo) sale numerado y el PDF aparece en la carpeta Bitácora.
3. Con el parte cerrado, pedile otra escritura. **Pasa si** responde que el parte está cerrado.

## 6. Aislamiento (con la segunda empresa)
Ingresá como el admin de "Otra Empresa" y probá:
- abrir por URL la ficha de un archivo de "Estudio Prueba" (`/archivos/<id>`, `/vista.pdf`, `/vista.svg`) → **404**;
- buscar la frase rara y una palabra del PDF → **sin resultados**;
- preguntarle al Documentador por esa frase → **no la conoce**.

## 7. Backups
`./scripts/backup.sh` y después `./scripts/probar_restauracion.sh`. **Pasa si** terminan sin error.

## Resultado
Completá y pasámelo (o pegalo en el chat): con esto actualizo `harness/hitos.md` y, si algo falla, escribo la tarea para Codex.

| Paso | Pasa / Falla | Notas (números, errores, capturas) |
|---|---|---|
| 1 Configuración y salud | | |
| 2 PDF, búsqueda, Documentador, embeddings | | |
| 3.1 DOCX con Gotenberg | | |
| 3.2 DXF | | |
| 3.3 IFC de Revit (áreas GSP vs Revit) | | |
| 3.4 GLB | | |
| 3.5 Memoria del worker con el IFC | | MB: |
| 3.6 ONLYOFFICE edición y lectura | | `ONLYOFFICE_URL_INTERNA` final: |
| 4 Presupuestos con aprobación y Excel | | |
| 5 Parte diario, dictado y agente de Obra | | |
| 6 Aislamiento con otra empresa | | |
| 7 Backup y restauración | | |
