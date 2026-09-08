"""
rank_jumps.py -- order the 100 jumps from easiest to hardest.

Reads j100/Data.txt, a sequence of blocks:

    # <PlayerName> <Falls|Teleports|Times|Ratings|Levels Completed>
    v1, v2, ... v100          (square brackets optional, junk tolerated)

Only jumps the player has actually BEATEN are used. A "Levels Completed" block
masks that player's other three stats; a player with no such block is assumed
to have beaten all 100. This matters: an unbeaten jump's fall count is a lower
bound, not a measurement, and an unattempted jump has 0 falls, which would read
as "trivially easy" if taken at face value.

MODEL
-----
Each signal is a noisy read on one latent per-jump difficulty d_j, shifted by a
per-player offset o_p (skill / scale usage):

    signal[p][j]  =  d_j  +  o_p  +  noise

With everyone having played everything this is just "centre each player, then
average". That shortcut BREAKS once players have partial progress: someone who
has beaten only their 30 easiest jumps has a low mean, so centring on it would
push every jump they touched upward. Instead fit_additive() solves the model
jointly over the observed cells only (alternating least squares -- two-way
ANOVA with missing cells), which estimates each player's offset from the jumps
they share with everyone else. Adding a player is still just adding a row.

Transforms:

  attempts = falls + teleports + 1   (the +1 is the successful attempt)
      If each try clears with probability p, attempts ~ Geometric(p) and
      E[attempts] = 1/p, so log(attempts) = -log(p) is the natural additive
      difficulty scale. It also tames the tail (one jump has 1734 falls).

  time -- log seconds.
      NOTE ON WEIGHTS: this data was collected under the old timing, where
      fallRegion.msc only accrued time between two falls less than 60s apart --
      a jump beaten in 0 or 1 falls recorded nothing, the winning attempt was
      never timed, and any pause over a minute was thrown away. That is why
      time gets the lowest weight. touchLevel.msc now clocks from level entry
      to the gold block, so once players are recorded under the new scheme,
      raise the time weight -- it should become the single best signal.

  rating -- log of the 1-100 self-report. Log rather than raw because players
      use the scale multiplicatively (one player's "hard" is 100, another's is
      35); the additive fit then removes what is left as an offset.

Usage:  python rank_jumps.py [path/to/Data.txt] [--json out.json]
"""

import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np
from scipy.stats import rankdata, spearmanr

warnings.filterwarnings("ignore", r"Mean of empty slice")
warnings.filterwarnings("ignore", r"Degrees of freedom <= 0")

N_JUMPS = 100
WEIGHTS = {"attempts": 0.50, "rating": 0.30, "time": 0.20}

# Two-word headers are checked before one-word ones.
STAT_ALIASES_2 = {"levels completed": "completed"}
STAT_ALIASES_1 = {
    "falls": "falls", "fall": "falls",
    "teleports": "teleports", "teleport": "teleports", "tps": "teleports",
    "times": "times", "time": "times",
    "ratings": "ratings", "rating": "ratings",
    "completed": "completed", "beaten": "completed",
}


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def parse_data(path):
    """-> {player: {stat: [raw token strings]}}"""
    players, current, buffer = {}, None, []

    def flush():
        if current is None:
            return
        player, stat = current
        toks = [t.strip().strip("[]").strip() for t in " ".join(buffer).split(",")]
        if len(toks) != N_JUMPS:
            print(f"  ! {player} {stat}: {len(toks)} values, expected {N_JUMPS}",
                  file=sys.stderr)
            toks = (toks + [""] * N_JUMPS)[:N_JUMPS]
        players.setdefault(player, {})[stat] = toks

    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#"):
            head = line.lstrip("#").strip().split()
            stat = name = None
            if len(head) >= 3 and " ".join(head[-2:]).lower() in STAT_ALIASES_2:
                stat = STAT_ALIASES_2[" ".join(head[-2:]).lower()]
                name = " ".join(head[:-2])
            elif len(head) >= 2 and head[-1].lower() in STAT_ALIASES_1:
                stat = STAT_ALIASES_1[head[-1].lower()]
                name = " ".join(head[:-1])
            if stat:
                flush()
                buffer, current = [], (name, stat)
            continue
        if line and current is not None:
            buffer.append(line.strip("[]"))
    flush()
    return players


SNAPSHOT_MATCH = 0.50   # exact-fall-count agreement above which two blocks
                        # cannot plausibly be two different humans


def _fall_match_rate(a, b):
    """Fraction of jumps where two blocks record exactly the same fall count."""
    fa, fb = nums(a.get("falls", [""] * N_JUMPS)), nums(b.get("falls", [""] * N_JUMPS))
    ok = ~np.isnan(fa) & ~np.isnan(fb)
    return float(np.mean(fa[ok] == fb[ok])) if ok.any() else 0.0


def _beaten_count(blocks):
    return int(bools(blocks["completed"]).sum()) if "completed" in blocks else N_JUMPS


