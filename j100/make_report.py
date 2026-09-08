"""
make_report.py -- render the jump-difficulty analysis as a standalone HTML page.

    python make_report.py                 # -> j100_ranking.html
    python make_report.py out.html

Runs rank_jumps.analyse() and inlines the result, so the page can never drift
from the numbers. Re-run it after adding a player to Data.txt.

The page is fully self-contained: no external fonts, scripts, or images.
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import rankdata, spearmanr

import rank_jumps as R

HERE = Path(__file__).parent


def build_payload(data_path):
    players, _ = R.drop_duplicate_players(R.parse_data(data_path))
    names, fits, diff, disagree, coverage, med_att, completed, sig, offsets = R.analyse(players)

    order = list(np.argsort(diff))
    ranks = rankdata(diff)

    rows = []
    for j in range(R.N_JUMPS):
        rows.append({
            "jump": j + 1,
            "rank": int(ranks[j]),
            "d": None if np.isnan(diff[j]) else round(float(diff[j]), 3),
            "att": None if np.isnan(med_att[j]) else int(med_att[j]),
            "cov": int(coverage[j]),
            "sig": {s: (None if np.isnan(fits[s][j]) else round(float(fits[s][j]), 3))
                    for s in R.WEIGHTS},
            "by": [n for i, n in enumerate(names) if completed[i][j]],
        })

    # Signal agreement, for the scatter caption.
    ok = ~np.isnan(fits["attempts"]) & ~np.isnan(fits["rating"])
    rho_ar = float(spearmanr(fits["attempts"][ok], fits["rating"][ok]).statistic)
    okt = ~np.isnan(fits["attempts"]) & ~np.isnan(fits["time"])
    rho_at = float(spearmanr(fits["attempts"][okt], fits["time"][okt]).statistic)

    return {
        "players": [{"name": n,
                     "beat": int(completed[i].sum()),
                     "offset": round(float(offsets["attempts"][i]), 3)}
                    for i, n in enumerate(names)],
        "weights": R.WEIGHTS,
        "jumps": rows,
        "order": [int(o) for o in order],
        "rhoAttemptsRating": round(rho_ar, 3),
        "rhoAttemptsTime": round(rho_at, 3),
        "allFour": int((coverage == len(names)).sum()),
        "totalClears": int(completed.sum()),
    }


TEMPLATE = r"""<title>Jump 100 — difficulty ranking</title>
<style>
:root{
  color-scheme: light;
  --ground:#eceef1; --panel:#fafbfc; --panel-2:#f3f5f7;
  --ink:#101318; --ink-2:#565d68; --ink-3:#858c96;
  --rule:#dfe3e8; --rule-2:#eaedf0;
  --accent:#2a78d6; --accent-ink:#1c5cab;
  --ring:rgba(16,19,24,.10);
  --cov1:#cdd2d8; --cov2:#9aa3ad; --cov3:#5d6671;
  --shadow:0 1px 2px rgba(16,19,24,.05), 0 8px 24px -16px rgba(16,19,24,.28);
  --font-display:"Bahnschrift","DIN Alternate","Franklin Gothic Medium","Segoe UI",system-ui,sans-serif;
  --font-body:system-ui,"Segoe UI",Roboto,sans-serif;
  --font-mono:"Cascadia Mono","Cascadia Code",Consolas,ui-monospace,monospace;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --ground:#0b0d10; --panel:#15181d; --panel-2:#1b1f25;
    --ink:#f2f5f8; --ink-2:#a6aeb9; --ink-3:#767d87;
    --rule:#242830; --rule-2:#1e222a;
    --accent:#3987e5; --accent-ink:#86b6ef;
    --ring:rgba(255,255,255,.12);
    --cov1:#333941; --cov2:#5d6671; --cov3:#98a1ac;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -16px rgba(0,0,0,.7);
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --ground:#0b0d10; --panel:#15181d; --panel-2:#1b1f25;
  --ink:#f2f5f8; --ink-2:#a6aeb9; --ink-3:#767d87;
  --rule:#242830; --rule-2:#1e222a;
  --accent:#3987e5; --accent-ink:#86b6ef;
  --ring:rgba(255,255,255,.12);
  --cov1:#333941; --cov2:#5d6671; --cov3:#98a1ac;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -16px rgba(0,0,0,.7);
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--font-body); font-size:15px; line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1180px; margin:0 auto; padding:40px 24px 72px;
      display:flex; flex-direction:column; gap:28px}

