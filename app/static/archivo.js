const limitar = (valor, minimo, maximo) => Math.min(maximo, Math.max(minimo, valor));
const vista = document.querySelector("#vista-archivo");
const divisor = document.querySelector("#divisor-visor");
const claveAncho = "gsp:ancho-visor";
let ancho = 64;

function ajustarAncho(porcentaje) {
    ancho = limitar(Math.round(porcentaje), 30, 76);
    vista.style.setProperty("--ancho-visor", ancho + "%");
    divisor.setAttribute("aria-valuenow", ancho);
}

function guardarAncho() {
    try {
        localStorage.setItem(claveAncho, String(ancho));
    } catch {
        // El divisor también funciona si el navegador bloquea el almacenamiento.
    }
}

try {
    const recordado = Number.parseFloat(localStorage.getItem(claveAncho));
    if (Number.isFinite(recordado)) ajustarAncho(recordado);
} catch {
    // Se usa el ancho inicial.
}

divisor.addEventListener("pointerdown", (evento) => {
    if (evento.button === 0) divisor.setPointerCapture(evento.pointerId);
});
divisor.addEventListener("pointermove", (evento) => {
    if (!divisor.hasPointerCapture(evento.pointerId)) return;
    const area = vista.getBoundingClientRect();
    ajustarAncho(100 * (evento.clientX - area.left) / area.width);
});
divisor.addEventListener("lostpointercapture", guardarAncho);
divisor.addEventListener("keydown", (evento) => {
    const desplazamiento = {ArrowLeft: -2, ArrowRight: 2}[evento.key];
    if (desplazamiento === undefined) return;
    evento.preventDefault();
    ajustarAncho(ancho + desplazamiento);
    guardarAncho();
});

async function iniciarPdf(visor) {
    const superficie = document.querySelector("#pagina-pdf");
    const estado = document.querySelector("#estado-pdf");
    const anterior = document.querySelector("#pagina-anterior");
    const siguiente = document.querySelector("#pagina-siguiente");
    const numero = document.querySelector("#numero-pagina");
    const acercar = document.querySelector("#acercar");
    const alejar = document.querySelector("#alejar");
    const desdeFragmento = () => Number(new URLSearchParams(location.hash.slice(1)).get("page")) || 1;
    let zoom = 1;
    let pagina = 1;
    let renderActual;
    let solicitud = 0;
    let documento;

    async function dibujar() {
        const turno = ++solicitud;
        renderActual?.cancel();
        try {
            const hoja = await documento.getPage(pagina);
            if (turno !== solicitud) return;
            const base = hoja.getViewport({scale: 1});
            const anchoDisponible = Math.max(160, superficie.clientWidth - 24);
            const plano = hoja.getViewport({scale: zoom * anchoDisponible / base.width});
            // Acota la memoria incluso para planos con proporciones extremas.
            const pixeles = Math.min(devicePixelRatio || 1, 2, Math.sqrt(12_000_000 / (plano.width * plano.height)));
            const lienzo = document.createElement("canvas");
            lienzo.width = Math.max(1, Math.ceil(plano.width * pixeles));
            lienzo.height = Math.max(1, Math.ceil(plano.height * pixeles));
            lienzo.style.width = plano.width + "px";
            lienzo.style.height = plano.height + "px";
            lienzo.setAttribute("aria-label", "Página " + pagina + " del PDF");
            renderActual = hoja.render({
                canvas: lienzo, viewport: plano, transform: [pixeles, 0, 0, pixeles, 0, 0],
            });
            await renderActual.promise;
            if (turno !== solicitud) return;
            superficie.replaceChildren(lienzo);
            estado.hidden = true;
        } catch (error) {
            if (turno !== solicitud || error.name === "RenderingCancelledException") return;
            estado.textContent = "No se pudo mostrar esta página.";
            estado.hidden = false;
        }
    }

    function irPagina(destino, actualizarFragmento = true) {
        pagina = limitar(Math.trunc(destino) || 1, 1, documento.numPages);
        numero.value = pagina;
        anterior.disabled = pagina === 1;
        siguiente.disabled = pagina === documento.numPages;
        if (actualizarFragmento) history.replaceState(null, "", "#page=" + pagina);
        dibujar();
    }

    function ajustarZoom(incremento) {
        zoom = limitar(zoom + incremento, 0.5, 3);
        alejar.disabled = zoom === 0.5;
        acercar.disabled = zoom === 3;
        dibujar();
    }

    try {
        const pdfjs = await import(visor.dataset.biblioteca);
        const directorio = new URL(".", new URL(visor.dataset.biblioteca, location.origin));
        pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdf.worker.mjs", directorio).href;
        documento = await pdfjs.getDocument({
            url: visor.dataset.contenido,
            cMapUrl: new URL("cmaps/", directorio).href,
            cMapPacked: true,
            standardFontDataUrl: new URL("standard_fonts/", directorio).href,
            wasmUrl: new URL("wasm/", directorio).href,
            iccUrl: new URL("iccs/", directorio).href,
            isEvalSupported: false,
        }).promise;
    } catch {
        estado.textContent = "No se pudo abrir el PDF. Podés descargarlo desde el historial.";
        return;
    }
    numero.max = documento.numPages;
    numero.disabled = false;
    acercar.disabled = false;
    alejar.disabled = false;
    document.querySelector("#total-paginas").textContent = "de " + documento.numPages;
    anterior.addEventListener("click", () => irPagina(pagina - 1));
    siguiente.addEventListener("click", () => irPagina(pagina + 1));
    numero.addEventListener("change", () => irPagina(Number(numero.value)));
    acercar.addEventListener("click", () => ajustarZoom(0.25));
    alejar.addEventListener("click", () => ajustarZoom(-0.25));
    window.addEventListener("hashchange", () => irPagina(desdeFragmento(), false));
    let ultimoAncho = superficie.clientWidth;
    new ResizeObserver(() => {
        const actual = superficie.clientWidth;
        if (actual === ultimoAncho) return;
        ultimoAncho = actual;
        dibujar();
    }).observe(superficie);
    irPagina(desdeFragmento(), false);
}

