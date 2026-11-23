const panel = document.querySelector("#panel-agente");
panel.insertAdjacentHTML("beforeend", `
    <div data-mensajes aria-label="Historial de la conversación" aria-live="polite"></div>
    <p class="muted" role="status"></p>
    <form class="stack">
        <label for="pregunta-documentador">Pregunta sobre el proyecto</label>
        <textarea id="pregunta-documentador" rows="3" maxlength="1600" required></textarea>
        <button class="btn small" disabled>Preguntar</button>
    </form>
`);

const mensajes = panel.querySelector("[data-mensajes]");
const formulario = panel.querySelector("form");
const consulta = formulario.querySelector("textarea");
const boton = formulario.querySelector("button");
const estado = panel.querySelector("[role=status]");
let conversacion;
let esperaAprobacion = false;

function mostrar(rol, contenido, citas = []) {
    const elemento = document.createElement("article");
    elemento.className = "sep";
    const titulo = document.createElement("strong");
    titulo.textContent = rol === "user" ? "Vos" : (panel.dataset.agente || "Documentador");
    const texto = document.createElement("p");
    texto.style.whiteSpace = "pre-wrap";
    texto.textContent = contenido;
    elemento.append(titulo, texto);
    if (citas.length) {
        const referencias = document.createElement("ul");
        referencias.className = "class-list";
        for (const cita of citas) {
            const item = document.createElement("li");
            const enlace = document.createElement("a");
            enlace.href = cita.url;
            enlace.textContent = cita.nombre + " · pág. " + cita.pagina;
            item.append(enlace);
            referencias.append(item);
        }
        elemento.append(referencias);
    }
    mensajes.append(elemento);
}

function mostrarAprobaciones(datos) {
    const pendientes = datos.aprobaciones || [];
    esperaAprobacion = pendientes.length > 0;
    panel.querySelector("[data-aprobaciones]")?.remove();
    if (!esperaAprobacion) return;
    const seccion = document.createElement("div");
    seccion.dataset.aprobaciones = "";
    seccion.setAttribute("aria-label", "Aprobaciones pendientes");
    for (const llamada of pendientes) {
        const tarjeta = document.createElement("section");
        tarjeta.className = "card";
        const titulo = document.createElement("h3");
        titulo.textContent = llamada.descripcion;
        const detalle = document.createElement("pre");
        detalle.textContent = JSON.stringify(llamada.argumentos, null, 2);
        detalle.style.whiteSpace = "pre-wrap";
        tarjeta.append(titulo, detalle);
        for (const [accion, etiqueta] of [["aprobar", "Aprobar"], ["rechazar", "Rechazar"]]) {
            const control = document.createElement("button");
            control.type = "button";
            control.className = "btn small";
            control.textContent = etiqueta;
            control.addEventListener("click", () => decidirAprobacion(datos.run_id, llamada.id, accion));
            tarjeta.append(control);
        }
        seccion.append(tarjeta);
    }
    mensajes.after(seccion);
}

async function decidirAprobacion(run, llamada, accion) {
    const controles = panel.querySelectorAll("[data-aprobaciones] button");
    controles.forEach((control) => { control.disabled = true; });
    estado.textContent = "Procesando la decisión…";
    try {
        const respuesta = await fetch("/agentes/runs/" + run + "/tool-calls/" + llamada + "/" + accion, {
            method: "POST",
            headers: {"Content-Type": "application/json", Accept: "application/json", "X-CSRF": panel.dataset.csrf},
            body: "{}",
        });
        const datos = await respuesta.json();
        if (!respuesta.ok) throw new Error(datos.detail || "No se pudo registrar la decisión.");
        conversacion = datos.conversacion_id;
        mostrarAprobaciones(datos);
        if (!esperaAprobacion && datos.respuesta !== undefined) mostrar("assistant", datos.respuesta, datos.citas);
        estado.textContent = "";
    } catch (error) {
        estado.textContent = error.message;
        controles.forEach((control) => { control.disabled = false; });
    } finally {
        boton.disabled = esperaAprobacion;
    }
}

async function cargarHistorial() {
    try {
        const respuesta = await fetch(panel.dataset.ruta, {headers: {Accept: "application/json"}});
        if (!respuesta.ok) throw new Error();
        const datos = await respuesta.json();
        conversacion = datos.conversacion_id;
        for (const fila of datos.mensajes) mostrar(fila.rol, fila.contenido, fila.citas);
        mostrarAprobaciones(datos);
    } catch {
        estado.textContent = "No se pudo cargar el historial.";
    } finally {
        boton.disabled = esperaAprobacion;
    }
}

formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const mensaje = consulta.value.trim();
    if (!mensaje || boton.disabled) return;
    boton.disabled = true;
    consulta.disabled = true;
    estado.textContent = "Buscando en la documentación…";
    try {
        const respuesta = await fetch(panel.dataset.ruta, {
            method: "POST",
            headers: {"Content-Type": "application/json", Accept: "application/json", "X-CSRF": panel.dataset.csrf},
            body: JSON.stringify({mensaje, conversacion_id: conversacion}),
        });
        const datos = await respuesta.json();
        if (!respuesta.ok) {
            throw new Error(typeof datos.detail === "string" ? datos.detail : "No pudimos enviar la consulta.");
        }
        conversacion = datos.conversacion_id;
        mostrar("user", mensaje);
        mostrarAprobaciones(datos);
        if (!esperaAprobacion) mostrar("assistant", datos.respuesta, datos.citas);
        consulta.value = "";
        estado.textContent = "";
    } catch (error) {
        estado.textContent = error instanceof SyntaxError ? "Volvé a iniciar sesión para consultar." : error.message;
    } finally {
        boton.disabled = esperaAprobacion;
        consulta.disabled = false;
        consulta.focus();
    }
});

cargarHistorial();
