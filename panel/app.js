// Helpers compartidos del panel -- sin build step, se sirve tal cual desde
// el mismo proceso de la API (api/app.py monta /panel como estatico). Todo
// fetch() es same-origin ('' de base) porque la API y el panel viven en el
// mismo host:puerto.
const API = "";

// Config elegida en la pantalla de Configuracion, pendiente de aplicar en
// el proximo /start. Vive en localStorage porque la API no persiste "que
// perfil vas a usar la proxima vez" -- solo lo que esta corriendo AHORA
// (ver docs/spec-api.md #5, "Persistencia del log de eventos" tiene la
// misma logica: nada de esto es critico, es conveniencia de UI).
const CONFIG_KEY = "pxs_pending_config";

function loadPendingConfig() {
  try {
    return JSON.parse(localStorage.getItem(CONFIG_KEY)) || null;
  } catch {
    return null;
  }
}

function savePendingConfig(cfg) {
  localStorage.setItem(CONFIG_KEY, JSON.stringify(cfg));
}

async function apiGet(path) {
  const res = await fetch(API + path);
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const parsed = (await res.json()).detail;
      if (parsed !== undefined && parsed !== null) detail = parsed;
    } catch {}
    // `detail` puede ser un string (caso general, ver .message abajo) o un
    // objeto estructurado (ej. BOT-032: {reason: "daily_loss_kill_switch",
    // ...}) -- se conserva sin perder informacion en err.detail, ademas de
    // un .message legible, para no romper a quien solo lea err.message.
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    if (typeof detail === "object") err.detail = detail;
    throw err;
  }
  return res.json();
}

function fmtUSD(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "--";
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "--";
  return `${v.toFixed(2)}%`;
}

function fmtLocalTime(unixSeconds) {
  if (!unixSeconds) return "--";
  return new Date(unixSeconds * 1000).toLocaleString("es-AR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function fmtLocalDateTime(unixSeconds) {
  if (!unixSeconds) return "--";
  return new Date(unixSeconds * 1000).toLocaleString("es-AR");
}

function showError(elId, err) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.textContent = `No se pudo conectar con la API: ${err.message}`;
  el.classList.add("show");
}

function clearError(elId) {
  const el = document.getElementById(elId);
  if (el) el.classList.remove("show");
}

// Deals cerrados (una fila por operacion, no por "leg" de MT5): filtra
// entry===1 (DEAL_ENTRY_OUT), que es donde MT5 asienta el profit/swap/
// comision realizado de la operacion completa.
const DEAL_ENTRY_OUT = 1;
const DEAL_TYPE_SELL = 1; // el deal DE CIERRE es lo opuesto a como se abrio la posicion:
                          // cerrar una compra se hace vendiendo (type=SELL) y viceversa.

function closedTrades(historyDeals) {
  return (historyDeals || [])
    .filter((d) => d.entry === DEAL_ENTRY_OUT)
    .map((d) => ({
      ...d,
      net: (d.profit || 0) + (d.swap || 0) + (d.commission || 0) + (d.fee || 0),
      side: d.type === DEAL_TYPE_SELL ? "compra" : "venta",
    }))
    .sort((a, b) => a.time - b.time);
}

function sideLabel(side) {
  return side === "compra" ? "Compra" : "Venta";
}

