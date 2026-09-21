"""
BOT-051.1 -- Signal Quality Integration Design / Contract Discovery.

Read-only reconstruction: joins the ALREADY-FROZEN, ALREADY-CAUSAL per-event
artifacts from BOT-047.2.2 (Alignment consensus inputs), BOT-048.1 (Structure,
origin_dist_atr) and BOT-050.1 (Context, weekday) on trade_id, derives the
Alignment Structural Consensus state using the exact rule frozen in
BOT-047.2.3, and reports:
  (1) causal reconstructibility of the Signal Quality vector from existing
      artifacts (no recomputation of any frozen feature, no MT5 access),
  (2) the REAL observed cardinality of the two frozen categorical dimensions
      (Alignment consensus x Context weekday) x direction, vs. the
      theoretical combinatorial space.

Does NOT touch pnl_r / pnl_usd / outcome for anything except a strict
passthrough for context in the raw print (never used to define, filter,
bucket or rank any state). No thresholds are invented. No weights are
invented. No score is produced.
"""
import pandas as pd

ALIGN_CSV = "reports/BOT-047.2.2-boundary-event-comparison-xau.csv"
STRUCT_CSV = "reports/BOT-048.1-structure-limits-xau.csv"
CTX_CSV = "reports/BOT-050.1-context-limits-xau.csv"

align = pd.read_csv(ALIGN_CSV)
struct = pd.read_csv(STRUCT_CSV)
ctx = pd.read_csv(CTX_CSV)

print(f"Alignment source rows (Universe B, filled+closed): {len(align)}")
print(f"Structure source rows (Universe A, all LIMITs):    {len(struct)}")
print(f"Context source rows (Universe A, all LIMITs):      {len(ctx)}")


def consensus(b0, b1):
    """Exact rule frozen in reports/BOT-047.2.3 ...FREEZE.md lines ~116-128."""
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
    if against_count == 1 and aligned_count == 1:
        # AGAINST vs ALIGNED direct flip -- undefined by construction, N=0
        # observed historically per BOT-047.2.3. Flag explicitly, do not guess.
        return "FLIP_UNDEFINED"
    return "UNCLASSIFIED"


align = align.copy()
align["alignment_consensus"] = [
    consensus(b0, b1) for b0, b1 in zip(align["B0_alignment"], align["B1_alignment"])
]

print("\nConsensus state distribution (should match BOT-047.2.3 Table, N=2474):")
print(align["alignment_consensus"].value_counts())

# --- Join on trade_id: Alignment (Universe B) x Structure (Universe A) x Context (Universe A) ---
merged = align[["trade_id", "direction", "alignment_consensus"]].merge(
    struct[["trade_id", "origin_dist_atr"]], on="trade_id", how="left", validate="one_to_one"
).merge(
    ctx[["trade_id", "weekday"]], on="trade_id", how="left", validate="one_to_one"
)

n_unmatched_struct = merged["origin_dist_atr"].isna().sum()
n_unmatched_ctx = merged["weekday"].isna().sum()
print(f"\nJoin reconstructibility check (trade_id key):")
print(f"  Alignment events (Universe B): {len(align)}")
print(f"  Successfully joined to Structure (origin_dist_atr): {len(merged) - n_unmatched_struct}/{len(merged)}")
print(f"  Successfully joined to Context (weekday):            {len(merged) - n_unmatched_ctx}/{len(merged)}")

# --- Cardinality: only the frozen CATEGORICAL dims (Alignment x weekday x direction) ---
# Structure (origin_dist_atr) is continuous RAW by design -- not binned, not
# part of the combinatorial count (per its own frozen contract, ORIGIN_ONLY_FREEZE
# explicitly rejected inventing bins/states for it).
cat = merged[merged["alignment_consensus"].isin(
    ["AGAINST_CONFIRMED", "AGAINST_SINGLE", "NEUTRAL", "ALIGNED_SINGLE", "ALIGNED_CONFIRMED", "UNAVAILABLE"]
)]

n_align_states = 6  # incl. UNAVAILABLE
n_weekday_states = ctx["weekday"].nunique()
n_direction_states = merged["direction"].nunique()
theoretical = n_align_states * n_weekday_states * n_direction_states

combo_counts = cat.groupby(["alignment_consensus", "weekday", "direction"]).size()
observed = len(combo_counts)

print(f"\n=== CARDINALITY (Alignment consensus x weekday x direction) ===")
print(f"Alignment consensus states (incl. UNAVAILABLE): {n_align_states}")
print(f"Weekday states observed in data:                {n_weekday_states} -> {sorted(ctx['weekday'].unique())}")
print(f"Direction states:                                {n_direction_states} -> {sorted(merged['direction'].unique())}")
print(f"Theoretical combinations:                        {theoretical}")
print(f"Observed (non-empty) combinations:                {observed}")
print(f"Unobserved combinations:                          {theoretical - observed}")
print(f"Rare combinations (N<=5):                         {(combo_counts <= 5).sum()}")
print(f"Combinations with N>=20:                          {(combo_counts >= 20).sum()}")

combo_counts.sort_values(ascending=True).to_csv(
    "reports/BOT-051.1-vector-cardinality-xau.csv", header=["n_events"]
)
print("\nWrote reports/BOT-051.1-vector-cardinality-xau.csv")

# Sanity: FLIP_UNDEFINED / UNCLASSIFIED must be empty given documented N=0 flip case.
weird = align[align["alignment_consensus"].isin(["FLIP_UNDEFINED", "UNCLASSIFIED"])]
print(f"\nFLIP_UNDEFINED/UNCLASSIFIED rows (should be 0 per BOT-047.2.3): {len(weird)}")