def drop_duplicate_players(players):
    """Collapse blocks that are the same player recorded twice.

    Catches both an unedited pasted block and, more subtly, two SNAPSHOTS of one
    player's progress taken at different times - which look like distinct people
    until you notice one's beaten set nests inside the other's and every count
    only ever went up.

    Either way, keeping both double-counts one person's attempts: it
    double-weights them in the additive fit, adds a phantom clear to each jump's
    "cleared by N", and deflates the measured disagreement, since the copy agrees
    perfectly with its original while contributing no independent evidence. The
    ranking would look more confident than the evidence supports.

    Real players overlap on only a few percent of exact fall counts, so the
    threshold is not delicate. The later snapshot (more jumps beaten) is kept.
    """
    names = list(players)
    dropped = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if a in dropped or b in dropped:
                continue
            rate = _fall_match_rate(players[a], players[b])
            if rate < SNAPSHOT_MATCH:
                continue
            keep, drop = (a, b) if _beaten_count(players[a]) >= _beaten_count(players[b]) else (b, a)
            dropped[drop] = (keep, rate)

    for drop, (keep, rate) in dropped.items():
        print(f"  ! EXCLUDED '{drop}': {rate * 100:.0f}% of its fall counts are identical "
              f"to '{keep}'.\n    These are the same player recorded twice "
              f"({_beaten_count(players[drop])} vs {_beaten_count(players[keep])} jumps beaten); "
              f"keeping the later one.", file=sys.stderr)

    return {n: b for n, b in players.items() if n not in dropped}, list(dropped)


def nums(toks):
    """Numeric tokens -> float array, junk/blank -> NaN."""
    return np.array(
        [float(t) if re.fullmatch(r"-?\d+(\.\d+)?", t) else np.nan for t in toks],
        dtype=float,
    )


def bools(toks):
    return np.array([t.lower() == "true" for t in toks], dtype=bool)


# --------------------------------------------------------------------------- #
# per-player signals, masked to beaten jumps only
# --------------------------------------------------------------------------- #
def player_signals(stats):
    blank = [""] * N_JUMPS
    falls = nums(stats.get("falls", blank))
    tps = nums(stats.get("teleports", blank))
    times = nums(stats.get("times", blank))
    rates = nums(stats.get("ratings", blank))

    # No "Levels Completed" block => that player beat all 100.
    done = bools(stats["completed"]) if "completed" in stats else np.ones(N_JUMPS, bool)

    attempts = np.nansum(np.vstack([falls, tps]), axis=0) + 1.0
    attempts[np.isnan(falls) & np.isnan(tps)] = np.nan

    times = np.where(times == 0, np.nan, times)   # 0 = never on the clock
    rates = np.where(rates > 0, rates, np.nan)

    out = {
        "attempts": np.log(attempts),
        "time": np.log(times / 1000.0),
        "rating": np.log(rates),
    }
    for k in out:                                  # beaten jumps only
        out[k] = np.where(done, out[k], np.nan)
    return out, done, attempts


# --------------------------------------------------------------------------- #
# two-way additive fit with missing cells
# --------------------------------------------------------------------------- #
def fit_additive(X, iters=2000, tol=1e-10):
    """X: players x jumps, NaN = unobserved.  Solve X_pj ~ d_j + o_p.

    Alternating least squares. Offsets are re-centred to sum to zero each
    sweep, which pins the otherwise-free additive constant.
    """
    obs = ~np.isnan(X)
    d = np.nanmean(X, axis=0)
    o = np.zeros(X.shape[0])
    for _ in range(iters):
        o_new = np.nanmean(X - d[None, :], axis=1)
        o_new = np.where(np.isnan(o_new), 0.0, o_new)
        o_new -= o_new[obs.any(axis=1)].mean()
        d_new = np.nanmean(X - o_new[:, None], axis=0)
        if np.nanmax(np.abs(d_new - d)) < tol and np.max(np.abs(o_new - o)) < tol:
            d, o = d_new, o_new
            break
        d, o = d_new, o_new
    resid = X - d[None, :] - o[:, None]
    return d, o, resid


def zs(v):
    ok = ~np.isnan(v)
    out = np.full_like(v, np.nan)
    out[ok] = (v[ok] - v[ok].mean()) / v[ok].std(ddof=1)
    return out