function iniciarImagen(visor) {
    const imagen = visor.querySelector("img");
    const acercar = document.querySelector("#acercar");
    const alejar = document.querySelector("#alejar");
    let zoom = 1;
    let x = 0;
    let y = 0;
    let origen;

    function dibujarImagen() {
        const limiteX = (zoom - 1) * visor.clientWidth / 2;
        const limiteY = (zoom - 1) * visor.clientHeight / 2;
        x = limitar(x, -limiteX, limiteX);
        y = limitar(y, -limiteY, limiteY);
        imagen.style.transform = "translate(" + x + "px, " + y + "px) scale(" + zoom + ")";
        visor.classList.toggle("ampliada", zoom > 1);
        alejar.disabled = zoom === 1;
        acercar.disabled = zoom === 4;
    }

    function ajustarZoom(valor) {
        zoom = limitar(valor, 1, 4);
        dibujarImagen();
    }

    acercar.addEventListener("click", () => ajustarZoom(zoom + 0.5));
    alejar.addEventListener("click", () => ajustarZoom(zoom - 0.5));
    document.querySelector("#restablecer").addEventListener("click", () => ajustarZoom(1));
    visor.addEventListener("pointerdown", (evento) => {
        if (zoom === 1 || evento.button !== 0) return;
        origen = {x: evento.clientX - x, y: evento.clientY - y};
        visor.setPointerCapture(evento.pointerId);
    });
    visor.addEventListener("pointermove", (evento) => {
        if (!origen || !visor.hasPointerCapture(evento.pointerId)) return;
        x = evento.clientX - origen.x;
        y = evento.clientY - origen.y;
        dibujarImagen();
    });
    visor.addEventListener("lostpointercapture", () => { origen = undefined; });
}

const pdf = document.querySelector("#visor-pdf");
const configOffice = document.querySelector("#config-onlyoffice");
if (configOffice) {
    try {
        new window.DocsAPI.DocEditor("visor-onlyoffice", JSON.parse(configOffice.textContent));
    } catch {
        document.querySelector("#visor-onlyoffice").textContent = "No se pudo abrir ONLYOFFICE. Podés descargar el archivo.";
    }
}
if (pdf) iniciarPdf(pdf);
const imagen = document.querySelector("#visor-imagen");
if (imagen) iniciarImagen(imagen);

