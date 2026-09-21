"""
BOT-051.2 -- Signal Quality Definition Freeze.

Reconstructs the frozen SignalQualityVectorV1 (momentum, alignment, structure,
context, direction) over the historical universe common to the four already-
frozen source contracts, reusing ONLY existing causal artifacts:

  - Momentum  (BOT-024.4, FREEZE_READY): roc_atr_3, RAW continuous
      source: reports/BOT-024.2-momentum-limits-xau.csv (Universe A, N=3207)
  - Alignment (BOT-047.2.3, FREEZE_READY): Structural Alignment Consensus
      source: reports/BOT-047.2.2-boundary-event-comparison-xau.csv (Universe B, N=2474)
  - Structure (BOT-048.2, ORIGIN_ONLY_FREEZE): origin_dist_atr, RAW continuous
      source: reports/BOT-048.1-structure-limits-xau.csv (Universe A, N=3207)
  - Context   (BOT-050.2, TEMPORAL_ONLY_FREEZE): weekday, RAW categorical
      source: reports/BOT-050.1-context-limits-xau.csv (Universe A, N=3207)

No feature is recomputed. No MT5 access. No outcome (pnl_r/pnl_usd/outcome)
is used to define, filter, bucket or rank any state -- outcome columns are
never even loaded into the joined vector table.

Base universe: Alignment's own causal artifact only exists for Universe B
(filled+closed trades, N=2474) -- this is an ARTIFACT scope limitation (the
Alignment contract itself is computable at limit_created_bar for any LIMIT,
filled or not), not a contract limitation. Documented explicitly, not hidden.
"""
import pandas as pd

MOMENTUM_CSV = "reports/BOT-024.2-momentum-limits-xau.csv"
ALIGNMENT_CSV = "reports/BOT-047.2.2-boundary-event-comparison-xau.csv"
STRUCTURE_CSV = "reports/BOT-048.1-structure-limits-xau.csv"
CONTEXT_CSV = "reports/BOT-050.1-context-limits-xau.csv"

ALIGNMENT_STATES = {
    "AGAINST_CONFIRMED", "AGAINST_SINGLE", "NEUTRAL",
    "ALIGNED_SINGLE", "ALIGNED_CONFIRMED", "UNAVAILABLE",
}


def consensus(b0, b1):
    """Exact rule frozen in reports/BOT-047.2.3-...FREEZE.md (verified in BOT-051.1)."""
    if b0 == "UNAVAILABLE" or b1 == "UNAVAILABLE":
        return "UNAVAILABLE"
    if b0 == "AGAINST" and b1 == "AGAINST":
        return "AGAINST_CONFIRMED"
    if b0 == "ALIGNED" and b1 == "ALIGNED":
        return "ALIGNED_CONFIRMED"
    against_count = (b0 == "AGAINST") + (b1 == "AGAINST")
    aligned_count = (b0 == "ALIGNED") + (b1 == "ALIGNED")
    if against_count == 1 and (b0 == "NEUTRAL_MIXED" or b1 == "NEUTRAL_MIXED"):
        return "AGAINST_SINGLE"
    if aligned_count == 1 and (b0 == "NEUTRAL_MIXED" or b1 == "NEUTRAL_MIXED"):
        return "ALIGNED_SINGLE"
    if b0 == "NEUTRAL_MIXED" and b1 == "NEUTRAL_MIXED":
        return "NEUTRAL"
    return "FLIP_UNDEFINED"  # AGAINST vs ALIGNED direct flip -- N=0 historically, never guessed


mom = pd.read_csv(MOMENTUM_CSV)[["trade_id", "limit_created_bar", "direction", "roc_atr_3"]]
align = pd.read_csv(ALIGNMENT_CSV)[["trade_id", "direction", "B0_alignment", "B1_alignment"]]
struct = pd.read_csv(STRUCTURE_CSV)[["trade_id", "origin_dist_atr"]]
ctx = pd.read_csv(CONTEXT_CSV)[["trade_id", "weekday"]]

print(f"N base -- Momentum source (Universe A, all LIMITs):  {len(mom)}")
print(f"N base -- Alignment source (Universe B, filled+closed): {len(align)}")
print(f"N base -- Structure source (Universe A, all LIMITs):  {len(struct)}")
print(f"N base -- Context source (Universe A, all LIMITs):    {len(ctx)}")

# duplicates check
for name, df in [("Momentum", mom), ("Alignment", align), ("Structure", struct), ("Context", ctx)]:
    dupes = df["trade_id"].duplicated().sum()
    print(f"Duplicate trade_id in {name} source: {dupes}")

align["alignment"] = [consensus(b0, b1) for b0, b1 in zip(align["B0_alignment"], align["B1_alignment"])]
n_flip_undefined = (align["alignment"] == "FLIP_UNDEFINED").sum()
print(f"\nFLIP_UNDEFINED rows (should be 0 per BOT-047.2.3): {n_flip_undefined}")

