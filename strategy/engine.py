"""Motor de la estrategia — implementa docs/spec-estrategia.md al pie de la
letra (version corregida, no el Pine original). Logica pura: sin MT5, sin
red, testeable de forma aislada (ver /strategy en docs/roadmap.md).

Contrato de entrada: arrays numpy de una misma longitud n, ordenados por
tiempo ascendente:
    time_utc   int64   segundos unix, YA corregidos por el offset del broker
                        (ver backtests/src/offset.py, o el equivalente en vivo
                        de Fase 4) — se usan para alinear el bloque HTF.
    time_server int64  segundos unix, tal cual los entrega MT5 (sin corregir)
                        — se usan para contar rollovers de swap (medianoche
                        del broker, no medianoche UTC).
    open/high/low/close  float64
    spread_pts float64  campo 'spread' de copy_rates (puntos), puede ser NaN.

No repinta nada: en la barra i solo se usan datos de la barra i o anteriores.
El modelo de costos (BrokerCosts, costs.py) es un parametro — este modulo no
asume ningun broker; correrlo con costos en cero da el resultado de la
estrategia "pelada", sin fricciones.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from .costs import BrokerCosts


@dataclass(frozen=True)
class StrategyParams:
    ema_periods: int
    periodos_htf_min: int          # duracion del bloque HTF, minutos (spec-estrategia #3.1)
    buf_bp: float                  # buffer del stop, basis points del nivel
    rr: float                      # riesgo:beneficio
    max_concurrent_por_direccion: int = 1
    valid_bars: int = 10
    orden_viva: bool = True
    max_bars_trade: int = 500
    fixed_lot: float = 0.01
    entrada_viva: bool = False     # spec-estrategia.md #4.3 -- variante del Pine, default False


@dataclass
class Trade:
    direction: int
    signal_bar: int
    born_bar: int
    entry_bar: int | None
    exit_bar: int | None
    entry_price: float | None          # limite, sin ajustar
    entry_price_adj: float | None      # ajustada por spread
    stop: float
    target: float
    exit_price: float | None
    exit_price_adj: float | None
    outcome: str                       # 'win' | 'loss' | 'timeout' | 'expired' | 'discarded_stop' | 'discarded_concurrency'
    pnl_usd: float | None = None
    pnl_r: float | None = None
    nights_held: int = 0


@dataclass
class Counters:
    n_sig: int = 0
    n_fill: int = 0
    n_win: int = 0
    n_loss: int = 0
    n_none: int = 0          # expiradas sin llenar (tpAntes / muerto / caduca)
    n_open_timeout: int = 0  # abiertas cerradas por maxBarsTrade
    n_skip_stop: int = 0     # descartadas: stop del lado incorrecto
    n_skip_concurrency: int = 0  # descartadas: limite de concurrencia


@dataclass
class BacktestResult:
    params: StrategyParams
    counters: Counters
    trades: list = field(default_factory=list)   # solo trades resueltos (win/loss/timeout)

    def resolved_trades(self):
        return [t for t in self.trades if t.outcome in ("win", "loss", "timeout")]

    def expectancy_r(self) -> float:
        rs = [t.pnl_r for t in self.resolved_trades() if t.pnl_r is not None]
        return sum(rs) / len(rs) if rs else float("nan")

    def expectancy_usd(self) -> float:
        us = [t.pnl_usd for t in self.resolved_trades() if t.pnl_usd is not None]
        return sum(us) / len(us) if us else float("nan")

    def win_rate(self) -> float:
        w = self.counters.n_win
        l = self.counters.n_loss
        return w / (w + l) if (w + l) > 0 else float("nan")

    def max_drawdown_r(self) -> float:
        rs = [t.pnl_r for t in self.resolved_trades() if t.pnl_r is not None]
        if not rs:
            return float("nan")
        equity = np.cumsum(rs)
        peak = np.maximum.accumulate(equity)
        dd = peak - equity
        return float(dd.max()) if len(dd) else 0.0

    def n_trades(self) -> int:
        return len(self.resolved_trades())


def ema(close: np.ndarray, period: int) -> np.ndarray:
    """Replica ta.ema de Pine tal cual: sum := na(sum[1]) ? src : alpha*src +
    (1-alpha)*sum[1] — arranca directo en la primera barra (ema[0]=close[0]),
    SIN sembrar con una SMA de `period` barras (a diferencia de TA-Lib/MT5).
    Verificado contra la formula publicada de ta.ema, no supuesto."""
    n = len(close)
    out = np.full(n, np.nan)
    if n == 0:
        return out
    alpha = 2.0 / (period + 1)
    out[0] = close[0]
    for i in range(1, n):
        out[i] = close[i] * alpha + out[i - 1] * (1 - alpha)
    return out


def bucket_levels(time_utc: np.ndarray, high: np.ndarray, low: np.ndarray, periodos_min: int):
    """resistencia[i]/soporte[i] = high/low del bloque HTF ANTERIOR ya cerrado.
    Ver docs/spec-estrategia.md #3.3 (correccion del bug de autoarmado)."""
    n = len(time_utc)
    bucket_len_s = periodos_min * 60
    bucket_id = time_utc // bucket_len_s

    prev_high = np.full(n, np.nan)
    prev_low = np.full(n, np.nan)

    cur_bucket = bucket_id[0]
    cur_high = high[0]
    cur_low = low[0]
    have_prev = False
    ph = pl = math.nan

    for i in range(n):
        if bucket_id[i] != cur_bucket:
            ph, pl = cur_high, cur_low
            have_prev = True
            cur_bucket = bucket_id[i]
            cur_high = high[i]
            cur_low = low[i]
        else:
            if high[i] > cur_high:
                cur_high = high[i]
            if low[i] < cur_low:
                cur_low = low[i]
        if have_prev:
            prev_high[i] = ph
            prev_low[i] = pl

    return prev_high, prev_low


