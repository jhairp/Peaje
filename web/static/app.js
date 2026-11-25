/**
 * Frontend SPA del Sistema Inteligente de Control de Peaje (IAM-811)
 * Maneja:
 *  - Autenticación con Google OAuth 2.0 y validación de Lista Blanca
 *  - Actualización en Tiempo Real vía WebSockets (/ws/eventos) + respaldo SSE (/api/v1/eventos/stream)
 *  - CRUD de Vehículos, Tarifas, Casetas y Lista Blanca
 *  - Historial de Pasos y Alertas en Tiempo Real
 *  - Agente Conversacional con Qwen (Texto e Imagen)
 *  - Verificación y configuración de INFERENCE_URL (RunPod / Google Colab)
 */

let TOKEN_SESION = localStorage.getItem("peaje_jwt") || "";
let USUARIO_ACTUAL = null;
let wsConexion = null;
let sseConexion = null;
let googleTokenClient = null;

// ============================================================================
// 1. AUTENTICACIÓN GOOGLE OAUTH 2.0
// ============================================================================
async function inicializarApp() {
  // Verificar si regresamos del callback oficial de Google OAuth 2.0 (/?oauth_token=... o /?oauth_error=...)
  const urlParams = new URLSearchParams(window.location.search);
  const oauthToken = urlParams.get("oauth_token");
  const oauthError = urlParams.get("oauth_error");

  if (oauthToken) {
    TOKEN_SESION = oauthToken;
    localStorage.setItem("peaje_jwt", TOKEN_SESION);
    window.history.replaceState({}, document.title, "/");
  } else if (oauthError) {
    window.history.replaceState({}, document.title, "/");
    document.getElementById("login-screen").classList.remove("hidden");
    mostrarErrorLogin(oauthError);
  }

  try {
    const rCfg = await fetch("/api/v1/auth/config");
    const cfg = await rCfg.json();
    if (cfg.google_client_id && !cfg.google_client_id.startsWith("tu-") && window.google) {
      window.google.accounts.id.initialize({
        client_id: cfg.google_client_id,
        callback: async (resp) => {
          await autenticarConBackend(resp.credential);
        },
      });
      window.google.accounts.id.renderButton(
        document.getElementById("google-btn-wrapper"),
        { theme: "filled_blue", size: "large", width: 340, text: "signin_with" }
      );
      googleTokenClient = window.google.accounts.oauth2.initTokenClient({
        client_id: cfg.google_client_id,
        scope: "openid email profile",
        prompt: "select_account",
        callback: async (resp) => {
          if (resp && resp.access_token) {
            await autenticarConBackend(resp.access_token);
          }
        },
      });
    }
  } catch (e) {
    console.warn("Google Identity script aviso:", e);
  }

  if (TOKEN_SESION) {
    const ok = await verificarSesionActiva();
    if (ok) {
      mostrarPanelPrincipal();
      return;
    }
  }
  document.getElementById("login-screen").classList.remove("hidden");
}

function abrirPopupGoogleOAuth() {
  if (googleTokenClient) {
    googleTokenClient.requestAccessToken({ prompt: "select_account" });
  } else {
    window.location.href = "/api/v1/auth/google/login?state=web";
  }
}

async function autenticarConBackend(googleIdToken) {
  document.getElementById("login-error-box").classList.add("hidden");
  try {
    const resp = await fetch("/api/v1/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: googleIdToken }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      mostrarErrorLogin(data.detail || "Cuenta de Google no autorizada en la lista blanca.");
      return;
    }
    TOKEN_SESION = data.access_token;
    USUARIO_ACTUAL = data.usuario;
    localStorage.setItem("peaje_jwt", TOKEN_SESION);
    mostrarPanelPrincipal();
  } catch (err) {
    mostrarErrorLogin(String(err));
  }
}

function mostrarErrorLogin(mensaje) {
  const box = document.getElementById("login-error-box");
  const msg = document.getElementById("login-error-msg");
  msg.textContent = mensaje;
  box.classList.remove("hidden");
}

async function verificarSesionActiva() {
  try {
    const r = await apiFetch("/api/v1/auth/me");
    if (!r.ok) return false;
    USUARIO_ACTUAL = await r.json();
    return true;
  } catch {
    return false;
  }
}

