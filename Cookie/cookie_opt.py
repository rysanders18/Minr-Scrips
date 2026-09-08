"""Cookie clicker (Minr/Theta secret) upgrade-order optimizer.

Model (from the .msc scripts / Cookie.nms):
- Player clicks 20/s. Main cookie click lands only if time since last landed
  click > cookieCooldown ms  -> landed rate m = min(20, 1000/C).
- Each landed click (main OR golden) rolls golden spawn with p = 1/G.
  Spawn picks 1 of 14 spots; if occupied, spawn is lost.
- Golden cookie click: +20*M cookies (no cooldown). Diamond (1/D of spawns): +200*M.
- Milk: 45s cycle (script @cooldown), active T seconds, multiplies ALL gains by K.
- Save-up strategy: during milk downtime, stop clicking goldens for the last tau
  seconds so up to 14 sit on the board when milk pops; click them under milk for K x.
  Held cookies block re-spawns (spot occupied) -> optimal tau = (14/a) ln K, capped.

Upgrade state = (cd, mu, go, di, milk, md, mm) = purchases made in each ladder.
Goal: minimize time to bank 100,000,000 cookies (Secret Completion Button).
Beam search over purchase order with per-state dedup (approaches DP-optimal).
"""
import math, heapq

mult_prices = [10 + 5*i*(i+1) for i in range(500)]        # stage i -> multiplier i+2
cool_prices = [10,25,100,400,800,1300,2000,3000,5000,10000,20000]
cool_vals   = [400,300,225,175,125,100,80,65,55,51,50]     # ms
gold_prices = [100,250,1000,3000,7000,12000,25000,50000,125000,250000,500000,1000000,2500000,5000000,10000000,25000000]
gold_vals   = [40,30,25,20,17,14,12,10,9,8,7,6,5,4,3,2]    # 1/G
dia_prices  = [1000,2000,4000,20000,80000,250000,450000,900000,1600000,3000000,5000000,7500000,10000000]
dia_vals    = [100,75,50,40,32,25,20,15,10,7,5,4,3]        # 1/D of goldens
mdur_prices = [50000,100000,175000,250000,400000,600000,800000,1150000,1500000,2000000]
mdur_vals   = [6,7,8,9,10,12,14,16,18,20]                  # seconds
mmul_prices = [100000,200000,400000,600000,900000,1200000,1500000,2000000,3500000,5000000,7500000]
mmul_vals   = [3,4,5,6,7,8,9,10,12,15,20]
MILK_UNLOCK = 15000
GOAL = 100_000_000.0
CYCLE = 45.0

def params(st):
    cd,mu,go,di,mk,md,mm = st
    C = 1000.0 if cd==0 else cool_vals[cd-1]
    M = 1.0 if mu==0 else (mu+1)
    G = 50.0 if go==0 else gold_vals[go-1]
    D = 500.0 if di==0 else dia_vals[di-1]
    T = 5.0 if md==0 else mdur_vals[md-1]
    K = 2.0 if mm==0 else mmul_vals[mm-1]
    return C,M,G,D,mk,T,K

def rate(st):
    C,M,G,D,mk,T,K = params(st)
    p = 1.0/G
    # golden click rate s: s = p*(m+s); m = min(1000/C, 20-s)
    m_c = 20.0*(1.0-p); s_c = 20.0*p          # click-budget-bound solution
    if 1000.0/C <= m_c:
        m = 1000.0/C; s = p*m/(1.0-p)          # cooldown-bound solution
    else:
        m, s = m_c, s_c
    V = M*(20.0*(1.0-1.0/D) + 200.0/D)         # avg value of one spawned golden
    R0 = m*M + s*V                             # cookies/sec, no milk
    if not mk:
        return R0
    a = s                                      # spawn success rate (empty board)
    if a > 1e-12:
        tau = min(CYCLE-T, (14.0/a)*math.log(K))
        b = 14.0*(1.0-math.exp(-a*tau/14.0))
        bonus = max(0.0, b*K*V - a*tau*V)      # saved-click gain minus blocked spawns
    else:
        bonus = 0.0
    return ((CYCLE-T)*R0 + T*K*R0 + bonus)/CYCLE

LADDERS = [  # (name, prices, index-in-state)
    ("cooldown", cool_prices, 0),
    ("multiplier", mult_prices, 1),
    ("golden", gold_prices, 2),
    ("diamond", dia_prices, 3),
    ("milkdur", mdur_prices, 5),
    ("milkmult", mmul_prices, 6),
]