def analyse(players):
    names = sorted(players)
    sig, done, att = {}, {}, {}
    for n in names:
        sig[n], done[n], att[n] = player_signals(players[n])

    fits, resids, offsets = {}, {}, {}
    for s in WEIGHTS:
        X = np.vstack([sig[n][s] for n in names])
        d, o, r = fit_additive(X)
        fits[s], resids[s], offsets[s] = zs(d), r, o

    stack = np.vstack([fits[s] for s in WEIGHTS])
    w = np.array([WEIGHTS[s] for s in WEIGHTS])[:, None]
    mask = ~np.isnan(stack)
    denom = (mask * w).sum(axis=0)
    difficulty = np.nansum(np.where(mask, stack, 0) * w, axis=0) / np.where(denom > 0, denom, np.nan)

    completed = np.vstack([done[n] for n in names])
    coverage = completed.sum(axis=0)

    # Disagreement: spread of the attempts-signal residuals on each jump.
    with np.errstate(invalid="ignore"):
        disagree = np.nanstd(resids["attempts"], axis=0, ddof=1)

    med_att = np.nanmedian(
        np.vstack([np.where(done[n], att[n], np.nan) for n in names]), axis=0
    )
    return names, fits, difficulty, disagree, coverage, med_att, completed, sig, offsets


# --------------------------------------------------------------------------- #
def emit_nms(order):
    """Print the permutation constants to paste into j100.nms.

    order[r] is the 0-based SLOT (physical cell i*10+j) shown as jump r+1.
    Per-player state stays keyed by SLOT, so swapping these lines re-ranks the
    map without moving anybody's progress.
    """
    slot_of_rank = [int(s) for s in order]
    rank_of_slot = [0] * N_JUMPS
    for r, s in enumerate(slot_of_rank):
        rank_of_slot[s] = r
    assert sorted(slot_of_rank) == list(range(N_JUMPS)), "not a permutation"
    assert all(rank_of_slot[slot_of_rank[r]] == r for r in range(N_JUMPS))
    assert all(slot_of_rank[rank_of_slot[s]] == s for s in range(N_JUMPS))

    print("\n\n== Paste into j100.nms (verified inverse pair) ==")
    for nm, v in (("slotOfRank", slot_of_rank), ("rankOfSlot", rank_of_slot)):
        print(f"    Int[] {nm} = Int[" + ", ".join(map(str, v)) + "]")


def report(path, json_out=None):
    players, _ = drop_duplicate_players(parse_data(path))
    names, fits, diff, disagree, coverage, med_att, completed, sig, offsets = analyse(players)

    print(f"Players ({len(names)}): {', '.join(names)}\n")
    print("== Coverage ==")
    for i, n in enumerate(names):
        print(f"  {n:<12} beat {completed[i].sum():>3}/100")
    print(f"  jumps beaten by all {len(names)}: {(coverage == len(names)).sum()}"
          f" | by exactly 1: {(coverage == 1).sum()} | by none: {(coverage == 0).sum()}")

    print("\n== Signal agreement (Spearman, on fitted difficulty) ==")
    ss = list(WEIGHTS)
    for i, a in enumerate(ss):
        for b in ss[i + 1:]:
            ok = ~np.isnan(fits[a]) & ~np.isnan(fits[b])
            print(f"  {a:>8} vs {b:<8} rho = {spearmanr(fits[a][ok], fits[b][ok]).statistic: .2f}"
                  f"  (n={ok.sum()})")

    order = np.argsort(diff)
    print("\n== Hardest 12 ==")
    for j in order[::-1][:12]:
        print(f"  jump {j+1:>3}  d={diff[j]:+.2f}  ~{med_att[j]:>5.0f} attempts"
              f"  beaten by {coverage[j]}/{len(names)}")
    print("\n== Easiest 12 ==")
    for j in order[:12]:
        print(f"  jump {j+1:>3}  d={diff[j]:+.2f}  ~{med_att[j]:>5.0f} attempts"
              f"  beaten by {coverage[j]}/{len(names)}")

    emit_nms(order)

    if json_out:
        rows = []
        for j in range(N_JUMPS):
            rows.append({
                "jump": j + 1,
                "rank": int(rankdata(diff)[j]),
                "difficulty": None if np.isnan(diff[j]) else round(float(diff[j]), 4),
                "attempts": None if np.isnan(med_att[j]) else int(med_att[j]),
                "coverage": int(coverage[j]),
                "disagree": None if np.isnan(disagree[j]) else round(float(disagree[j]), 4),
                "signals": {s: (None if np.isnan(fits[s][j]) else round(float(fits[s][j]), 4))
                            for s in WEIGHTS},
                "players": {n: (None if np.isnan(sig[n]["attempts"][j]) else
                                round(float(sig[n]["attempts"][j]), 4)) for n in names},
                "beatenBy": [n for i, n in enumerate(names) if completed[i][j]],
            })
        Path(json_out).write_text(json.dumps({
            "players": names,
            "beatCounts": {n: int(completed[i].sum()) for i, n in enumerate(names)},
            "offsets": {n: round(float(offsets["attempts"][i]), 4) for i, n in enumerate(names)},
            "weights": WEIGHTS,
            "jumps": rows,
        }, indent=1), encoding="utf-8")
        print(f"\nwrote {json_out}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    jout = None
    if "--json" in argv:
        i = argv.index("--json")
        jout = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    args = [a for a in argv if not a.startswith("--")]
    report(args[0] if args else Path(__file__).parent / "j100" / "Data.txt", jout)
