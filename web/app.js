/* CUTE & FAKE — lee contenido.json (generado por build.py) y pinta la web. */
(() => {
  "use strict";

  const $ = (s, el = document) => el.querySelector(s);
  const el = (tag, attrs = {}, hijos = []) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "html") n.innerHTML = v;
      else if (k === "text") n.textContent = v;
      else if (k in n && typeof v !== "string") n[k] = v;
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const h of [].concat(hijos)) if (h) n.append(h);
    return n;
  };

  // Aleatorio con semilla: la colocación es "aleatoria" pero estable entre visitas.
  const crearRng = (semilla) => {
    let a = semilla >>> 0;
    return () => {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };
  const entre = (r, a, b) => a + r() * (b - a);

  let DATOS = null;
  const indice = new Map(); // ruta -> nodo
  const padre = new Map();  // ruta -> ruta del padre ("" = portada)
  let estado = { fondoAlto: 0, iconosAlto: 0 };
  let scrollPortada = 0;
  let vistaActual = "portada";

  // ------------------------------------------------------------------ medios
  function medio(m, { controles = false, bucle = false } = {}) {
    if (!m) return null;
    if (m.tipo === "video") {
      const v = el("video", {
        src: controles ? m.src : undefined,
        "data-src": controles ? undefined : m.src,
        poster: m.poster, playsinline: true, preload: "none",
        muted: !controles, loop: bucle, controls: controles,
        width: m.w, height: m.h,
      });
      if (!controles) { v.muted = true; v.setAttribute("muted", ""); observarVideo(v); }
      return v;
    }
    return el("img", { src: m.src, alt: "", loading: "lazy", decoding: "async", width: m.w, height: m.h });
  }

  // Los vídeos-icono solo se descargan y reproducen cuando están cerca de la pantalla.
  const observador = "IntersectionObserver" in window ? new IntersectionObserver((entradas) => {
    for (const e of entradas) {
      const v = e.target;
      if (e.isIntersecting) {
        if (!v.src && v.dataset.src) { v.src = v.dataset.src; v.preload = "auto"; }
        v.play().catch(() => {});
      } else if (!v.paused) v.pause();
    }
  }, { rootMargin: "60% 0px" }) : null;
  function observarVideo(v) {
    if (observador) observador.observe(v);
    else { v.src = v.dataset.src; v.autoplay = true; }
  }

  // ------------------------------------------------------------------ título vertical que cabe
  function ajustarTitulo(h, maxAlto) {
    h.style.fontSize = "";
    const base = Math.min(140, Math.max(44, window.innerHeight * 0.11), window.innerWidth * 0.14);
    h.style.fontSize = base + "px";
    const alto = h.getBoundingClientRect().height;
    if (alto > maxAlto) h.style.fontSize = Math.max(22, base * (maxAlto / alto)) + "px";
    return h.getBoundingClientRect().width;
  }

  // ------------------------------------------------------------------ portada
  // Ajustes de la portada (config.json → "portada"). Tamaños: 1 = ocupa toda la pantalla.
  const AJUSTES_DEFECTO = {
    limite_movil_px: 700,
    movil:      { iconos_por_pantalla: 1.3, iconos_tamano: [0.35, 0.75], fondos_por_pantalla: 1.2, fondos_tamano: [0.3, 1.0], hueco: 0.08 },
    escritorio: { iconos_por_pantalla: 1.6, iconos_tamano: [0.22, 0.5],  fondos_por_pantalla: 1.3, fondos_tamano: [0.25, 0.95], hueco: 0.06 },
  };
  let AJ = null; // ajustes efectivos (los del config mezclados con los de defecto)
  function prepararAjustes() {
    const c = DATOS.portada || {};
    AJ = {
      limite_movil_px: c.limite_movil_px || AJUSTES_DEFECTO.limite_movil_px,
      movil: { ...AJUSTES_DEFECTO.movil, ...(c.movil || {}) },
      escritorio: { ...AJUSTES_DEFECTO.escritorio, ...(c.escritorio || {}) },
    };
  }
  const modo = () => (document.documentElement.clientWidth < AJ.limite_movil_px ? "movil" : "escritorio");

  // Escala un medio para que quepa en (s·ancho) × (s·alto) de pantalla
  function medir(m, s, W, V) {
    if (!m || !m.w || !m.h) { const l = Math.round(s * Math.min(W, V) * 0.7); return [l, l]; }
    const k = Math.min((s * W) / m.w, (s * V) / m.h);
    return [Math.round(m.w * k), Math.round(m.h * k)];
  }

  function solapa(a, b, pad) {
    return a.x < b.x + b.w + pad && a.x + a.w + pad > b.x && a.y < b.y + b.h + pad && a.y + a.h + pad > b.y;
  }

  /* Coloca una capa: un elemento cada (pantalla / por_pantalla), con algo de variación,
     y empujando hacia abajo lo que choque con los anteriores (más el hueco mínimo). */
  function colocarCapa(medios, { W, V, r, porPantalla, tam, hueco, inicio, hasta }) {
    const paso = V / Math.max(0.2, porPantalla);
    const pad = hueco * V;
    const margen = W * 0.03;
    const puestas = [];
    let cursor = inicio;
    for (let i = 0; hasta ? cursor < hasta : i < medios.length; i++) {
      const m = medios[i % medios.length];
      const [w, h] = medir(m, entre(r, tam[0], tam[1]), W, V);
      const c = { m, w, h, x: Math.round(entre(r, margen, Math.max(margen, W - w - margen))), y: Math.round(cursor + entre(r, -0.2, 0.2) * paso) };
      if (w > W - 2 * margen) c.x = Math.round((W - w) / 2);
      for (let vuelta = 0; vuelta < 20; vuelta++) {
        const choca = puestas.slice(-6).find((b) => solapa(c, b, pad));
        if (!choca) break;
        c.y = Math.round(choca.y + choca.h + pad);
      }
      c.y = Math.max(c.y, 0);
      puestas.push(c);
      cursor = c.y + paso;
      if (hasta && i > 500) break;
    }
    return { puestas, fin: puestas.reduce((f, c) => Math.max(f, c.y + c.h), 0) };
  }

  function barajar(lista, r) {
    const a = lista.slice();
    for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    return a;
  }

  function pintarPortada() {
    const W = document.documentElement.clientWidth, V = window.innerHeight;
    const a = AJ[modo()];
    const semilla = DATOS.semilla || 1;

    // Capa de iconos
    const capaIconos = $("#iconos");
    capaIconos.textContent = "";
    const ri = crearRng(semilla);
    const { puestas, fin } = colocarCapa(DATOS.posts.map((p) => p.icono), {
      W, V, r: ri, porPantalla: a.iconos_por_pantalla, tam: a.iconos_tamano, hueco: a.hueco, inicio: V * 0.2,
    });
    estado.iconosAlto = Math.round(Math.max(fin + V * 0.4, V * 1.5));
    capaIconos.style.height = estado.iconosAlto + "px";

    puestas.forEach((c, i) => {
      const p = DATOS.posts[i];
      const contenido = p.icono ? medio(p.icono, { bucle: true }) : el("div", { class: "sin-icono", text: p.titulo });
      let nodo;
      if (p.tipo === "carpeta") nodo = el("a", { href: "#/" + p.ruta, class: "icono clicable", "aria-label": p.titulo }, contenido);
      else if (p.tipo === "enlace") nodo = el("a", { href: p.url, target: "_blank", rel: "noopener", class: "icono clicable", "aria-label": p.titulo }, contenido);
      else nodo = el("div", { class: "icono media" }, contenido);
      nodo.dataset.titulo = p.titulo;
      Object.assign(nodo.style, { left: c.x + "px", top: c.y + "px", width: c.w + "px", height: c.h + "px" });
      capaIconos.append(nodo);
    });

    // Capa de fondo: se rellena (repitiendo las capturas si hace falta) hasta cubrir el mismo largo
    const capaFondo = $("#fondo .capa");
    capaFondo.textContent = "";
    const fondos = DATOS.fondo || [];
    estado.fondoAlto = estado.iconosAlto;
    if (fondos.length) {
      const rf = crearRng(semilla * 31 + 5);
      let lista = [];
      while (lista.length < 400) lista = lista.concat(barajar(fondos, rf));
      const f = colocarCapa(lista, {
        W, V, r: rf, porPantalla: a.fondos_por_pantalla, tam: a.fondos_tamano, hueco: a.hueco,
        inicio: 0, hasta: estado.iconosAlto,
      });
      estado.fondoAlto = Math.max(estado.iconosAlto, f.fin);
      for (const c of f.puestas) {
        const m = c.m;
        const caja = el("div", {}, m.tipo === "video"
          ? el("video", { src: m.src, poster: m.poster, muted: true, autoplay: true, loop: true, playsinline: true })
          : el("img", { src: m.src, alt: "", decoding: "async" }));
        Object.assign(caja.style, { left: c.x + "px", top: c.y + "px", width: c.w + "px", height: c.h + "px" });
        capaFondo.append(caja);
      }
    }
    capaFondo.style.height = estado.fondoAlto + "px";
    // Título
    const t = $("#titulo-portada");
    t.textContent = DATOS.titulo || "";
    ajustarTitulo(t, V * 0.8);
    alScroll();
  }

  // Las dos capas acaban a la vez: la de iconos con el scroll normal,
  // la de fondo recorre su largo en sentido contrario.
  let pendiente = false;
  function alScroll() {
    if (vistaActual !== "portada") return;
    const V = window.innerHeight;
    const max = Math.max(1, document.documentElement.scrollHeight - V);
    const p = Math.min(1, Math.max(0, window.scrollY / max));
    const recorrido = Math.max(0, estado.fondoAlto - V);
    $("#fondo .capa").style.transform = `translate3d(0, ${-(1 - p) * recorrido}px, 0)`;
    $("#titulo-portada").style.opacity = Math.max(0, 1 - window.scrollY / (V * 0.45));
  }
  window.addEventListener("scroll", () => {
    if (pendiente) return;
    pendiente = true;
    requestAnimationFrame(() => { pendiente = false; alScroll(); });
  }, { passive: true });

  // ------------------------------------------------------------------ etiqueta que sigue al ratón
  const etiqueta = $("#etiqueta");
  if (matchMedia("(hover: hover)").matches) {
    document.addEventListener("pointermove", (e) => {
      const objetivo = e.target.closest && e.target.closest("[data-titulo]");
      if (objetivo && vistaActual === "portada") {
        etiqueta.textContent = objetivo.dataset.titulo;
        const w = etiqueta.offsetWidth;
        const x = e.clientX + 16 + w > window.innerWidth ? e.clientX - w - 12 : e.clientX + 16;
        etiqueta.style.transform = `translate(${x}px, ${e.clientY + 14}px)`;
        etiqueta.classList.add("visible");
      } else etiqueta.classList.remove("visible");
    });
    document.addEventListener("pointerleave", () => etiqueta.classList.remove("visible"));
  }

  // ------------------------------------------------------------------ página de carpeta
  const ICONO_LINK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>';

  function pintarItem(i) {
    switch (i.tipo) {
      case "imagen": {
        const img = medio(i);
        img.classList.add("foto");
        img.addEventListener("click", () => abrirVisor(i.src));
        return img;
      }
      case "video":
        return medio(i, { controles: true });
      case "texto":
        return el("div", { class: "texto", html: i.html });
      case "pdf":
        return el("a", { href: i.src, target: "_blank", rel: "noopener", class: "pdf" + (i.miniatura ? "" : " sin-miniatura") }, [
          i.miniatura ? el("img", { src: i.miniatura, alt: "", loading: "lazy", width: i.w, height: i.h }) : null,
          el("span", { class: "marca", text: "PDF ↗" }),
        ]);
      case "enlace":
        return el("a", { href: i.url, target: "_blank", rel: "noopener", class: "enlace", html: ICONO_LINK }, [
          el("span", { text: i.dominio }), el("span", { class: "marca", text: "↗" }),
        ]);
    }
    return null;
  }

  function pintarTarjeta(h) {
    const cara = el("span", { class: "cara" }, h.icono ? medio(h.icono, { bucle: true }) : el("span", { class: "sin-icono", text: h.titulo }));
    const nombre = el("span", { class: "nombre", text: h.titulo });
    if (h.tipo === "carpeta") return el("a", { href: "#/" + h.ruta, class: "tarjeta clicable" }, [cara, nombre]);
    if (h.tipo === "enlace") return el("a", { href: h.url, target: "_blank", rel: "noopener", class: "tarjeta clicable" }, [cara, nombre]);
    return el("div", { class: "tarjeta" }, [cara, nombre]);
  }

  function pintarPagina(nodo) {
    $("#titulo-pagina").textContent = nodo.titulo;
    $("#volver").href = "#/" + (padre.get(nodo.ruta) || "");
    const g = $("#cuadricula");
    g.textContent = "";
    for (const h of nodo.hijos || []) g.append(pintarTarjeta(h));
    for (const i of nodo.items || []) { const n = pintarItem(i); if (n) g.append(n); }
    const ancho = ajustarTitulo($("#titulo-pagina"), window.innerHeight - 90);
    $("#pagina").style.setProperty("--ancho-titulo", Math.ceil(Math.max(ancho, 40)) + "px");
    document.title = `${nodo.titulo} — ${DATOS.titulo}`;
  }

  // ------------------------------------------------------------------ visor
  const visor = $("#visor");
  function abrirVisor(src) { $("img", visor).src = src; visor.hidden = false; }
  visor.addEventListener("click", () => (visor.hidden = true));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") visor.hidden = true; });

  // ------------------------------------------------------------------ rutas (#/post/subcarpeta)
  function indexar(nodos, rutaPadre) {
    for (const n of nodos) {
      indice.set(n.ruta, n);
      padre.set(n.ruta, rutaPadre);
      if (n.hijos) indexar(n.hijos, n.ruta);
    }
  }

  function navegar() {
    const ruta = decodeURIComponent(location.hash.replace(/^#\/?/, "")).replace(/\/$/, "");
    const nodo = ruta && indice.get(ruta);
    etiqueta.classList.remove("visible");
    if (nodo && nodo.tipo === "carpeta") {
      if (vistaActual === "portada") scrollPortada = window.scrollY;
      vistaActual = "pagina";
      document.querySelectorAll("#iconos video").forEach((v) => v.pause());
      $("#portada").hidden = true; $("#fondo").hidden = true; $("#pagina").hidden = false;
      pintarPagina(nodo);
      window.scrollTo(0, 0);
    } else {
      const volviendo = vistaActual !== "portada";
      vistaActual = "portada";
      $("#pagina").hidden = true; $("#portada").hidden = false; $("#fondo").hidden = false;
      $("#cuadricula").textContent = "";
      document.title = DATOS.titulo;
      if (volviendo) window.scrollTo(0, scrollPortada);
      alScroll();
    }
  }

  // En el móvil la barra del navegador cambia el alto al hacer scroll: solo se recoloca
  // si cambia el ancho (girar el móvil, redimensionar la ventana en el PC).
  function repintarConservandoScroll() {
    const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    const p = window.scrollY / max;
    pintarPortada();
    window.scrollTo(0, p * Math.max(0, document.documentElement.scrollHeight - window.innerHeight));
  }
  let tRedim, anchoAnterior = document.documentElement.clientWidth;
  window.addEventListener("resize", () => {
    clearTimeout(tRedim);
    tRedim = setTimeout(() => {
      const ancho = document.documentElement.clientWidth;
      if (ancho === anchoAnterior) { alScroll(); return; }
      anchoAnterior = ancho;
      if (vistaActual === "portada") repintarConservandoScroll();
      else {
        const n = indice.get(decodeURIComponent(location.hash.replace(/^#\/?/, "")));
        if (n) pintarPagina(n);
      }
      if (panelAjustes) panelAjustes.refrescar();
    }, 200);
  });

  // ------------------------------------------------------------------ panel de ajustes
  // Se abre con ?ajustes en la URL (o si la web se genera con build.py --ajustes).
  // Sirve para probar valores en directo y copiarlos a config.json.
  let panelAjustes = null;
  function crearPanelAjustes() {
    const campos = [
      ["iconos_por_pantalla", "Iconos por pantalla", 0.3, 4, 0.1],
      ["iconos_tamano.0", "Icono: tamaño mínimo", 0.05, 1.2, 0.01],
      ["iconos_tamano.1", "Icono: tamaño máximo", 0.05, 1.2, 0.01],
      ["fondos_por_pantalla", "Fondos por pantalla", 0.3, 4, 0.1],
      ["fondos_tamano.0", "Fondo: tamaño mínimo", 0.05, 1.2, 0.01],
      ["fondos_tamano.1", "Fondo: tamaño máximo", 0.05, 1.2, 0.01],
      ["hueco", "Hueco mínimo", 0, 0.6, 0.01],
    ];
    const leer = (o, ruta) => ruta.split(".").reduce((x, k) => x[k], o);
    const escribir = (o, ruta, v) => { const ks = ruta.split("."); const u = ks.pop(); ks.reduce((x, k) => x[k], o)[u] = v; };
    const caja = el("div", { id: "ajustes" });
    const cabecera = el("button", { type: "button", class: "ajustes-boton", text: "Ajustes" });
    const cuerpo = el("div", { class: "ajustes-cuerpo", hidden: true });
    const titulo = el("p", { class: "ajustes-modo" });
    const filas = el("div");
    const salida = el("pre", { class: "ajustes-json" });
    const copiar = el("button", { type: "button", text: "Copiar para config.json" });
    const semilla = el("input", { type: "number", min: 1, max: 99999, value: DATOS.semilla || 1 });
    cuerpo.append(titulo, filas, el("label", { class: "ajustes-fila" }, [el("span", { text: "Semilla" }), semilla]), copiar, salida);
    caja.append(cabecera, cuerpo);
    document.body.append(caja);
    cabecera.addEventListener("click", () => { cuerpo.hidden = !cuerpo.hidden; });

    let tPintar;
    const aplicar = () => { clearTimeout(tPintar); tPintar = setTimeout(() => { if (vistaActual === "portada") repintarConservandoScroll(); }, 60); mostrarJson(); };
    const mostrarJson = () => {
      salida.textContent = JSON.stringify({ semilla: DATOS.semilla, portada: AJ }, null, 2)
        .replace(/\[\s+([\d.]+),\s+([\d.]+)\s+\]/g, "[$1, $2]");
    };
    semilla.addEventListener("input", () => { DATOS.semilla = parseInt(semilla.value, 10) || 1; aplicar(); });
    copiar.addEventListener("click", () => {
      navigator.clipboard.writeText(salida.textContent).then(() => { copiar.textContent = "¡Copiado!"; setTimeout(() => (copiar.textContent = "Copiar para config.json"), 1500); })
        .catch(() => { copiar.textContent = "Selecciona el texto y cópialo a mano"; });
    });
    function refrescar() {
      const m = modo();
      titulo.textContent = m === "movil" ? "Ajustando: MÓVIL" : "Ajustando: ESCRITORIO (estrecha la ventana para el móvil)";
      filas.textContent = "";
      for (const [ruta, nombre, min, max, paso] of campos) {
        const valor = el("output", { text: leer(AJ[m], ruta) });
        const rango = el("input", { type: "range", min, max, step: paso, value: leer(AJ[m], ruta) });
        rango.addEventListener("input", () => {
          const v = Math.round(parseFloat(rango.value) * 100) / 100;
          escribir(AJ[m], ruta, v);
          const t = AJ[m][ruta.split(".")[0]];
          if (Array.isArray(t) && t[0] > t[1]) { t.reverse(); refrescar(); }
          valor.textContent = v;
          aplicar();
        });
        filas.append(el("label", { class: "ajustes-fila" }, [el("span", { text: nombre }), rango, valor]));
      }
      mostrarJson();
    }
    refrescar();
    return { refrescar };
  }

  window.addEventListener("hashchange", navegar);

  fetch("contenido.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then(async (d) => {
      DATOS = d;
      document.title = d.titulo;
      indexar(d.posts, "");
      prepararAjustes();
      try { await document.fonts.ready; } catch (e) {}
      pintarPortada();
      if (d.ajustes || new URLSearchParams(location.search).has("ajustes")) panelAjustes = crearPanelAjustes();
      navegar();
    })
    .catch((e) => { document.body.textContent = "No se ha podido cargar contenido.json"; console.error(e); });
})();
