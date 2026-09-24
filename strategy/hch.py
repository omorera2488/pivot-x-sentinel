"""BOT-052.2 -- canonical HCH ("Lector de confluencias") contract, frozen
from BOT-052.1's causal reconstruction of the TradingView Pine indicator
(verbatim semantics, see `basecode_tradingview/Lector de confluencias.pine`
L150-L283 and `reports/BOT-052.1-confluence-reader-historical-discovery.md`
section 3.4).

SINGLE CANONICAL IMPLEMENTATION (BOT-052.2 Phase 2 requirement), shared by:
  - `scripts/confluence_reader.py::emulate_hch()` (research, batch/vectorized,
    BOT-052.1) -- now a thin wrapper that loops calling `HCHEngine.step()`
    bar by bar and fills the same preallocated numpy arrays it always did.
    Cross-checked against the 25 tests in `scripts/test_confluence_reader.py`
    (unchanged) to prove the refactor did not alter behaviour.
  - `execution/src/bot.py` (production, live incremental shadow, BOT-052.2)
    -- feeds this engine one CLOSED bar at a time as the bot's own signal
    engine (`strategy/live_signal.py`) advances.

CRITICAL STRUCTURAL NOTE (BOT-052.1 finding, preserved deliberately, do NOT
"fix"/"improve"): the geometry this class detects is NOT a textbook
head-and-shoulders. All observed historical formations occurred immediately
after an HTF block reset -- the "head" is the last extreme of the PREVIOUS
block and the "shoulders" are the reset+reform. The shoulder tolerance
(`HCH_SHOULDER_TOL`) is empirically vacuous once the head is strictly the
highest/lowest of the three (BOT-052.1 section 3.4, hallazgo 1) but is kept
literally per that report's explicit instruction not to simplify it away
without a formally demonstrated exact-equivalence proof.

SHADOW ONLY. This module's output never feeds `strategy/engine.py`,
`strategy/live_signal.py`, or any order-placement decision in
`execution/src/bot.py`. It observes the causal signal/level stream produced
elsewhere and reports what happened -- nothing here can change the number,
timing, direction, price, or size of a trade. No outcome-derived field may
ever participate in this module's calculation (mirrors the same guarantee
`strategy/signal_quality.py` already gives for Momentum/Alignment/
Structure/Context).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Frozen from BOT-052.1 (Pine L204/L243) -- the canonical value, NOT tuned.
# Empirically non-discriminating once the head is strictly the highest/lowest
# of the three (BOT-052.1 section 3.4 hallazgo 1; sensitivity 1.00/1.25/1.50
# produced identical historical HCH events; verified with a 20,000-case
# property test in scripts/test_confluence_reader.py::
# test_shoulder_tolerance_is_vacuous). Preserved literally: BOT-052.2 must
# NOT simplify this away or "optimize" it.
HCH_SHOULDER_TOL = 1.25

# BOT-052.2 Phase 1 -- output states (explicit 3-way enum, never an
# ambiguous boolean, per the task's "Output states" requirement).
HCH_STATE_HCH = "HCH"
HCH_STATE_NO_HCH = "NO_HCH"
HCH_STATE_UNAVAILABLE = "UNAVAILABLE"
HCH_STATES = (HCH_STATE_HCH, HCH_STATE_NO_HCH, HCH_STATE_UNAVAILABLE)

# Contract version stamped on every persisted snapshot (score_store.py) --
# same pattern as strategy.signal_quality.SCHEMA_VERSION. Bump only if the
# frozen semantics above ever change (they should not, absent new evidence
# reopening BOT-052.1's classification).
HCH_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class HCHStepResult:
    """One closed bar's worth of HCH engine output -- field for field the
    same per-bar values `scripts/confluence_reader.py::emulate_hch()` (before
    BOT-052.2) used to fill into its preallocated numpy arrays. See that
    function's history / `HCHEngine.step()` below for the exact Pine-line
    provenance of each field.

    `hch_sell_level`/`hch_buy_level`/`hch_sell_form_bar`/`hch_buy_form_bar`
    are captured BEFORE this bar's own consumption (Pine L273-L283) -- i.e.
    they answer "what HCH level/formation bar was active WHEN this bar's
    check ran", matching `confluence_row()`'s `hch_active_level`/
    `hch_form_bar` semantics in BOT-052.1 exactly (a level consumed by this
    same bar's pivot still shows here; it reads NaN only from the NEXT bar
    onwards)."""
    sell_pivot: bool
    buy_pivot: bool
    hch_sell_formed: bool
    hch_buy_formed: bool
    res1: float
    res2: float
    res3: float
    sop1: float
    sop2: float
    sop3: float
    hch_sell_level: float
    hch_buy_level: float
    hch_sell_form_bar: float
    hch_buy_form_bar: float
    new_res: bool
    new_sup: bool


class HCHEngine:
    """Stateful, one-bar-at-a-time HCH detector -- THE canonical
    implementation. State is exactly `res1/res2/res3` and `sop1/sop2/sop3`
    (the last 3 DISTINCT plotted resistencia/soporte values, oldest to
    newest is res3->res2->res1, continuous history, no reset -- Pine
    L187-L209/L226-L248) plus the currently-active (unconsumed) HCH
    level/formation-bar for each side. Minimal (10 floats), deterministic, no
    pandas, no network/TradingView dependency at runtime, multi-asset safe by
    construction (nothing here is hardcoded to XAUUSD -- the caller supplies
    the plotted resistencia/soporte/mintick for whichever symbol/magic it is
    tracking).

    `step()` must be called with EVERY closed bar's plotted
    resistencia/soporte, in order, with no bar skipped -- this mirrors the
    Pine's own `var` (persistent, unbounded) state exactly. It does not
    matter whether a signal fired that bar or not: new-level detection and
    pattern formation can happen on any bar (the plotted resistencia/soporte
    updates whenever the running HTF-block high/low updates, not just at
    block boundaries).

    CRITICAL (BOT-052.1 section verbatim, "raw-arrow ownership"): `sell_sig`/
    `buy_sig` must be the RAW arrow-fire booleans for that bar -- every arrow
    the strategy's signal engine produces, including ones later discarded by
    the bot for invalid stop or concurrency. The original Pine indicator's
    `plotshape` fires for every arrow regardless of what a downstream
    execution layer does with it; HCH consumes/checks against that same raw
    stream. Feeding only the ACCEPTED-LIMIT subset would silently diverge
    from the frozen Pine semantics (BOT-052.1 section 3.1)."""

    def __init__(self) -> None:
        self.res1 = self.res2 = self.res3 = math.nan
        self.sop1 = self.sop2 = self.sop3 = math.nan
        self._lvl_sell = self._lvl_buy = math.nan
        self._form_sell_bar: float = math.nan
        self._form_buy_bar: float = math.nan
        self._prev_res = self._prev_sup = math.nan

    def step(self, bar_index: int, res_plotted: float, sup_plotted: float,
             sell_sig: bool, buy_sig: bool, mintick: float) -> HCHStepResult:
        """`res_plotted`/`sup_plotted`: the PLOTTED (bucket-masked)
        resistencia/soporte for THIS bar -- NaN on the first bar of a new HTF
        block (Pine L359-L360, `nuevoBucket ? na : ...`); the caller owns
        that masking (see `execution/src/bot.py`/`scripts/confluence_reader.py`
        for the two production/research callers). `bar_index`: any
        monotonically increasing integer identifying this bar within the
        CALLER's own numbering -- only used to record where an active
        pattern formed, never compared across callers/sessions. `mintick`:
        the symbol's price resolution (XAUUSDc: 0.001, BOT-052.1 section
        3.4)."""
        isn = math.isnan
        r, s = res_plotted, sup_plotted

        # Pine L150-L151: a "new" level is any CHANGE of the plotted value
        # (including reappearance after NaN).
        new_res = (not isn(r)) and (isn(self._prev_res) or r != self._prev_res)
        new_sup = (not isn(s)) and (isn(self._prev_sup) or s != self._prev_sup)

        hch_sell_formed = hch_buy_formed = False
        if new_res:                                       # Pine L187-L209
            self.res3, self.res2, self.res1 = self.res2, self.res1, r
            if not (isn(self.res3) or isn(self.res2) or isn(self.res1)):
                altura = self.res2 - min(self.res3, self.res1)
                cabeza = self.res2 > self.res3 and self.res2 > self.res1   # strict, Pine uses >
                hombros = altura > 0 and abs(self.res3 - self.res1) <= altura * HCH_SHOULDER_TOL
                if cabeza and hombros:
                    self._lvl_sell = self.res1
                    self._form_sell_bar = float(bar_index)
                    hch_sell_formed = True
        if new_sup:                                        # Pine L226-L248 (mirror on supports)
            self.sop3, self.sop2, self.sop1 = self.sop2, self.sop1, s
            if not (isn(self.sop3) or isn(self.sop2) or isn(self.sop1)):
                altura = max(self.sop3, self.sop1) - self.sop2
                cabeza = self.sop2 < self.sop3 and self.sop2 < self.sop1
                hombros = altura > 0 and abs(self.sop3 - self.sop1) <= altura * HCH_SHOULDER_TOL
                if cabeza and hombros:
                    self._lvl_buy = self.sop1
                    self._form_buy_bar = float(bar_index)
                    hch_buy_formed = True

        # Snapshot BEFORE this bar's own consumption -- "what was active when
        # this bar's check ran" (matches confluence_row()'s
        # hch_active_level/hch_form_bar exactly, BOT-052.1).
        level_sell_at_check = self._lvl_sell
        level_buy_at_check = self._lvl_buy
        form_sell_at_check = self._form_sell_bar
        form_buy_at_check = self._form_buy_bar

        # Pine L265-L267: check = arrow fires while the plotted level still
        # equals the active HCH level (within mintick -- exact anyway, since
        # both come from the same high/low series).
        sell_pivot = (bool(sell_sig) and not isn(level_sell_at_check) and not isn(r)
                      and abs(r - level_sell_at_check) <= mintick)
        buy_pivot = (bool(buy_sig) and not isn(level_buy_at_check) and not isn(s)
                     and abs(s - level_buy_at_check) <= mintick)

        # Pine L273-L283: a used HCH level is consumed -- one check per HCH.
        if sell_pivot:
            self._lvl_sell = math.nan
        if buy_pivot:
            self._lvl_buy = math.nan

        self._prev_res, self._prev_sup = r, s

        return HCHStepResult(
            sell_pivot=sell_pivot, buy_pivot=buy_pivot,
            hch_sell_formed=hch_sell_formed, hch_buy_formed=hch_buy_formed,
            res1=self.res1, res2=self.res2, res3=self.res3,
            sop1=self.sop1, sop2=self.sop2, sop3=self.sop3,
            hch_sell_level=level_sell_at_check, hch_buy_level=level_buy_at_check,
            hch_sell_form_bar=form_sell_at_check, hch_buy_form_bar=form_buy_at_check,
            new_res=new_res, new_sup=new_sup,
        )


def hch_state_for_signal(direction: int, step: HCHStepResult) -> tuple[str, dict]:
    """Classify HCH_state (HCH/NO_HCH/UNAVAILABLE) for a signal that just
    fired on the bar `step` describes -- EXACTLY the rule
    `scripts/discover_confluence_reader_xau.py::confluence_row()` uses
    (BOT-052.1):

        have3 = the 3 pivots on THIS direction's side are all non-NaN
        HCH      if the pivot check fired this bar
        NO_HCH   if it did not fire but have3 (state known, simply no match)
        UNAVAILABLE  if have3 is False (not enough level history yet --
                     cold start / bot restart / very start of the dataset)

    Never used for any Momentum/Alignment/Structure/Context field, never
    reachable from `strategy/signal_quality.py` -- Signal Quality v1 stays
    exactly as frozen. `direction`: +1 LONG (buy side) / -1 SHORT (sell
    side), same convention as `strategy/live_signal.py::BarSignal.dir`.

    Returns `(state, audit)` where `audit` carries the 3 pivots, the active
    level and its formation bar for the side actually used -- enough to
    reproduce/debug the decision later without recomputing anything (BOT-052.2
    Phase 3). NaN values become `None` (JSON-safe -- see
    execution/src/score_store.py::_json_safe(), BOT-051.6.3, which this
    module's floats/bools/None values are already compatible with without
    needing that defense)."""
    if direction < 0:
        p1, p2, p3 = step.res1, step.res2, step.res3
        pivot = step.sell_pivot
        active_level = step.hch_sell_level
        form_bar = step.hch_sell_form_bar
    else:
        p1, p2, p3 = step.sop1, step.sop2, step.sop3
        pivot = step.buy_pivot
        active_level = step.hch_buy_level
        form_bar = step.hch_buy_form_bar

    have3 = not (math.isnan(p1) or math.isnan(p2) or math.isnan(p3))
    state = HCH_STATE_HCH if pivot else (HCH_STATE_NO_HCH if have3 else HCH_STATE_UNAVAILABLE)
    audit = {
        "hch_pivot_1": None if math.isnan(p1) else p1,
        "hch_pivot_2": None if math.isnan(p2) else p2,
        "hch_pivot_3": None if math.isnan(p3) else p3,
        "hch_active_level": None if math.isnan(active_level) else active_level,
        "hch_formation_bar": None if math.isnan(form_bar) else int(form_bar),
    }
    return state, audit
