# verify_direct.py - build a seed with generate_maze_v3 and run the
# independent verify() directly, bypassing the stats gate (the gate
# rejects on fork-gap viol long before verify runs, so structural
# regressions would otherwise go unseen). Usage: python verify_direct.py [seed]
import sys
import time

import generate_maze_v3 as gm


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    t0 = time.time()
    sim = gm.Sim(seed)
    if not sim.run():
        print('seed %d: run() failed (%s)' % (seed, sim.fail))
        sys.exit(1)
    print('seed %d built in %.1fs, verifying...' % (seed, time.time() - t0))
    errs = gm.verify(sim)
    gap_errs = [e for e in errs if e.startswith('fork gap')]
    other = [e for e in errs if not e.startswith('fork gap')]
    print('verify: %d fork-gap errors (known open), %d OTHER errors'
          % (len(gap_errs), len(other)))
    for e in other[:25]:
        print('  ' + e)
    sys.exit(2 if other else 0)


if __name__ == '__main__':
    main()