# --- Base universe = Alignment's own artifact (Universe B) ---
# Documented reason: Alignment's causal consensus was only pre-computed for
# Universe B in existing artifacts. This is the binding constraint on the
# vector's reconstructible universe today, not any of the other 3 factors.
vec = align[["trade_id", "direction", "alignment"]].merge(
    mom[["trade_id", "roc_atr_3"]], on="trade_id", how="left", validate="one_to_one", indicator="momentum_join"
).merge(
    struct, on="trade_id", how="left", validate="one_to_one", indicator="structure_join"
).merge(
    ctx, on="trade_id", how="left", validate="one_to_one", indicator="context_join"
)

n_base = len(vec)
print(f"\n=== JOIN RECONSTRUCTIBILITY (base universe = Alignment artifact, N={n_base}) ===")
for factor, col in [("momentum", "momentum_join"), ("structure", "structure_join"), ("context", "context_join")]:
    matched = (vec[col] == "both").sum()
    print(f"  {factor}: {matched}/{n_base} joined successfully")

# --- Availability semantics per factor (AVAILABLE / UNAVAILABLE) ---
vec["momentum_status"] = vec["roc_atr_3"].apply(lambda v: "UNAVAILABLE" if pd.isna(v) else "AVAILABLE")
vec["structure_status"] = vec["origin_dist_atr"].apply(lambda v: "UNAVAILABLE" if pd.isna(v) else "AVAILABLE")
vec["context_status"] = vec["weekday"].apply(lambda v: "UNAVAILABLE" if pd.isna(v) else "AVAILABLE")
vec["alignment_status"] = vec["alignment"].apply(lambda v: "UNAVAILABLE" if v == "UNAVAILABLE" else "AVAILABLE")
# NEUTRAL is a real observed value, not missing -- distinct from UNAVAILABLE by construction of consensus()

print("\n=== MISSING / AVAILABILITY PER FACTOR (N={}) ===".format(n_base))
for factor in ["momentum", "alignment", "structure", "context"]:
    status_col = f"{factor}_status"
    counts = vec[status_col].value_counts()
    n_unavail = counts.get("UNAVAILABLE", 0)
    print(f"  {factor}: UNAVAILABLE={n_unavail} ({n_unavail/n_base:.2%}), AVAILABLE={n_base - n_unavail}")

vec["all_available"] = (
    (vec["momentum_status"] == "AVAILABLE")
    & (vec["alignment_status"] == "AVAILABLE")
    & (vec["structure_status"] == "AVAILABLE")
    & (vec["context_status"] == "AVAILABLE")
)
n_complete = vec["all_available"].sum()
n_partial = n_base - n_complete
print(f"\nN fully reconstructed (4/4 AVAILABLE): {n_complete}/{n_base}")
print(f"N with >=1 UNAVAILABLE slot:            {n_partial}/{n_base}")

# --- Direction consistency check (metadata must agree across sources) ---
mom_dir = mom.set_index("trade_id")["direction"]
mismatched_direction = 0
for tid, row_dir in zip(vec["trade_id"], vec["direction"]):
    if tid in mom_dir.index and mom_dir.loc[tid] != row_dir:
        mismatched_direction += 1
print(f"\nDirection metadata mismatches (Alignment source vs Momentum source): {mismatched_direction}")

# --- Enum validity check ---
invalid_alignment = (~vec["alignment"].isin(ALIGNMENT_STATES)).sum()
print(f"Invalid Alignment enum values (should be 0): {invalid_alignment}")

# --- Universe incompatibility note ---
n_mom_not_in_base = len(mom) - n_base
print(f"\nUniverse note: Momentum/Structure/Context sources cover {len(mom)} LIMITs (Universe A, all created),")
print(f"  but Alignment's causal artifact only covers {n_base} (Universe B, filled+closed).")
print(f"  {n_mom_not_in_base} LIMITs from Universe A are NOT represented in this reconstruction")
print(f"  solely because no pre-computed Alignment artifact exists for them -- not a contract limitation.")

# --- Write audit CSV (component values only, never pnl_r/pnl_usd/outcome) ---
audit_cols = [
    "trade_id", "direction", "momentum_status", "roc_atr_3",
    "alignment_status", "alignment", "structure_status", "origin_dist_atr",
    "context_status", "weekday", "all_available",
]
vec[audit_cols].to_csv("reports/BOT-051.2-signal-quality-vector-audit-xau.csv", index=False)
print("\nWrote reports/BOT-051.2-signal-quality-vector-audit-xau.csv")
print(f"Columns written: {audit_cols}")
print("(pnl_r / pnl_usd / outcome intentionally never loaded into this script)")