function tradeStats(trades) {
  const n = trades.length;
  const wins = trades.filter((t) => t.net > 0).length;
  const losses = trades.filter((t) => t.net < 0).length;
  const total = trades.reduce((s, t) => s + t.net, 0);
  const winRate = wins + losses > 0 ? (wins / (wins + losses)) * 100 : null;
  return { n, wins, losses, total, winRate };
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtSigned(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "--";
  return n > 0 ? `+${n}` : `${n}`;
}

// Calificación de entrada (Divergencia/Tendencia/CVP -- ver strategy/scoring.py)
// + Signal Quality (BOT-051.4): un ícono con un popover CSS que arma el
// desglose, el motivo de cada factor, y el vector de Signal Quality -- todo
// capturado en el MISMO momento causal (t0, al colocar la orden). scoresMap
// viene de GET /scores ({ticket: {...score, signal_quality,
// signal_quality_diagnostics}}); el `ticket` con el que el bot coloca la
// orden es el mismo `position_id` que trae cada deal de /history y el mismo
// `ticket` que devuelven /positions y /orders (ver execution/src/score_store.py
// y reports/BOT-051.5-* sección de identidad/linkage) -- por eso este mismo
// componente se reusa tal cual para una LIMIT pendiente (BOT-051.6, sección
// 5: visible desde que nace, no solo al cerrar), una posición abierta, o una
// fila del historial de cerradas. Sin dato para ese ticket, no muestra nada.
function scoreBadge(scoresMap, ticket) {
  const s = scoresMap && scoresMap[ticket];
  if (!s) return "";
  const cls = (v) => (v > 0 ? "ok" : v < 0 ? "bad" : "muted");
  // score/reason pueden faltar en registros de antes de agregar un factor
  // nuevo (ej. "Nodo" no existía en las primeras entradas calificadas) --
  // se omite la fila en vez de mostrar "undefined".
  const row = (label, score, reason) => {
    if (score === undefined || reason === undefined) return "";
    return `
    <div class="score-row">
      <b>${label}</b> <span class="${cls(score)}">${fmtSigned(score)}</span>
      <div class="muted">${escapeHtml(reason)}</div>
    </div>`;
  };
  const hasTotal = s.total !== undefined;
  return `
    <span class="score-badge">
      <span class="score-icon ${hasTotal ? cls(s.total) : "muted"}" tabindex="0">ⓘ${hasTotal ? " " + fmtSigned(s.total) : ""}</span>
      <div class="score-pop">
        ${row("Divergencia", s.divergencia_score, s.divergencia_reason)}
        ${row("Tendencia", s.tendencia_score, s.tendencia_reason)}
        ${row("CVP", s.cvp_score, s.cvp_reason)}
        ${row("Nodo", s.nodo_score, s.nodo_reason)}
        ${hasTotal ? `<div class="score-total">Total <b class="${cls(s.total)}">${fmtSigned(s.total)}</b> · el volumen no cambia (fixed_lot)</div>` : ""}
        ${signalQualitySection(s.signal_quality, s.signal_quality_diagnostics)}
      </div>
    </span>`;
}

// Signal Quality (BOT-051.4, ver strategy/signal_quality.py): vector crudo
// (Momentum/Alignment/Structure/Context + Direction), SIN score, SIN
// tiers/colores que impliquen un ranking -- ver
// reports/BOT-051.2-signal-quality-definition-freeze.md sección 11. Registros
// sin `signal_quality` (previos a BOT-051.4, o donde el cálculo falló) no
// muestran esta sección -- nunca "undefined", nunca un valor inventado.
// `reasonKey` indexa diagnostics.unavailable_reasons (BOT-051.5 seccion 10,
// ver strategy/signal_quality.py) -- solo presente para factores realmente
// UNAVAILABLE; registros de antes de BOT-051.5 no tienen diagnostics y el
// factor se sigue mostrando igual que antes (UNAVAILABLE sin razon).
function signalQualityFactor(label, unit, fo, reasonKey, diagnostics) {
  if (!fo) return "";
  if (fo.status !== "AVAILABLE") {
    const reason = diagnostics && diagnostics.unavailable_reasons
      ? diagnostics.unavailable_reasons[reasonKey] : undefined;
    return `<div class="sq-row sq-row-unavailable">
      <span>${label}</span><b class="sq-unavailable">UNAVAILABLE</b>
      ${reason ? `<div class="sq-reason">Reason: ${escapeHtml(reason)}</div>` : ""}
    </div>`;
  }
  // Momentum/Structure son continuos (float) -- 2 decimales solo de
  // presentación, el valor crudo sigue siendo el que persiste score_store.
  // Alignment/Context son texto (enum, NUNCA colapsado a UNAVAILABLE --
  // NEUTRAL es un VALOR de Alignment con status=AVAILABLE, no un status
  // propio, ver strategy/signal_quality.py) -- se muestran tal cual, escapados.
  const shown = typeof fo.value === "number"
    ? `${fo.value >= 0 ? "+" : ""}${fo.value.toFixed(2)}${unit ? " " + unit : ""}`
    : escapeHtml(String(fo.value));
  return `<div class="sq-row"><span>${label}</span><b>${shown}</b></div>`;
}

// BOT-051.6 sección 9 (crítica): título explícito "AL CREAR LA LIMIT (t0)" --
// esta sección es SIEMPRE el snapshot inmutable de t0
// (strategy.signal_quality.SignalQualityVectorV1, congelado al nacer la
// LIMIT), nunca el resultado del trade. Donde exista un resultado ex post
// (precio/volumen/P&L neto/hora de cierre -- BOT-051.4 ya los muestra en la
// FILA de la tabla, ver renderTradesTable()), queda visual y
// estructuralmente separado de esta caja -- nunca mezclado adentro (ver
// reports/BOT-051.5-* y el enunciado de BOT-051.6 sección 9).
function signalQualitySection(sq, diagnostics) {
  if (!sq) return "";
  return `
    <div class="sq-section">
      <div class="sq-title">Signal Quality — al crear la LIMIT (t0)</div>
      ${signalQualityFactor("Momentum", "ATR / 3 velas", sq.momentum, "momentum", diagnostics)}
      ${signalQualityFactor("Alignment", "", sq.alignment, "alignment", diagnostics)}
      ${signalQualityFactor("Structure", "ATR", sq.structure, "structure", diagnostics)}
      ${signalQualityFactor("Context", "", sq.context, "context", diagnostics)}
      <div class="sq-row sq-direction"><span>Direction</span><b>${escapeHtml(sq.direction || "--")}</b></div>
    </div>`;
}

// Tarjeta de acumulación OOS de Signal Quality (BOT-051.5) -- GET
// /signal-quality/oos-status. Solo conteos/estados de readiness
// (NO_DATA/ACCUMULATING/READY_FOR_OOS_ANALYSIS) -- sin score, sin colores de
// calidad, sin recomendaciones, sin gate.
function renderSignalQualityOos(status) {
  const el = document.getElementById("sqOosCard");
  if (!el) return;
  if (!status) {
    el.innerHTML = `<p class="muted">No disponible.</p>`;
    return;
  }
  const r = status.readiness || {};
  const sr = status.structure_replay || {};
  const factorRow = (label, state) => `
    <div class="sq-oos-readiness-item">
      <span>${label}</span>
      <b>${escapeHtml(state || "NO_DATA")}</b>
    </div>`;
  el.innerHTML = `
    <div class="sample-grid">
      <div class="sample-item"><span>LIMITs reales (desde ${fmtLocalDateTime(Math.floor(new Date(status.accumulation_start_utc).getTime() / 1000))})</span><b>${status.genuine_live_limits ?? 0}</b></div>
      <div class="sample-item"><span>Cerradas / evaluables</span><b>${status.evaluable_closed_trades ?? 0}</b></div>
      <div class="sample-item"><span>Signal Quality completo</span><b>${status.full_sq_available ?? 0} / ${status.genuine_live_limits ?? 0}</b></div>
      <div class="sample-item"><span>Structure replay</span><b>${sr.match ?? 0} match / ${sr.mismatch ?? 0} mismatch</b></div>
    </div>
    <div class="sq-oos-readiness">
      ${factorRow("Momentum", r.momentum)}
      ${factorRow("Alignment", r.alignment)}
      ${factorRow("Structure", r.structure)}
      ${factorRow("Context", r.context)}
    </div>
    <div class="sq-oos-note">Observacional -- sin score, sin gate. La acumulación ocurre en paralelo, sin bloquear el desarrollo.</div>`;
}
