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
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
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

// Calificación de entrada (Divergencia/Tendencia/CVP -- ver strategy/scoring.py):
// un ícono con un popover CSS que arma el desglose y el motivo de cada factor.
// scoresMap viene de GET /scores ({ticket: score}); el ticket con el que el
// bot coloca la orden es el mismo position_id que trae cada deal de /history
// (ver execution/src/score_store.py) -- sin dato para esa fila, no muestra nada
// (operaciones previas a esta función, o que el bot nunca llegó a calificar).
function scoreBadge(scoresMap, positionId) {
  const s = scoresMap && scoresMap[positionId];
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
  return `
    <span class="score-badge">
      <span class="score-icon ${cls(s.total)}" tabindex="0">ⓘ ${fmtSigned(s.total)}</span>
      <div class="score-pop">
        ${row("Divergencia", s.divergencia_score, s.divergencia_reason)}
        ${row("Tendencia", s.tendencia_score, s.tendencia_reason)}
        ${row("CVP", s.cvp_score, s.cvp_reason)}
        ${row("Nodo", s.nodo_score, s.nodo_reason)}
        <div class="score-total">Total <b class="${cls(s.total)}">${fmtSigned(s.total)}</b> · el volumen no cambia (fixed_lot)</div>
      </div>
    </span>`;
}
