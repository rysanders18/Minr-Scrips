# emit_sandbox.py - build a seed with generate_maze_v3 and emit it to a
# SANDBOX directory, bypassing main()'s seed gate (which rejects on
# fork-gap viol > 0 and so has never let a v3 maze reach emit).
# Nothing in the repo's own slimemaze/ is touched.
# Usage: python emit_sandbox.py <seed> <outdir>
import os
import sys
import time

import generate_maze_v3 as gm


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    outdir = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else None
    if outdir is None:
        print('refusing to emit without an explicit outdir')
        sys.exit(1)
    os.makedirs(os.path.join(outdir, gm.NAMESPACE), exist_ok=True)
    t0 = time.time()
    sim = gm.Sim(seed)
    if not sim.run():
        print('seed %d: run() failed (%s)' % (seed, sim.fail))
        sys.exit(1)
    st = sim.stats()
    print('seed %d built in %.1fs: %d blocks, %d forks (%d golden), '
          '%d splices (%d novel), %d merges, %d braids, %d landings, '
          'peak %d, fork gap max %d, viol %d'
          % (seed, time.time() - t0, st['blocks'], st['forks'],
             st['golden_forks'], st['splices'], st['novel_splices'],
             st['merges'], st['braids'], st['landings'], st['peak_width'],
             st['forkgap_max'], st['forkgap_viol']))
    errs = gm.verify(sim)
    other = [e for e in errs if not e.startswith('fork gap')]
    print('verify: %d fork-gap, %d other' % (len(errs) - len(other),
                                             len(other)))
    for e in other[:15]:
        print('  ' + e)
    if other:
        print('NOT emitting: structural errors present')
        sys.exit(2)
    t1 = time.time()
    gm.emit(sim, outdir)
    print('emitted to %s in %.1fs' % (outdir, time.time() - t1))


if __name__ == '__main__':
    main()