// El primer bloque de un GLB 2 es su único documento JSON.
async function leerGltf(archivo, extension) {
    if (extension === "gltf") return JSON.parse(await archivo.text());
    const cabecera = new DataView(await archivo.slice(0, 20).arrayBuffer());
    const longitud = cabecera.getUint32(12, true);
    if (cabecera.getUint32(4, true) !== 2 || cabecera.getUint32(8, true) !== archivo.size ||
        cabecera.getUint32(16, true) !== 0x4e4f534a || 20 + longitud > archivo.size) {
        throw new Error("GLB inválido");
    }
    for (let pos = 20 + longitud; pos < archivo.size;) {
        const bloque = new DataView(await archivo.slice(pos, pos + 8).arrayBuffer());
        pos += 8 + bloque.getUint32(0, true);
        if (bloque.getUint32(4, true) === 0x4e4f534a || pos > archivo.size) throw new Error("GLB inválido");
    }
    return JSON.parse(await archivo.slice(20, 20 + longitud).text());
}

async function iniciarModelo3d(contenedor) {
    const estado = contenedor.querySelector("#estado-modelo");
    const encuadrar = contenedor.querySelector("#encuadrar-modelo");
    const superficie = contenedor.querySelector(".superficie-modelo");
    const fallo = () => { estado.textContent = "No se pudo mostrar el modelo. Podés descargar el original."; };
    try {
        const respuesta = await fetch(contenedor.dataset.contenido, {credentials: "same-origin"});
        if (!respuesta.ok) throw new Error("Contenido no disponible");
        const archivo = new File([await respuesta.blob()], contenedor.dataset.nombre);
        const extension = archivo.name.split(".").pop().toLowerCase();
        if (extension === "gltf" || extension === "glb") {
            const gltf = await leerGltf(archivo, extension);
            const recursos = [...(gltf.buffers || []), ...(gltf.images || [])];
            if (recursos.some(({uri}) => uri !== undefined && !uri.startsWith("data:"))) {
                estado.textContent = "Subí el modelo como GLB o glTF embebido";
                return;
            }
            if (gltf.extensionsRequired?.includes("KHR_draco_mesh_compression")) {
                estado.textContent = "Exportá el modelo sin compresión Draco.";
                return;
            }
        }
        const cargador = new OV.ThreeModelLoader();
        if (extension === "ifc") {
            const api = new WebIFC.IfcAPI();
            api.SetWasmPath("/static/vendor/web-ifc/", true);
            await api.Init(undefined, true);
            // El importador de o3dv 0.18.0 reutiliza una API ya inicializada.
            const importador = cargador.GetImporter().importers.find(i => i.CanImportExtension("ifc"));
            importador.ifc = api;
        }
        const visor = new OV.Viewer();
        visor.Init(superficie.querySelector("canvas"));
        const ajustar = () => visor.Resize(superficie.clientWidth, superficie.clientHeight);
        ajustar();
        new ResizeObserver(ajustar).observe(superficie);
        cargador.LoadModel(OV.InputFilesFromFileObjects([archivo]), new OV.ImportSettings(), {
            onLoadStart() {},
            onFileListProgress() {},
            onFileLoadProgress() {},
            onImportStart() { estado.textContent = "Leyendo la geometría…"; },
            onVisualizationStart() { estado.textContent = "Dibujando el modelo…"; },
            onTextureLoaded() { visor.Render(); },
            onLoadError: fallo,
            onModelFinished(resultado, objeto) {
                visor.SetMainObject(objeto);
                const esfera = visor.GetBoundingSphere(() => true);
                visor.AdjustClippingPlanesToSphere(esfera);
                visor.SetUpVector(OV.Direction.Y, false);
                visor.FitSphereToWindow(esfera, false);
                encuadrar.addEventListener("click", () => visor.FitSphereToWindow(esfera, true));
                encuadrar.disabled = false;
                estado.hidden = true;
            },
        });
    } catch {
        fallo();
    }
}

const modelo = document.querySelector("#visor-modelo3d");
if (modelo) iniciarModelo3d(modelo);