/* ---------- header ---------- */
.masthead{display:flex; flex-direction:column; gap:10px}
.eyebrow{font-family:var(--font-mono); font-size:11px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--ink-3)}
h1{font-family:var(--font-display); font-weight:600; font-size:clamp(30px,5vw,46px);
   line-height:1.05; margin:0; letter-spacing:.005em; text-wrap:balance}
.dek{margin:0; max-width:66ch; color:var(--ink-2); font-size:16px}

/* ---------- panels ---------- */
.panel{background:var(--panel); border:1px solid var(--rule); border-radius:10px;
  padding:22px; box-shadow:var(--shadow)}
.panel > header{display:flex; flex-direction:column; gap:3px; margin-bottom:18px}
h2{font-family:var(--font-display); font-weight:600; font-size:20px; margin:0;
   letter-spacing:.01em}
.sub{margin:0; color:var(--ink-2); font-size:13.5px; max-width:78ch}

/* ---------- stat tiles ---------- */
.tiles{display:grid; gap:2px; grid-template-columns:repeat(auto-fit,minmax(148px,1fr));
  background:var(--rule); border:1px solid var(--rule); border-radius:10px; overflow:hidden}
.tile{background:var(--panel); padding:16px 18px; display:flex; flex-direction:column; gap:3px}
.tile .k{font-family:var(--font-mono); font-size:10.5px; letter-spacing:.12em;
  text-transform:uppercase; color:var(--ink-3)}
.tile .v{font-size:27px; font-weight:600; line-height:1.15}
.tile .n{font-size:12.5px; color:var(--ink-2)}

/* ---------- charts ---------- */
.scroller{overflow-x:auto; overflow-y:hidden; padding-bottom:4px}
svg{display:block}
.tick{font-family:var(--font-mono); font-size:10px; fill:var(--ink-3)}
.axlabel{font-size:11.5px; fill:var(--ink-2)}
.gridline{stroke:var(--rule-2); stroke-width:1}
.zeroline{stroke:var(--rule); stroke-width:1}
.bar{cursor:pointer}
.bar rect.fill{transition:opacity .1s; stroke:var(--ring); stroke-width:1}
.dim .bar:not(.on) rect{opacity:.34}
.dot{stroke:var(--panel); stroke-width:2; cursor:pointer}

/* ---------- legend ---------- */
.legend{display:flex; align-items:center; gap:12px; flex-wrap:wrap;
  margin-top:14px; font-size:12px; color:var(--ink-2)}
.ramp{display:flex; gap:2px}
.ramp i{width:26px; height:11px; border-radius:2px; display:block}
.heatbar{width:190px; height:11px; border-radius:3px; border:1px solid var(--ring);
  background:linear-gradient(90deg,#0d366b,#8f2020)}
.legend .cap{font-family:var(--font-mono); font-size:10.5px; letter-spacing:.09em;
  text-transform:uppercase; color:var(--ink-3)}

/* ---------- grid heatmap ---------- */
.two{display:grid; gap:28px; grid-template-columns:1fr}
@media (min-width:900px){ .two{grid-template-columns:minmax(0,1fr) minmax(0,360px)} }
.gridmap{display:grid; grid-template-columns:repeat(10,1fr); gap:3px; max-width:460px}
.cell{aspect-ratio:1; border-radius:3px; display:flex; align-items:center;
  justify-content:center; font-family:var(--font-mono); font-size:10px;
  cursor:pointer; border:1px solid var(--ring)}
.cell:focus-visible,.bar:focus-visible,.dot:focus-visible{outline:2px solid var(--accent);
  outline-offset:2px}

/* ---------- players ---------- */
.players{display:flex; flex-direction:column; gap:10px}
.prow{display:grid; grid-template-columns:1fr auto; gap:10px; align-items:baseline}
.pname{font-weight:600; font-size:14px}
.pmeta{font-family:var(--font-mono); font-size:11.5px; color:var(--ink-3)}
.pbar{grid-column:1/-1; height:6px; border-radius:3px; background:var(--panel-2);
  overflow:hidden}
.pbar i{display:block; height:100%; background:var(--accent); border-radius:3px}

/* ---------- table ---------- */
.tablewrap{max-height:460px; overflow:auto; border:1px solid var(--rule);
  border-radius:8px}
table{border-collapse:collapse; width:100%; font-size:13px}
thead th{position:sticky; top:0; background:var(--panel-2); text-align:left;
  font-family:var(--font-mono); font-size:10.5px; letter-spacing:.09em;
  text-transform:uppercase; color:var(--ink-3); font-weight:500;
  padding:9px 12px; border-bottom:1px solid var(--rule); white-space:nowrap}
tbody td{padding:7px 12px; border-bottom:1px solid var(--rule-2)}
tbody tr:last-child td{border-bottom:none}
.num{font-family:var(--font-mono); font-variant-numeric:tabular-nums; text-align:right}
.swatch{display:inline-block; width:10px; height:10px; border-radius:2px;
  vertical-align:-1px; margin-right:7px; border:1px solid var(--ring)}
.pill{display:inline-block; padding:1px 7px; border-radius:20px; font-size:11px;
  font-family:var(--font-mono); border:1px solid var(--rule); color:var(--ink-2)}

/* ---------- tooltip ---------- */
#tip{position:fixed; pointer-events:none; z-index:60; opacity:0;
  transition:opacity .09s; background:var(--panel); color:var(--ink);
  border:1px solid var(--rule); border-radius:8px; padding:10px 12px;
  box-shadow:var(--shadow); font-size:12.5px; max-width:250px; line-height:1.5}
#tip .t{font-weight:600; margin-bottom:4px; font-size:13px}
#tip .r{display:flex; justify-content:space-between; gap:14px; color:var(--ink-2)}
#tip .r b{color:var(--ink); font-family:var(--font-mono);
  font-variant-numeric:tabular-nums; font-weight:500}