function cerrarSesion() {
  TOKEN_SESION = "";
  USUARIO_ACTUAL = null;
  localStorage.removeItem("peaje_jwt");
  document.getElementById("login-screen").classList.remove("hidden");
}

async function apiFetch(url, options = {}) {
  const headers = options.headers || {};
  if (TOKEN_SESION) {
    headers["Authorization"] = `Bearer ${TOKEN_SESION}`;
  }
  return fetch(url, { ...options, headers });
}

// ============================================================================
// 2. INICIALIZACIÓN DEL PANEL Y CONEXIÓN EN TIEMPO REAL (WS + SSE)
// ============================================================================
async function mostrarPanelPrincipal() {
  document.getElementById("login-screen").classList.add("hidden");
  if (USUARIO_ACTUAL) {
    document.getElementById("user-name-label").textContent = USUARIO_ACTUAL.nombre;
    document.getElementById("user-email-label").textContent = USUARIO_ACTUAL.email_google;
    const badge = document.getElementById("user-role-badge");
    badge.textContent = USUARIO_ACTUAL.rol.toUpperCase();
  }

  await cargarResumenDashboard();
  conectarTiempoReal();
}

function conectarTiempoReal() {
  // 1. Conexión WebSocket
  try {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    wsConexion = new WebSocket(`${proto}://${window.location.host}/ws/eventos`);
    wsConexion.onopen = () => {
      document.getElementById("rt-status-text").textContent = "Tiempo Real Conectado (WebSocket)";
    };
    wsConexion.onmessage = (ev) => {
      procesarEventoTiempoReal(JSON.parse(ev.data));
    };
    wsConexion.onclose = () => {
      iniciarRespaldoSSE();
    };
  } catch {
    iniciarRespaldoSSE();
  }
}

function iniciarRespaldoSSE() {
  if (sseConexion) return;
  sseConexion = new EventSource("/api/v1/eventos/stream");
  sseConexion.onopen = () => {
    document.getElementById("rt-status-text").textContent = "Tiempo Real Conectado (SSE)";
  };
  sseConexion.onmessage = (ev) => {
    try {
      procesarEventoTiempoReal(JSON.parse(ev.data));
    } catch {}
  };
}

function procesarEventoTiempoReal(evento) {
  if (!evento || !evento.tipo) return;
  const { tipo, datos } = evento;

  if (datos.metricas) {
    actualizarKPIs(datos.metricas);
  }

  if (tipo === "nuevo_paso" && datos.paso) {
    actualizarSpotlightUltimoPaso(datos.paso);
    insertarFilaPasoTiempoReal(datos.paso);
    if (datos.alerta) {
      insertarAlertaTiempoReal(datos.alerta);
    }
  } else if (tipo === "alerta_atendida") {
    cargarResumenDashboard();
  }
}

// ============================================================================
// 3. DASHBOARD EN TIEMPO REAL
// ============================================================================
async function cargarResumenDashboard() {
  const r = await apiFetch("/api/v1/dashboard/resumen");
  if (!r.ok) return;
  const data = await r.json();

  actualizarKPIs(data.metricas);

  const pasos = data.pasos_recientes || [];
  if (pasos.length > 0) {
    actualizarSpotlightUltimoPaso(pasos[0]);
  }

  const tbody = document.getElementById("panel-pasos-tbody");
  tbody.innerHTML = pasos.map((p) => renderFilaPasoHTML(p, false)).join("");

  const alertasCont = document.getElementById("panel-alertas-list");
  const alertasPend = (data.alertas_recientes || []).filter((a) => !a.atendida);
  if (alertasPend.length === 0) {
    alertasCont.innerHTML = `<div class="p-4 rounded-xl bg-slate-900/60 text-xs text-slate-400 text-center">Sin alertas pendientes</div>`;
  } else {
    alertasCont.innerHTML = alertasPend.map((a) => renderTarjetaAlertaMini(a)).join("");
  }
}

