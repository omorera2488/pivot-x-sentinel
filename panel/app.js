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

function closedTrades(historyDeals) {
  return (historyDeals || [])
    .filter((d) => d.entry === DEAL_ENTRY_OUT)
    .map((d) => ({
      ...d,
      net: (d.profit || 0) + (d.swap || 0) + (d.commission || 0) + (d.fee || 0),
    }))
    .sort((a, b) => a.time - b.time);
}

function tradeStats(trades) {
  const n = trades.length;
  const wins = trades.filter((t) => t.net > 0).length;
  const losses = trades.filter((t) => t.net < 0).length;
  const total = trades.reduce((s, t) => s + t.net, 0);
  const winRate = wins + losses > 0 ? (wins / (wins + losses)) * 100 : null;
  return { n, wins, losses, total, winRate };
}