/* ---------- notes ---------- */
.notes{display:grid; gap:18px; grid-template-columns:1fr}
@media (min-width:760px){ .notes{grid-template-columns:1fr 1fr} }
.note h3{font-family:var(--font-display); font-size:15px; margin:0 0 5px;
  font-weight:600; letter-spacing:.01em}
.note p{margin:0; font-size:13.5px; color:var(--ink-2)}
code{font-family:var(--font-mono); font-size:.9em; background:var(--panel-2);
  padding:1px 5px; border-radius:4px}
.foot{color:var(--ink-3); font-size:12.5px; text-align:center; margin:0}
@media (prefers-reduced-motion: reduce){ *{transition:none !important} }
</style>

<div class="wrap">

  <div class="masthead">
    <div class="eyebrow">Minr &middot; Jump 100 &middot; player telemetry</div>
    <h1>Which jumps are actually the hardest</h1>
    <p class="dek">One difficulty score per jump, fitted from attempts, self-reported
    ratings and time-on-jump across <span id="np"></span> players &mdash; using only
    the jumps each player has actually beaten.</p>
  </div>

  <div class="tiles" id="tiles"></div>

  <section class="panel">
    <header>
      <h2>The ordering</h2>
      <p class="sub">All 100 jumps, easiest to hardest. Bar height is the fitted
      difficulty in standard deviations; the zero line is an average jump. The rail
      underneath shows how many players have cleared each one &mdash; the evidence
      behind that bar.</p>
    </header>
    <div class="scroller"><svg id="rankchart" role="group"
      aria-label="Bar chart of all 100 jumps ordered easiest to hardest by fitted difficulty score."></svg></div>
    <div class="legend">
      <span class="cap">Easier</span>
      <span class="heatbar" aria-hidden="true"></span>
      <span class="cap">Harder</span>
      <span style="flex:1"></span>
      <span class="cap">Cleared by</span>
      <span class="ramp">
        <i style="background:var(--cov1)"></i><i style="background:var(--cov2)"></i>
        <i style="background:var(--cov3)"></i>
      </span>
      <span style="font-family:var(--font-mono);font-size:10.5px">2 &rarr; 4 players</span>
    </div>
  </section>

  <div class="two">
    <section class="panel">
      <header>
        <h2>Where the hard jumps live</h2>
        <p class="sub">The same scores laid over the map's physical 10&times;10 grid,
        in the layout <code>showProgress</code> prints. Row <em>i</em> is jumps
        <em>i</em>0+1 to <em>i</em>0+10.</p>
      </header>
      <div class="gridmap" id="gridmap"></div>
    </section>

    <section class="panel">
      <header>
        <h2>Do the signals agree?</h2>
        <p class="sub">Each dot is a jump: how many attempts it took, against how hard
        players said it felt. These are independent measurements.</p>
      </header>
      <div class="scroller"><svg id="scatter" role="group"
        aria-label="Scatter plot of attempts-based difficulty against rating-based difficulty for each jump."></svg></div>
      <div class="legend"><span id="rhonote"></span></div>
    </section>
  </div>

  <div class="two">
    <section class="panel">
      <header>
        <h2>Players</h2>
        <p class="sub">Offset is the model's skill estimate &mdash; how many
        log-attempts above or below the group this player runs. It is fitted from
        shared jumps, so partial progress does not distort it.</p>
      </header>
      <div class="players" id="players"></div>
    </section>

    <section class="panel">
      <header>
        <h2>Method</h2>
        <p class="sub">In short.</p>
      </header>
      <div class="notes" style="grid-template-columns:1fr">
        <div class="note">
          <h3>Beaten jumps only</h3>
          <p>An unbeaten jump's fall count is a lower bound, not a measurement, and
          an unattempted one reads as zero falls &mdash; which would look trivially easy.</p>
        </div>
        <div class="note">
          <h3>Log attempts</h3>
          <p>Clearing with probability <em>p</em> takes 1/<em>p</em> tries on average, so
          <code>log(attempts)</code> is the natural additive difficulty scale.</p>
        </div>
        <div class="note">
          <h3>Fitted, not averaged</h3>
          <p>Difficulty and player skill are solved together over observed jumps only.
          Plain averaging would penalise every jump a partially-finished player touched.</p>
        </div>
      </div>
    </section>
  </div>

  <section class="panel">
    <header>
      <h2>Every jump</h2>
      <p class="sub">The full table &mdash; the same numbers behind every chart above.
      <span id="tablenote"></span></p>
    </header>
    <div class="tablewrap">
      <table>
        <thead><tr>
          <th>Rank</th><th>Jump</th><th class="num">Difficulty</th>
          <th class="num">Attempts</th><th class="num">Cleared by</th>
          <th class="num">Attempts sig.</th><th class="num">Rating sig.</th><th class="num">Time sig.</th>
        </tr></thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </section>

  <p class="foot">Generated from <code>Data.txt</code> by <code>rank_jumps.py</code>.
  Jump numbers are physical slots &mdash; the current in-game numbering.</p>
