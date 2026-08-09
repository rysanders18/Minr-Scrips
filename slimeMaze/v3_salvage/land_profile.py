import sys, time, os
sys.path.insert(0, r'C:\Users\ryanp\AppData\Local\Temp\claude\C--Users-ryanp-code-Minr-Scrips-slimeMaze\0a27feee-c90a-4306-93c7-69ac816bce98\scratchpad\landfix')
import generate_maze as gm

t0 = time.time()
calls = {'n': 0, 'ok': 0, 'tsum': 0.0, 'tmax': 0.0}
orig = gm.Sim.splice_landing

def wrapped(self, br, tip_idx=None):
    s = time.time()
    r = orig(self, br, tip_idx=tip_idx)
    dt = time.time() - s
    calls['n'] += 1
    calls['tsum'] += dt
    calls['tmax'] = max(calls['tmax'], dt)
    if r:
        calls['ok'] += 1
    if calls['n'] % 25 == 0:
        print('t=%5.0fs  ld calls %5d ok %3d  time-in-ld %6.0fs  max-one-call %5.1fs'
              % (time.time() - t0, calls['n'], calls['ok'],
                 calls['tsum'], calls['tmax']), flush=True)
    return r

gm.Sim.splice_landing = wrapped

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
sim = gm.Sim(seed)
ok = sim.run()
st = sim.stats() if ok else None
print('DONE t=%.0fs ok=%s' % (time.time() - t0, ok), flush=True)
if ok:
    errs = gm.verify(sim)
    print('seed %d: viol %d (max %d), forks %d, golden %d, ggap %d, splices %d, '
          'landings %d, braids %d, gapmean %.1f, bpf %.1f, verify %d'
          % (seed, st['forkgap_viol'], st['forkgap_max'], st['forks'],
             st['golden_forks'], st['gap_max'], st['splices'],
             st['landings'], st['braids'], st['forkgap_mean'],
             st['blocks_per_fork'], len(errs)), flush=True)
    print('stages:', getattr(sim, 'gap_stages', {}), flush=True)
    ld = {k: v for k, v in sim.rstats.items() if k.startswith('ld_')}
    print('landing stats:', ld, flush=True)
else:
    print('FAIL:', sim.fail, flush=True)