def children(st):
    out = []
    for name, prices, idx in LADDERS:
        k = st[idx]
        if k < len(prices):
            if idx in (5,6) and not st[4]:
                continue                      # milk upgrades need milk unlocked
            ns = list(st); ns[idx] = k+1
            out.append((name, prices[k], tuple(ns)))
    if not st[4]:
        ns = list(st); ns[4] = True
        out.append(("milkunlock", MILK_UNLOCK, tuple(ns)))
    return out

def beam_search(width=600):
    start = (0,0,0,0,False,0,0)
    # node: state -> (t, bank, path)   path = list of (name, price, t_at_purchase)
    frontier = {start: (0.0, 0.0, ())}
    best_finish = None   # (t_total, path)
    for depth in range(700):
        nxt = {}
        for st,(t,bank,path) in frontier.items():
            R = rate(st)
            fin = t + (GOAL-bank)/R
            if best_finish is None or fin < best_finish[0]:
                best_finish = (fin, path)
            for name, price, ns in children(st):
                wait = max(0.0, (price-bank)/R)
                t2 = t + wait; b2 = bank + wait*R - price
                if best_finish and t2 >= best_finish[0]:
                    continue
                p2 = path + ((name, price, t2),)
                cur = nxt.get(ns)
                sc2 = t2 + (GOAL-b2)/rate(ns)
                if cur is None or sc2 < cur[3]:
                    nxt[ns] = (t2, b2, p2, sc2)
        if not nxt:
            break
        pruned = heapq.nsmallest(width, nxt.items(), key=lambda kv: kv[1][3])
        frontier = {st:(t,b,p) for st,(t,b,p,_) in pruned}
    return best_finish

fin_t, path = beam_search()
print(f"TOTAL TIME TO 100M: {fin_t:.0f}s = {fin_t/60:.1f} min = {fin_t/3600:.2f} h")
print(f"purchases: {len(path)}")
# reconstruct state along path for annotation
st = [0,0,0,0,False,0,0]
idx_of = {"cooldown":0,"multiplier":1,"golden":2,"diamond":3,"milkunlock":4,"milkdur":5,"milkmult":6}
lines = []
for name, price, t in path:
    i = idx_of[name]
    if name == "milkunlock":
        st[4] = True; val = "unlocked"
    else:
        st[i] += 1
        val = {0:lambda k: f"{cool_vals[k-1]}ms", 1:lambda k: f"x{k+1}",
               2:lambda k: f"1/{gold_vals[k-1]}", 3:lambda k: f"1/{dia_vals[k-1]}",
               5:lambda k: f"{mdur_vals[k-1]}s", 6:lambda k: f"x{mmul_vals[k-1]}"}[i](st[i])
    R = rate(tuple(st))
    lines.append((t, name, val, price, R))
for t,name,val,price,R in lines:
    print(f"{t:9.1f}s  {name:10s} -> {val:8s}  cost {price:>10,}   R={R:,.1f}/s")

# ---------- cross-check: payback greedy ----------
def greedy():
    st = (0,0,0,0,False,0,0)
    t = 0.0; bank = 0.0; path = []
    while True:
        R = rate(st)
        rem = (GOAL - bank)/R
        best = None
        for name, price, ns in children(st):
            dR = rate(ns) - R
            if dR <= 0:
                continue
            wait = max(0.0, (price - bank)/R)
            payback = wait + price/dR
            # worth buying only if it reduces total finish time (myopic test)
            fin_with = wait + (GOAL - (bank + wait*R - price))/rate(ns)
            if fin_with < rem and (best is None or payback < best[0]):
                best = (payback, name, price, ns, wait)
        if best is None:
            t += rem
            return t, path
        _, name, price, ns, wait = best
        t += wait; bank += wait*R - price; st = ns
        path.append((name, price, t, rate(ns)))

gt, gpath = greedy()
print(f"\nGREEDY TOTAL: {gt:.0f}s = {gt/60:.1f} min   purchases={len(gpath)}")
st2 = [0,0,0,0,False,0,0]
for name, price, t, R in gpath:
    i = idx_of[name]
    if name == "milkunlock": st2[4]=True; val="unlocked"
    else:
        st2[i]+=1
        val = {0:lambda k: f"{cool_vals[k-1]}ms",1:lambda k: f"x{k+1}",2:lambda k: f"1/{gold_vals[k-1]}",3:lambda k: f"1/{dia_vals[k-1]}",5:lambda k: f"{mdur_vals[k-1]}s",6:lambda k: f"x{mmul_vals[k-1]}"}[i](st2[i])
    print(f"{t:9.1f}s  {name:10s} -> {val:8s}  cost {price:>10,}   R={R:,.1f}/s")