def _server_date(ts: int):
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


def run_backtest(
    time_utc: np.ndarray,
    time_server: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    spread_pts: np.ndarray,
    params: StrategyParams,
    costs: BrokerCosts,
    ema_line: np.ndarray | None = None,
    resistencia: np.ndarray | None = None,
    soporte: np.ndarray | None = None,
    signal_log: list | None = None,
) -> BacktestResult:
    """Los parametros ema_line/resistencia/soporte son un hook de testeo: si se
    pasan, se usan tal cual (permite construir escenarios deterministicos en
    strategy/test_engine.py sin tener que resolver EMA a mano). En el
    camino real (sweep/robustez) se dejan en None y se calculan aca.

    signal_log: si se pasa una lista, se le agrega un dict por CADA señal
    generada (bar, dir, entry, stop, target, valido) sin importar si termino
    descartada por stop invalido o por concurrencia — sirve para validar que
    live_signal.LiveSignalEngine (motor incremental de Fase 4) genera
    exactamente las mismas señales que este motor batch, ver
    strategy/test_engine.py."""
    n = len(close)
    if ema_line is None:
        ema_line = ema(close, params.ema_periods)
    if resistencia is None or soporte is None:
        resistencia, soporte = bucket_levels(time_utc, high, low, params.periodos_htf_min)
    buf = params.buf_bp / 10000.0

    armado_venta = False
    armado_compra = False

    pending: list[dict] = []   # {dir, entry, stop, target, born}
    open_pos: list[dict] = []  # {dir, stop, target, open_bar, entry_price, entry_price_adj}

    counters = Counters()
    trades: list[Trade] = []

    def risk_usd(stop, entry):
        return abs(stop - entry) * costs.contract_size * params.fixed_lot

    def close_open_trade(pos, i, outcome, exit_price):
        sp = costs.spread_price(spread_pts[i])
        exit_adj = costs.adjust_exit_price(pos["dir"], exit_price, sp)
        raw_risk = risk_usd(pos["stop"], pos["entry_price"])

        pnl_price = (pos["entry_price_adj"] - exit_adj) if pos["dir"] < 0 else (exit_adj - pos["entry_price_adj"])
        pnl_usd = pnl_price * costs.contract_size * params.fixed_lot

        open_date = _server_date(time_server[pos["open_bar"]])
        close_date = _server_date(time_server[i])
        nights = max((close_date - open_date).days, 0)
        pnl_usd -= costs.swap_total_usd(pos["dir"], params.fixed_lot, open_date, close_date)
        pnl_usd -= costs.commission_usd(params.fixed_lot)

        pnl_r = pnl_usd / raw_risk if raw_risk > 0 else float("nan")

        trades.append(Trade(
            direction=pos["dir"], signal_bar=pos["born_bar"], born_bar=pos["born_bar"],
            entry_bar=pos["open_bar"], exit_bar=i,
            entry_price=pos["entry_price"], entry_price_adj=pos["entry_price_adj"],
            stop=pos["stop"], target=pos["target"],
            exit_price=exit_price, exit_price_adj=exit_adj,
            outcome=outcome, pnl_usd=pnl_usd, pnl_r=pnl_r, nights_held=nights,
        ))
        if outcome == "win":
            counters.n_win += 1
        elif outcome == "loss":
            counters.n_loss += 1
        elif outcome == "timeout":
            counters.n_open_timeout += 1

    for i in range(1, n):
        r_i, s_i = resistencia[i], soporte[i]

        down = close[i - 1] >= ema_line[i - 1] and close[i] < ema_line[i]
        up = close[i - 1] <= ema_line[i - 1] and close[i] > ema_line[i]
        senal_venta = armado_venta and down
        senal_compra = armado_compra and up

        if senal_venta:
            armado_venta = False
        if senal_compra:
            armado_compra = False
        if not math.isnan(r_i) and high[i] >= r_i:
            armado_venta = True
        if not math.isnan(s_i) and low[i] <= s_i:
            armado_compra = True

        # --- 1. resolver ABIERTAS ---
        still_open = []
        for pos in open_pos:
            d = pos["dir"]
            hit_sl = high[i] >= pos["stop"] if d < 0 else low[i] <= pos["stop"]
            hit_tp = low[i] <= pos["target"] if d < 0 else high[i] >= pos["target"]
            too_long = (i - pos["open_bar"]) >= params.max_bars_trade
            if hit_sl:
                close_open_trade(pos, i, "loss", pos["stop"])
            elif hit_tp:
                close_open_trade(pos, i, "win", pos["target"])
            elif too_long:
                close_open_trade(pos, i, "timeout", close[i])
            else:
                still_open.append(pos)
        open_pos = still_open

        # --- 2. evaluar PENDIENTES ---
        still_pending = []
        for po in pending:
            d = po["dir"]
            # entradaViva (spec-estrategia #4.3): el nivel que se vigila para
            # el llenado sigue la EMA ACTUAL en vez de quedar fijo en la EMA
            # de la barra de señal. El stop nunca se mueve (sigue el mismo,
            # congelado desde la señal); el target sí se recalcula al llenar,
            # con el riesgo REAL observado en ese momento -- exactamente como
            # en el Pine (`entryUse`/`tpUse`, ver basecode_tradingview).
            entry_use = ema_line[i] if params.entrada_viva else po["entry"]
            touched = high[i] >= entry_use if d < 0 else low[i] <= entry_use
            if touched:
                counters.n_fill += 1
                sp = costs.spread_price(spread_pts[i])
                entry_adj = costs.adjust_entry_price(d, entry_use, sp)
                if params.entrada_viva:
                    r_now = abs(po["stop"] - entry_use)
                    target_use = entry_use - params.rr * r_now if d < 0 else entry_use + params.rr * r_now
                else:
                    target_use = po["target"]
                hit_sl = high[i] >= po["stop"] if d < 0 else low[i] <= po["stop"]
                hit_tp = low[i] <= target_use if d < 0 else high[i] >= target_use
                pos = {"dir": d, "stop": po["stop"], "target": target_use, "open_bar": i,
                       "born_bar": po["born"], "entry_price": entry_use, "entry_price_adj": entry_adj}
                if hit_sl:
                    close_open_trade(pos, i, "loss", po["stop"])
                elif hit_tp:
                    close_open_trade(pos, i, "win", target_use)
                else:
                    open_pos.append(pos)
                continue

            # tpAntes/muerto/caduca SIEMPRE contra el target/entry originales de
            # la señal -- entradaViva no cambia estas condiciones de expiracion
            # en el Pine, solo cambia que dispara el llenado y el target post-fill.
            tp_antes = low[i] <= po["target"] if d < 0 else high[i] >= po["target"]
            expired = False
            if tp_antes:
                expired = True
            elif params.orden_viva:
                muerto = high[i] >= po["stop"] if d < 0 else low[i] <= po["stop"]
                caduca = (i - po["born"]) >= params.max_bars_trade
                expired = muerto or caduca
            else:
                caduca = (i - po["born"]) >= params.valid_bars
                expired = caduca

            if expired:
                counters.n_none += 1
            else:
                still_pending.append(po)
        pending = still_pending

        # --- 3. nueva señal -> encolar orden ---
        if senal_venta or senal_compra:
            counters.n_sig += 1
            d = -1 if senal_venta else 1
            entry = ema_line[i]
            stop = r_i * (1 + buf) if d < 0 else s_i * (1 - buf)
            valid = (stop > entry) if d < 0 else (stop < entry)
            target = None
            if valid:
                risk = abs(stop - entry)
                target = entry - params.rr * risk if d < 0 else entry + params.rr * risk
            if signal_log is not None:
                signal_log.append({"bar": i, "dir": d, "entry": entry, "stop": stop,
                                    "target": target, "valido": valid})
            if not valid:
                counters.n_skip_stop += 1
            else:
                active = sum(1 for po in pending if po["dir"] == d) + sum(1 for pos in open_pos if pos["dir"] == d)
                if active >= params.max_concurrent_por_direccion:
                    counters.n_skip_concurrency += 1
                else:
                    pending.append({"dir": d, "entry": entry, "stop": stop, "target": target, "born": i})

    return BacktestResult(params=params, counters=counters, trades=trades)