function actualizarKPIs(m) {
  document.getElementById("kpi-total-pasos").textContent = m.total_pasos;
  document.getElementById("kpi-recaudacion").textContent = Number(m.recaudacion_total_bs || 0).toFixed(2);
  document.getElementById("kpi-alertas").textContent = m.alertas_pendientes;
  document.getElementById("kpi-vehiculos").textContent = m.vehiculos_registrados;
  document.getElementById("nav-count-vehiculos").textContent = m.vehiculos_registrados;
  document.getElementById("nav-badge-alertas").textContent = m.alertas_pendientes;
}

function actualizarSpotlightUltimoPaso(p) {
  document.getElementById("live-img").src = p.imagen_url || `/api/v1/evidencias/demo_${p.placa_normalizada}.svg`;
  document.getElementById("live-placa").textContent = p.placa_normalizada;
  document.getElementById("live-categoria").textContent = p.categoria_detectada.toUpperCase();
  document.getElementById("live-ejes").textContent = `${p.ejes_detectados} ejes`;
  document.getElementById("live-monto").textContent = `Bs. ${Number(p.monto).toFixed(2)}`;
  document.getElementById("live-caseta").textContent = p.caseta_nombre;
  document.getElementById("live-propietario").textContent = p.propietario;
  document.getElementById("live-last-time").textContent = p.hora || p.fecha_hora;

  const estEl = document.getElementById("live-estado");
  estEl.textContent = p.estado.replace("_", " ").toUpperCase();
  estEl.className = "text-sm font-bold uppercase mt-0.5 " + (
    p.estado === "aprobado" ? "text-emerald-400" : p.estado === "sin_saldo" ? "text-amber-400" : "text-red-400"
  );
}

function badgeEstadoPaso(estado) {
  if (estado === "aprobado") {
    return `<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-700">APROBADO</span>`;
  }
  if (estado === "sin_saldo") {
    return `<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-700">SIN SALDO</span>`;
  }
  return `<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-red-950 text-red-300 border border-red-700">NO REGISTRADA</span>`;
}

function renderFilaPasoHTML(p, animado = true) {
  const imgUrl = p.imagen_url || `/api/v1/evidencias/demo_${p.placa_normalizada}.svg`;
  return `
    <tr class="${animado ? 'nuevo-item' : ''} hover:bg-slate-800/40 transition">
      <td class="py-2.5 px-3">
        <img src="${imgUrl}" onclick="verEvidenciaModal('${imgUrl}', 'Placa ${p.placa_normalizada} - ${p.categoria_detectada.toUpperCase()}')"
          class="w-16 h-10 object-cover rounded-lg border border-slate-700 cursor-pointer hover:scale-105 transition" />
      </td>
      <td class="py-2.5 px-3 font-mono font-bold text-white">${p.placa_normalizada}</td>
      <td class="py-2.5 px-3 text-slate-300">${p.propietario}</td>
      <td class="py-2.5 px-3 uppercase font-semibold text-sky-300">${p.categoria_detectada}</td>
      <td class="py-2.5 px-3 text-amber-300 font-semibold">${p.ejes_detectados}</td>
      <td class="py-2.5 px-3 text-purple-300 font-semibold">${p.pasajeros || 1}</td>
      <td class="py-2.5 px-3 font-bold text-emerald-400">Bs. ${Number(p.monto).toFixed(2)}</td>
      <td class="py-2.5 px-3 text-slate-400">${p.caseta_nombre}</td>
      <td class="py-2.5 px-3">${badgeEstadoPaso(p.estado)}</td>
      <td class="py-2.5 px-3 font-mono text-slate-400">${p.hora || p.fecha_hora}</td>
    </tr>
  `;
}

function insertarFilaPasoTiempoReal(p) {
  const tbody = document.getElementById("panel-pasos-tbody");
  tbody.insertAdjacentHTML("afterbegin", renderFilaPasoHTML(p, true));
}

