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

function mostrar(rol, contenido, citas = []) {
    const elemento = document.createElement("article");
    elemento.className = "sep";
    const titulo = document.createElement("strong");
    titulo.textContent = rol === "user" ? "Vos" : "Documentador";
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

async function cargarHistorial() {
    try {
        const respuesta = await fetch(panel.dataset.ruta, {headers: {Accept: "application/json"}});
        if (!respuesta.ok) throw new Error();
        const datos = await respuesta.json();
        conversacion = datos.conversacion_id;
        for (const fila of datos.mensajes) mostrar(fila.rol, fila.contenido, fila.citas);
    } catch {
        estado.textContent = "No se pudo cargar el historial.";
    } finally {
        boton.disabled = false;
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
        mostrar("assistant", datos.respuesta, datos.citas);
        consulta.value = "";
        estado.textContent = "";
    } catch (error) {
        estado.textContent = error instanceof SyntaxError ? "Volvé a iniciar sesión para consultar." : error.message;
    } finally {
        boton.disabled = false;
        consulta.disabled = false;
        consulta.focus();
    }
});

cargarHistorial();