</div>

<div id="tip" role="status" aria-live="polite"></div>

<script>
const DATA = __DATA__;
const J = DATA.jumps, NP = DATA.players.length;
const SVGNS = "http://www.w3.org/2000/svg";
const el = (t, a = {}) => { const n = document.createElementNS(SVGNS, t);
  for (const k in a) n.setAttribute(k, a[k]); return n; };

const dVals = J.map(j => j.d).filter(v => v !== null);
const dMin = Math.min(...dVals), dMax = Math.max(...dVals);
const LIM = Math.max(Math.abs(dMin), Math.abs(dMax));

/* Continuous ramp straight from dark blue to dark red, no midpoint.
   Interpolated in OKLab rather than sRGB: a raw sRGB blend between two dark
   ends muddies through a flat brown-purple, while OKLab keeps the chroma up
   and the lightness even across the middle. */
const HEAT_EASY = [13, 54, 107], HEAT_HARD = [143, 32, 32];
const toLin = c => (c /= 255, c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
const toSrgb = c => { const v = c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
  return Math.max(0, Math.min(255, v * 255)); };
function toOklab([r, g, b]){
  const R = toLin(r), G = toLin(g), B = toLin(b);
  const l = Math.cbrt(0.4122214708*R + 0.5363325363*G + 0.0514459929*B);
  const m = Math.cbrt(0.2119034982*R + 0.6806995451*G + 0.1073969566*B);
  const s = Math.cbrt(0.0883024619*R + 0.2817188376*G + 0.6299787005*B);
  return [0.2104542553*l + 0.7936177850*m - 0.0040720468*s,
          1.9779984951*l - 2.4285922050*m + 0.4505937099*s,
          0.0259040371*l + 0.7827717662*m - 0.8086757660*s];
}
function fromOklab([L, A, B2]){
  const l = (L + 0.3963377774*A + 0.2158037573*B2) ** 3;
  const m = (L - 0.1055613458*A - 0.0638541728*B2) ** 3;
  const s = (L - 0.0894841775*A - 1.2914855480*B2) ** 3;
  return [toSrgb( 4.0767416621*l - 3.3077115913*m + 0.2309699292*s),
          toSrgb(-1.2684380046*l + 2.6097574011*m - 0.3413193965*s),
          toSrgb(-0.0041960863*l - 0.7034186147*m + 1.7076147010*s)];
}
const LAB_EASY = toOklab(HEAT_EASY), LAB_HARD = toOklab(HEAT_HARD);
function mix(d){
  const t = (Math.max(-1, Math.min(1, d / LIM)) + 1) / 2;   /* 0 = easiest */
  return fromOklab(LAB_EASY.map((v, i) => v + (LAB_HARD[i] - v) * t));
}
function band(d){
  if (d === null) return "var(--rule)";
  const c = mix(d).map(Math.round);
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
/* Text sits on the fill, not on the theme surface, so pick it from the fill's
   own luminance - a token would be unreadable on white in dark mode. */
function inkOn(d){
  if (d === null) return "var(--ink-2)";
  const lin = mix(d).map(v => { v /= 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
  const lum = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
  /* 0.179 is where white and black contrast equally against a fill; it is the
     flip point that maximises the worst case (4.58:1, clearing 4.5:1). */
  return lum > 0.179 ? "#000000" : "#ffffff";
}
const covColor = c => c >= NP ? "var(--cov3)" : c >= NP - 1 ? "var(--cov2)" : "var(--cov1)";

/* ---------------- tooltip ---------------- */
const tip = document.getElementById("tip");
function showTip(e, html){
  tip.innerHTML = html; tip.style.opacity = 1;
  const r = tip.getBoundingClientRect();
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
  if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
const hideTip = () => tip.style.opacity = 0;
function jumpTip(j){
  const s = j.sig, f = v => v === null ? "&mdash;" : (v > 0 ? "+" : "") + v.toFixed(2);
  return `<div class="t">Jump ${j.jump}</div>
    <div class="r"><span>Rank</span><b>${j.rank} of 100</b></div>
    <div class="r"><span>Difficulty</span><b>${f(j.d)}</b></div>
    <div class="r"><span>Typical attempts</span><b>${j.att ?? "&mdash;"}</b></div>
    <div class="r"><span>Cleared by</span><b>${j.cov}/${NP}</b></div>
    <div class="r"><span>Attempts / rating</span><b>${f(s.attempts)} / ${f(s.rating)}</b></div>`;
}

/* ---------------- stat tiles ---------------- */
const byRank = [...J].sort((a, b) => a.rank - b.rank);
const easiest = byRank[0], hardest = byRank[byRank.length - 1];
document.getElementById("np").textContent = NP;
document.getElementById("tiles").innerHTML = [
  ["Players", NP, DATA.totalClears + " jump clears"],
  ["Hardest", "Jump " + hardest.jump, "~" + hardest.att + " attempts"],
  ["Easiest", "Jump " + easiest.jump, "~" + easiest.att + " attempt" + (easiest.att === 1 ? "" : "s")],
  ["Cleared by all", DATA.allFour, "of 100 jumps"],
  ["Signal agreement", "ρ " + DATA.rhoAttemptsRating.toFixed(2), "attempts vs rating"],
].map(([k, v, n]) =>
  `<div class="tile"><span class="k">${k}</span><span class="v">${v}</span><span class="n">${n}</span></div>`
).join("");

/* Legend swatch, sampled from the same ramp the marks use. */
document.querySelectorAll(".heatbar").forEach(b => {
  const stops = Array.from({length: 13}, (_, i) => {
    const c = mix(-LIM + (2 * LIM) * (i / 12)).map(Math.round);
    return `rgb(${c[0]},${c[1]},${c[2]}) ${(i / 12 * 100).toFixed(1)}%`;
  });
  b.style.background = `linear-gradient(90deg, ${stops.join(", ")})`;
});

/* ---------------- ranking chart ---------------- */
(function(){
  const n = J.length, bw = 8, gap = 2, step = bw + gap;
  const mL = 44, mR = 14, mT = 16, plotH = 230, railH = 12, railGap = 26, axH = 34;
  const W = mL + n * step + mR, H = mT + plotH + railGap + railH + axH;
  const svg = document.getElementById("rankchart");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", W); svg.setAttribute("height", H);

  const y = d => mT + plotH / 2 - (d / LIM) * (plotH / 2 - 6);
  const y0 = y(0);

  [-2, -1, 1, 2].forEach(v => {
    if (Math.abs(v) > LIM) return;
    svg.appendChild(el("line", {x1:mL, x2:W-mR, y1:y(v), y2:y(v), class:"gridline"}));
    const t = el("text", {x:mL-8, y:y(v)+3.5, class:"tick", "text-anchor":"end"});
    t.textContent = (v > 0 ? "+" : "") + v; svg.appendChild(t);
  });
  svg.appendChild(el("line", {x1:mL, x2:W-mR, y1:y0, y2:y0, class:"zeroline"}));
  const zt = el("text", {x:mL-8, y:y0+3.5, class:"tick", "text-anchor":"end"});
  zt.textContent = "0"; svg.appendChild(zt);

  const ordered = byRank;
  ordered.forEach((j, i) => {
    const x = mL + i * step;
    const g = el("g", {class:"bar", tabindex:"0"});
    g.setAttribute("aria-label",
      `Jump ${j.jump}, rank ${j.rank}, difficulty ${j.d === null ? "unknown" : j.d.toFixed(2)}`);
    const up = j.d >= 0, h = Math.max(1.5, Math.abs(y(j.d) - y0));
    const r = el("rect", {x, y: up ? y0 - h : y0, width:bw, height:h,
      fill: band(j.d), rx:3, class:"fill"});
    g.appendChild(r);
    /* wide invisible hit target: the 24px minimum, not the 8px bar */
    g.appendChild(el("rect", {x:x-1, y:mT, width:step+2, height:plotH,
      fill:"transparent"}));
    const on = e => { showTip(e, jumpTip(j)); svg.classList.add("dim"); g.classList.add("on"); };
    g.addEventListener("mousemove", on);
    g.addEventListener("mouseenter", on);
    g.addEventListener("focus", e => {
      const b = r.getBoundingClientRect();
      on({clientX:b.left + b.width/2, clientY:b.top});
    });
    const off = () => { hideTip(); svg.classList.remove("dim"); g.classList.remove("on"); };
    g.addEventListener("mouseleave", off);
    g.addEventListener("blur", off);
    svg.appendChild(g);

    /* coverage rail */
    const rail = el("rect", {x, y: mT + plotH + railGap, width:bw, height:railH,
      fill: covColor(j.cov), rx:2});
    svg.appendChild(rail);
  });

  /* selective direct labels: the two extremes only */
  [[0, "easiest"], [n - 1, "hardest"]].forEach(([i, txt]) => {
    const j = ordered[i], x = mL + i * step + bw / 2, up = j.d >= 0;
    const t = el("text", {x, y: up ? y(j.d) - 9 : y(j.d) + 16, class:"axlabel",
      "text-anchor": i === 0 ? "start" : "end", "font-weight":"600"});
    t.textContent = `Jump ${j.jump} · ${txt}`;
    svg.appendChild(t);
  });

  for (let i = 0; i < n; i += 10){
    const t = el("text", {x: mL + i * step + bw / 2, y: H - 12, class:"tick",
      "text-anchor":"middle"});
    t.textContent = i + 1; svg.appendChild(t);
  }
  const al = el("text", {x: mL, y: H - 1, class:"axlabel"});
  al.textContent = "position in the ordering →"; svg.appendChild(al);
  const rl = el("text", {x: mL - 8, y: mT + plotH + railGap + 9, class:"tick",
    "text-anchor":"end"});
  rl.textContent = "seen"; svg.appendChild(rl);
})();

/* ---------------- physical grid ---------------- */
(function(){
  const g = document.getElementById("gridmap");
  const byNum = {}; J.forEach(j => byNum[j.jump] = j);
  for (let i = 0; i < 10; i++) for (let k = 0; k < 10; k++){
    const j = byNum[i * 10 + k + 1];
    const c = document.createElement("div");
    c.className = "cell"; c.tabIndex = 0;
    c.style.background = band(j.d);
    c.style.color = inkOn(j.d);
    c.textContent = j.jump;
    c.setAttribute("aria-label", `Jump ${j.jump}, rank ${j.rank} of 100`);
    const on = e => showTip(e, jumpTip(j));
    c.addEventListener("mousemove", on);
    c.addEventListener("mouseenter", on);
    c.addEventListener("focus", e => {
      const b = c.getBoundingClientRect();
      on({clientX:b.left + b.width/2, clientY:b.top});
    });
    c.addEventListener("mouseleave", hideTip);
    c.addEventListener("blur", hideTip);
    g.appendChild(c);
  }
})();

/* ---------------- scatter ---------------- */
(function(){
  const pts = J.filter(j => j.sig.attempts !== null && j.sig.rating !== null);
  const S = 300, mL = 38, mB = 34, mT = 10, mR = 10;
  const W = S, H = 270, iw = W - mL - mR, ih = H - mT - mB;
  const svg = document.getElementById("scatter");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", W); svg.setAttribute("height", H);
  const lim = 2.6;
  const X = v => mL + (v + lim) / (2 * lim) * iw;
  const Y = v => mT + ih - (v + lim) / (2 * lim) * ih;

  [-2, 0, 2].forEach(v => {
    svg.appendChild(el("line", {x1:X(v), x2:X(v), y1:mT, y2:mT+ih, class:"gridline"}));
    svg.appendChild(el("line", {x1:mL, x2:mL+iw, y1:Y(v), y2:Y(v), class:"gridline"}));
    const a = el("text", {x:X(v), y:H-mB+15, class:"tick", "text-anchor":"middle"});
    a.textContent = v; svg.appendChild(a);
    const b = el("text", {x:mL-7, y:Y(v)+3.5, class:"tick", "text-anchor":"end"});
    b.textContent = v; svg.appendChild(b);
  });

  pts.forEach(j => {
    const c = el("circle", {cx:X(j.sig.attempts), cy:Y(j.sig.rating), r:4.5,
      fill:"var(--accent)", class:"dot", tabindex:"0"});
    c.setAttribute("aria-label", `Jump ${j.jump}`);
    const on = e => showTip(e, jumpTip(j));
    c.addEventListener("mousemove", on);
    c.addEventListener("mouseenter", on);
    c.addEventListener("focus", e => {
      const b = c.getBoundingClientRect();
      on({clientX:b.left + b.width/2, clientY:b.top});
    });
    c.addEventListener("mouseleave", hideTip);
    c.addEventListener("blur", hideTip);
    svg.appendChild(c);
  });

  const xl = el("text", {x:mL+iw/2, y:H-4, class:"axlabel", "text-anchor":"middle"});
  xl.textContent = "difficulty from attempts →"; svg.appendChild(xl);
  const yl = el("text", {x:12, y:mT+ih/2, class:"axlabel", "text-anchor":"middle",
    transform:`rotate(-90 12 ${mT+ih/2})`});
  yl.textContent = "difficulty from ratings →"; svg.appendChild(yl);

  document.getElementById("rhonote").innerHTML =
    `Spearman <b>ρ = ${DATA.rhoAttemptsRating.toFixed(2)}</b> &mdash; how players
     rate a jump closely tracks how many tries it took. Time agrees less
     (ρ = ${DATA.rhoAttemptsTime.toFixed(2)}), which is why it carries the least weight.`;
})();

/* ---------------- players ---------------- */
document.getElementById("players").innerHTML = DATA.players
  .slice().sort((a, b) => b.beat - a.beat).map(p => `
  <div class="prow">
    <span class="pname">${p.name}</span>
    <span class="pmeta">${p.beat}/100 beaten &middot; offset ${p.offset > 0 ? "+" : ""}${p.offset.toFixed(2)}</span>
    <span class="pbar"><i style="width:${p.beat}%"></i></span>
  </div>`).join("");

/* ---------------- table ---------------- */
document.getElementById("tablenote").textContent =
  `Sorted easiest to hardest. Signal columns are z-scores; blank means that player group left no usable reading.`;
document.getElementById("tbody").innerHTML = byRank.map(j => {
  const f = v => v === null ? '<span style="color:var(--ink-3)">&mdash;</span>'
                            : (v > 0 ? "+" : "") + v.toFixed(2);
  return `<tr>
    <td class="num">${j.rank}</td>
    <td><span class="swatch" style="background:${band(j.d)}"></span>Jump ${j.jump}</td>
    <td class="num">${f(j.d)}</td>
    <td class="num">${j.att ?? "&mdash;"}</td>
    <td class="num"><span class="pill">${j.cov}/${NP}</span></td>
    <td class="num">${f(j.sig.attempts)}</td>
    <td class="num">${f(j.sig.rating)}</td>
    <td class="num">${f(j.sig.time)}</td>
  </tr>`;
}).join("");
</script>
"""


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "j100_ranking.html"
    payload = build_payload(HERE / "j100" / "Data.txt")
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}  ({len(html):,} bytes, {len(payload['jumps'])} jumps, "
          f"{len(payload['players'])} players)")


if __name__ == "__main__":
    main()