function renderTarjetaAlertaMini(a) {
  const esEvasion = a.tipo === "placa_no_registrada";
  return `
    <div class="nuevo-item p-3.5 rounded-xl border ${esEvasion ? 'bg-red-950/40 border-red-700/60' : 'bg-amber-950/40 border-amber-700/60'} flex items-start justify-between gap-2">
      <div>
        <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded ${esEvasion ? 'bg-red-600 text-white' : 'bg-amber-600 text-white'}">
          ${esEvasion ? 'Placa No Registrada' : 'Vehículo Sin Saldo'}
        </span>
        <p class="text-xs font-bold text-white mt-1.5">Placa: <span class="font-mono">${a.placa}</span> (${a.categoria.toUpperCase()} · ${a.ejes} ejes)</p>
        <p class="text-[11px] text-slate-400">${a.caseta_nombre} · ${a.fecha_hora}</p>
      </div>
      <button onclick="marcarAlertaAtendida(${a.id})" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-emerald-700 text-[11px] text-slate-200 transition">
        Atender
      </button>
    </div>
  `;
}

function insertarAlertaTiempoReal(a) {
  const cont = document.getElementById("panel-alertas-list");
  if (cont.innerText.includes("Sin alertas pendientes")) {
    cont.innerHTML = "";
  }
  cont.insertAdjacentHTML("afterbegin", renderTarjetaAlertaMini(a));
}

// ============================================================================
// 4. ENVÍO DE FRAME REAL O SIMULADO DESDE CASETA
// ============================================================================
async function enviarFrameArchivo(inputEl) {
  if (!inputEl.files || !inputEl.files[0]) return;
  const formData = new FormData();
  formData.append("file", inputEl.files[0]);
  formData.append("caseta_id", document.getElementById("sim-caseta-id").value);

  const r = await apiFetch("/api/v1/pasos/frame", { method: "POST", body: formData });
  const data = await r.json();
  inputEl.value = "";
  if (!r.ok) {
    alert(data.detail || "Error al procesar el frame en INFERENCE_URL.");
  }
}

async function simularPasoCaseta(placa, categoria, ejes) {
  const caseta_id = Number(document.getElementById("sim-caseta-id").value || 1);
  const r = await apiFetch("/api/v1/pasos/frame", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      caseta_id,
      placa_override: placa,
      categoria_override: categoria,
      ejes_override: ejes,
    }),
  });
  if (!r.ok) {
    const err = await r.json();
    alert(err.detail || "Error al registrar paso");
  }
}

// ============================================================================
// 5. CRUD DE VEHÍCULOS, TARIFAS Y LISTA BLANCA
// ============================================================================
async function cargarVehiculos() {
  const q = document.getElementById("vehiculo-search").value.trim();
  const r = await apiFetch(`/api/v1/vehiculos${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  if (!r.ok) return;
  const lista = await r.json();

  const tbody = document.getElementById("vehiculos-tbody");
  tbody.innerHTML = lista.map((v) => `
    <tr class="hover:bg-slate-800/40">
      <td class="py-2.5 px-3 text-slate-400">#${v.id}</td>
      <td class="py-2.5 px-3 font-mono font-bold text-emerald-400">${v.placa}</td>
      <td class="py-2.5 px-3 text-white font-medium">${v.propietario}</td>
      <td class="py-2.5 px-3 uppercase text-sky-300 font-semibold">${v.categoria}</td>
      <td class="py-2.5 px-3 text-amber-300">${v.ejes}</td>
      <td class="py-2.5 px-3 font-bold ${v.saldo > 0 ? 'text-emerald-400' : 'text-red-400'}">Bs. ${Number(v.saldo).toFixed(2)}</td>
      <td class="py-2.5 px-3">${v.activo ? '<span class="text-emerald-400">Sí</span>' : '<span class="text-red-400">No</span>'}</td>
      <td class="py-2.5 px-3 text-right space-x-1.5">
        <button onclick='editarVehiculo(${JSON.stringify(v)})' class="px-2.5 py-1 rounded bg-slate-800 hover:bg-blue-600 text-slate-200">
          <i class="fa-solid fa-pen"></i>
        </button>
        <button onclick="eliminarVehiculo(${v.id}, '${v.placa}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-red-600 text-slate-200">
          <i class="fa-solid fa-trash"></i>
        </button>
      </td>
    </tr>
  `).join("");

  cargarTarifasYUsuarios();
}

async function cargarTarifasYUsuarios() {
  const rT = await apiFetch("/api/v1/tarifas");
  if (rT.ok) {
    const tarifas = await rT.json();
    document.getElementById("tarifas-tbody").innerHTML = tarifas.map((t) => `
      <tr>
        <td class="py-2 uppercase font-semibold text-sky-300">${t.categoria}</td>
        <td class="py-2 text-amber-300">${t.ejes} ejes</td>
        <td class="py-2 font-bold text-emerald-400">Bs. ${Number(t.monto).toFixed(2)}</td>
      </tr>
    `).join("");
  }

  const rU = await apiFetch("/api/v1/usuarios");
  if (rU.ok) {
    const usuarios = await rU.json();
    document.getElementById("usuarios-tbody").innerHTML = usuarios.map((u) => `
      <tr>
        <td class="py-2 font-mono text-slate-200">${u.email_google}</td>
        <td class="py-2 text-slate-300">${u.nombre}</td>
        <td class="py-2 uppercase font-bold ${u.rol === 'administrador' ? 'text-emerald-400' : 'text-sky-400'}">${u.rol}</td>
      </tr>
    `).join("");
  }
}

function abrirModalVehiculo() {
  document.getElementById("form-veh-id").value = "";
  document.getElementById("form-veh-placa").value = "";
  document.getElementById("form-veh-propietario").value = "";
  document.getElementById("form-veh-categoria").value = "auto";
  document.getElementById("form-veh-ejes").value = "2";
  document.getElementById("form-veh-saldo").value = "100";
  document.getElementById("modal-vehiculo-titulo").textContent = "Registrar Nuevo Vehículo";
  document.getElementById("modal-vehiculo").classList.remove("hidden");
}

function editarVehiculo(v) {
  document.getElementById("form-veh-id").value = v.id;
  document.getElementById("form-veh-placa").value = v.placa;
  document.getElementById("form-veh-propietario").value = v.propietario;
  document.getElementById("form-veh-categoria").value = v.categoria;
  document.getElementById("form-veh-ejes").value = v.ejes;
  document.getElementById("form-veh-saldo").value = v.saldo;
  document.getElementById("modal-vehiculo-titulo").textContent = `Editar Vehículo ${v.placa}`;
  document.getElementById("modal-vehiculo").classList.remove("hidden");
}

function cerrarModalVehiculo() {
  document.getElementById("modal-vehiculo").classList.add("hidden");
}

async function guardarVehiculoModal(ev) {
  ev.preventDefault();
  const id = document.getElementById("form-veh-id").value;
  const payload = {
    placa: document.getElementById("form-veh-placa").value,
    propietario: document.getElementById("form-veh-propietario").value,
    categoria: document.getElementById("form-veh-categoria").value,
    ejes: Number(document.getElementById("form-veh-ejes").value),
    saldo: Number(document.getElementById("form-veh-saldo").value),
    activo: true,
  };

  const url = id ? `/api/v1/vehiculos/${id}` : "/api/v1/vehiculos";
  const method = id ? "PUT" : "POST";
  const r = await apiFetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const err = await r.json();
    alert(err.detail || "No se pudo guardar el vehículo");
    return;
  }
  cerrarModalVehiculo();
  cargarVehiculos();
  cargarResumenDashboard();
}

async function eliminarVehiculo(id, placa) {
  if (!confirm(`¿Eliminar el vehículo con placa ${placa}?`)) return;
  const r = await apiFetch(`/api/v1/vehiculos/${id}`, { method: "DELETE" });
  if (!r.ok) {
    const err = await r.json();
    alert(err.detail || "Error al eliminar");
    return;
  }
  cargarVehiculos();
  cargarResumenDashboard();
}

async function agregarUsuarioListaBlanca(ev) {
  ev.preventDefault();
  const payload = {
    email_google: document.getElementById("nuevo-user-email").value,
    nombre: document.getElementById("nuevo-user-nombre").value,
    rol: document.getElementById("nuevo-user-rol").value,
    activo: true,
  };
  const r = await apiFetch("/api/v1/usuarios", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const err = await r.json();
    alert(err.detail || "Solo administradores pueden modificar la lista blanca.");
    return;
  }
  document.getElementById("nuevo-user-email").value = "";
  document.getElementById("nuevo-user-nombre").value = "";
  cargarTarifasYUsuarios();
}

// ============================================================================
// 6. HISTORIAL DE PASOS Y CENTRO DE ALERTAS
// ============================================================================
async function cargarHistorialPasos() {
  const placa = document.getElementById("pasos-filter-placa").value.trim();
  const estado = document.getElementById("pasos-filter-estado").value;
  const params = new URLSearchParams();
  if (placa) params.set("placa", placa);
  if (estado) params.set("estado", estado);

  const r = await apiFetch(`/api/v1/pasos?${params.toString()}`);
  if (!r.ok) return;
  const filas = await r.json();

  document.getElementById("historial-pasos-tbody").innerHTML = filas.map((p) => {
    const imgUrl = p.imagen_url || `/api/v1/evidencias/demo_${p.placa_normalizada}.svg`;
    return `
      <tr class="hover:bg-slate-800/40">
        <td class="py-2.5 px-3 text-slate-400">#${p.id}</td>
        <td class="py-2.5 px-3">
          <img src="${imgUrl}" onclick="verEvidenciaModal('${imgUrl}', 'Evidencia Paso #${p.id} - Placa ${p.placa_normalizada}')"
            class="w-16 h-10 object-cover rounded border border-slate-700 cursor-pointer" />
        </td>
        <td class="py-2.5 px-3 font-mono text-slate-300">${p.placa_leida}</td>
        <td class="py-2.5 px-3 font-mono font-bold text-white">${p.placa_normalizada}</td>
        <td class="py-2.5 px-3 text-slate-300">${(p.confianza_ocr * 100).toFixed(1)}%</td>
        <td class="py-2.5 px-3 uppercase text-sky-300 font-semibold">${p.categoria_detectada}</td>
        <td class="py-2.5 px-3 text-amber-300">${p.ejes_detectados}</td>
        <td class="py-2.5 px-3 font-bold text-emerald-400">Bs. ${Number(p.monto).toFixed(2)}</td>
        <td class="py-2.5 px-3 text-slate-400">${p.caseta_nombre}</td>
        <td class="py-2.5 px-3">${badgeEstadoPaso(p.estado)}</td>
        <td class="py-2.5 px-3 font-mono text-slate-400">${p.fecha_hora}</td>
      </tr>
    `;
  }).join("");
}

async function cargarAlertas() {
  const r = await apiFetch("/api/v1/alertas");
  if (!r.ok) return;
  const alertas = await r.json();
  const grid = document.getElementById("alertas-full-grid");
  if (alertas.length === 0) {
    grid.innerHTML = `<div class="p-6 text-slate-400 text-xs">No hay alertas registradas.</div>`;
    return;
  }
  grid.innerHTML = alertas.map((a) => {
    const esEvasion = a.tipo === "placa_no_registrada";
    return `
      <div class="p-4 rounded-2xl border ${esEvasion ? 'bg-red-950/30 border-red-800/60' : 'bg-amber-950/30 border-amber-800/60'} flex items-center justify-between gap-4">
        <div class="space-y-1">
          <div class="flex items-center gap-2">
            <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase ${esEvasion ? 'bg-red-600 text-white' : 'bg-amber-600 text-white'}">
              ${esEvasion ? 'Placa No Registrada (Posible Evasión)' : 'Vehículo Sin Saldo'}
            </span>
            <span class="text-xs text-slate-400">#${a.id} · ${a.fecha_hora}</span>
          </div>
          <p class="text-sm font-bold text-white">Placa: <span class="font-mono text-emerald-400">${a.placa}</span> · Categoría: ${a.categoria.toUpperCase()} (${a.ejes} ejes)</p>
          <p class="text-xs text-slate-400">${a.caseta_nombre} · Tarifa: Bs. ${Number(a.monto).toFixed(2)}</p>
        </div>
        <div>
          ${a.atendida
            ? `<span class="px-3 py-1 rounded-lg bg-slate-800 text-emerald-400 text-xs font-semibold"><i class="fa-solid fa-check mr-1"></i>Atendida</span>`
            : `<button onclick="marcarAlertaAtendida(${a.id})" class="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white">Marcar Atendida</button>`
          }
        </div>
      </div>
    `;
  }).join("");
}

async function marcarAlertaAtendida(id) {
  await apiFetch(`/api/v1/alertas/${id}/atender`, { method: "PATCH" });
  cargarResumenDashboard();
  cargarAlertas();
}

// ============================================================================
// 7. AGENTE CONVERSACIONAL QWEN (TEXTO E IMAGEN)
// ============================================================================
function agregarBurbujaChat(remitente, htmlTexto, badgeEstado = "") {
  const cont = document.getElementById("chat-messages");
  const esUsuario = remitente === "usuario";
  const formateado = htmlTexto
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.*?)`/g, "<code class='px-1.5 py-0.5 rounded bg-slate-800 text-emerald-300 font-mono'>$1</code>")
    .replace(/\n/g, "<br/>");

  const div = document.createElement("div");
  div.className = `p-4 rounded-2xl text-xs leading-relaxed ${
    esUsuario
      ? "bg-blue-600/20 border border-blue-500/40 ml-12 text-white"
      : "bg-slate-900/95 border border-slate-800 mr-8 text-slate-200"
  }`;
  div.innerHTML = `
    <div class="flex items-center justify-between mb-1.5">
      <span class="font-bold ${esUsuario ? 'text-blue-300' : 'text-purple-300'}">
        ${esUsuario ? '<i class="fa-solid fa-user mr-1"></i> Operador' : '<i class="fa-solid fa-robot mr-1"></i> Agente Qwen'}
      </span>
      ${badgeEstado ? `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-950 text-purple-300 border border-purple-700">${badgeEstado}</span>` : ""}
    </div>
    <div>${formateado}</div>
  `;
  cont.appendChild(div);
  cont.scrollTop = cont.scrollHeight;
}

async function enviarMensajeAgente(ev) {
  ev.preventDefault();
  const input = document.getElementById("chat-text-input");
  const texto = input.value.trim();
  if (!texto) return;
  input.value = "";
  await probarConsultaAgente(texto);
}

async function probarConsultaAgente(texto) {
  agregarBurbujaChat("usuario", texto);
  const r = await apiFetch("/api/v1/agente/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mensaje: texto }),
  });
  const data = await r.json();
  if (!r.ok) {
    agregarBurbujaChat("agente", `Error: ${data.detail || "No se pudo consultar el agente."}`);
    return;
  }
  agregarBurbujaChat("agente", data.respuesta, data.estado);
}

async function enviarImagenAgente(inputEl) {
  if (!inputEl.files || !inputEl.files[0]) return;
  const archivo = inputEl.files[0];
  agregarBurbujaChat("usuario", `📷 Imagen enviada para lectura de placa (M1 + OCR): **${archivo.name}**`);

  const formData = new FormData();
  formData.append("file", archivo);

  const r = await apiFetch("/api/v1/placas/consultar-imagen", {
    method: "POST",
    body: formData,
  });
  const data = await r.json();
  inputEl.value = "";
  if (!r.ok) {
    agregarBurbujaChat("agente", `⚠️ ${data.detail || "El endpoint de inferencia M1+OCR no respondió."}`, "Error Inferencia");
    return;
  }
  agregarBurbujaChat("agente", data.respuesta, data.estado);
}

// ============================================================================
// 8. ESTADO DEL ENDPOINT DE INFERENCIA (RUNPOD / GOOGLE COLAB)
// ============================================================================
async function verificarEstadoInferencia() {
  const card = document.getElementById("inferencia-status-card");
  card.innerHTML = `<p class="text-xs text-slate-400"><i class="fa-solid fa-spinner fa-spin mr-1.5"></i> Verificando conexión con INFERENCE_URL...</p>`;
  const r = await apiFetch("/api/v1/estado/inferencia");
  if (!r.ok) return;
  const data = await r.json();

  document.getElementById("input-inference-url").value = data.inference_url || "";

  if (data.online) {
    const det = data.detalle_servidor || {};
    const mods = det.modelos || {};
    card.innerHTML = `
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-2xl bg-emerald-500/20 border border-emerald-500/50 flex items-center justify-center">
            <i class="fa-solid fa-circle-check text-2xl text-emerald-400"></i>
          </div>
          <div>
            <p class="text-sm font-bold text-emerald-400">ENDPOINT DE INFERENCIA EN LÍNEA (RUNPOD / COLAB)</p>
            <p class="text-xs font-mono text-slate-300">${data.inference_url}</p>
          </div>
        </div>
        <div class="text-right text-xs">
          <p class="text-slate-400">Latencia Ping: <strong class="text-emerald-400">${data.latencia_ping_ms} ms</strong></p>
          <p class="text-slate-400">GPU / Dispositivo: <strong class="text-white">${det.dispositivo || 'CUDA GPU'}</strong></p>
        </div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4 pt-4 border-t border-slate-800 text-xs">
        <div class="p-3 rounded-xl bg-slate-950 border border-slate-800">
          <p class="text-slate-400">M1 (Detección Placas + OCR)</p>
          <p class="font-mono font-bold text-emerald-300 mt-1">${mods.m1_placas_ocr || 'Activo'}</p>
        </div>
        <div class="p-3 rounded-xl bg-slate-950 border border-slate-800">
          <p class="text-slate-400">M2 (Segmentación Vehículos)</p>
          <p class="font-mono font-bold text-sky-300 mt-1">${mods.m2_segmentacion || 'Activo'}</p>
        </div>
        <div class="p-3 rounded-xl bg-slate-950 border border-slate-800">
          <p class="text-slate-400">M3 (Keypoints Ruedas → Ejes)</p>
          <p class="font-mono font-bold text-amber-300 mt-1">${mods.m3_keypoints_ejes || 'Activo'}</p>
        </div>
      </div>
    `;
  } else {
    card.innerHTML = `
      <div class="flex items-start gap-3">
        <div class="w-12 h-12 rounded-2xl bg-amber-500/20 border border-amber-500/50 flex items-center justify-center shrink-0">
          <i class="fa-solid fa-plug-circle-exclamation text-2xl text-amber-400"></i>
        </div>
        <div class="space-y-1 text-xs">
          <p class="text-sm font-bold text-amber-300">Endpoint de Inferencia Sin Respuesta Directa</p>
          <p class="font-mono text-slate-300">INFERENCE_URL actual: ${data.inference_url}</p>
          <p class="text-slate-400">Detalle: ${data.error || 'Inicie el notebook servidor_inferencia_runpod.ipynb o servidor_inferencia_colab.ipynb y pegue la URL pública abajo.'}</p>
        </div>
      </div>
    `;
  }
}

async function guardarConfigInferencia(ev) {
  ev.preventDefault();
  const inference_url = document.getElementById("input-inference-url").value.trim();
  const inference_api_token = document.getElementById("input-inference-token").value.trim();
  const r = await apiFetch("/api/v1/estado/inferencia/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inference_url, inference_api_token: inference_api_token || null }),
  });
  if (!r.ok) {
    const err = await r.json();
    alert(err.detail || "Solo un Administrador puede cambiar INFERENCE_URL.");
    return;
  }
  await verificarEstadoInferencia();
}

// ============================================================================
// 9. NAVEGACIÓN DE PESTAÑAS Y MODALES
// ============================================================================
function cambiarTab(nombre) {
  const vistas = ["panel", "vehiculos", "pasos", "alertas", "chat", "estado"];
  for (const v of vistas) {
    document.getElementById(`view-${v}`).classList.toggle("hidden", v !== nombre);
    const btn = document.getElementById(`tab-btn-${v}`);
    if (v === nombre) {
      btn.className = "tab-btn px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white transition";
    } else {
      btn.className = "tab-btn px-3.5 py-1.5 rounded-lg text-xs font-semibold text-slate-300 hover:text-white transition";
    }
  }

  if (nombre === "panel") cargarResumenDashboard();
  if (nombre === "vehiculos") cargarVehiculos();
  if (nombre === "pasos") cargarHistorialPasos();
  if (nombre === "alertas") cargarAlertas();
  if (nombre === "estado") verificarEstadoInferencia();
}

function verEvidenciaModal(url, titulo) {
  document.getElementById("modal-evidencia-img").src = url;
  document.getElementById("modal-evidencia-titulo").textContent = titulo || "Imagen de Evidencia";
  document.getElementById("modal-evidencia").classList.remove("hidden");
}

window.addEventListener("DOMContentLoaded", inicializarApp);
