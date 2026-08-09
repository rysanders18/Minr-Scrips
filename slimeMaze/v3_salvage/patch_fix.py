import re

P = r'C:\Users\ryanp\AppData\Local\Temp\claude\C--Users-ryanp-code-Minr-Scrips-slimeMaze\0a27feee-c90a-4306-93c7-69ac816bce98\scratchpad\landfix\generate_maze.py'
src = open(P, encoding='utf-8').read()

# ---- 1. replace the whole splice_landing body ----------------------------
start = src.index('    def splice_landing(self, br, tip_idx=None):')
anchor = ('    # ---- doomed pair-merges ------------------------------'
          '-------------------')
end = src.index(anchor)
assert 0 < start < end

func = '''    def splice_landing(self, br, tip_idx=None):
        # LANDING splice (user-designed): when no existing window fits
        # the dying arm, keep the seamless-teleport rule by BUILDING
        # the destination instead of finding one. The arm grows a
        # fork-free 8-bounce tail; an exact integer-translated copy of
        # [tip + tail] is erected elsewhere as a LANDING BRANCH: a
        # corridor that starts in mid-air (parentless - the player can
        # only ever be teleported onto it, new territory by
        # construction) and, past the copied stretch, runs an
        # m-bounce connector that merges onto a STABLE corridor with
        # the standard junction shape. The translation delta is a free
        # variable, solved backwards from the junction, so the landing
        # arrives exactly. Cadence: the landing root is a path start
        # (d=0, fork_gap_map gives parentless blocks 0), the ride to
        # the junction is 8 + m + 1 <= 17 bounces, the trigger sits
        # d_tip + 1 past the arm's last fork.
        #
        # SEARCH DISCIPLINE (v2, the postmortem rewrite): everything
        # speculative is placed via place() and unwound via
        # pop_block() strict LIFO, the same protocol as splice_tail.
        # The v1 implementation borrowed the branch-walk machinery
        # (step + rewind_retry) whose non-LIFO erases can neither be
        # bounded (forward-1/rewind-3 cycles hang forever) nor rolled
        # back (rollback() cannot restore what rewinds erased -> the
        # chew crashes on blocks a failed attempt ate). No shared
        # branch state is touched until the commit point.
        self.rstats['ld_call'] += 1
        if tip_idx is None:
            tip_idx = br['last']
        tip = self.blocks[tip_idx]
        if tip is None or tip['h'] is None or tip['px'] is None:
            return False
        if self.bounces_since_fork(tip_idx) + 1 > FORK_GAP_MAX:
            self.rstats['ld_guard'] += 1
            return False
        if tip['y'] - WINDOW < MORTAL_FLOOR:
            self.rstats['ld_mortal'] += 1
            return False
        dir0 = br['dir'] if br['dir'] in (-1, 1) \\
            else self.rng.choice((-1, 1))
        # candidate tail shapes: constant arc and weave, both
        # chiralities. Turn direction may vary inside a window; only
        # the entry turn matters (dw)
        seqs_tail = [[dir0] * WINDOW,
                     [-dir0] * WINDOW,
                     [dir0 * (1, -1)[k % 2] for k in range(WINDOW)],
                     [-dir0 * (1, -1)[k % 2] for k in range(WINDOW)]]
        for st in seqs_tail:
            placed = []
            px, pz, h, y, last = (tip['px'], tip['pz'], tip['h'],
                                  tip['y'], tip_idx)
            ok = True
            for t in st:
                h += t * TURN
                px += CHORD * math.cos(h)
                pz += CHORD * math.sin(h)
                y -= 1
                bx, bz = rnd(px), rnd(pz)
                if (math.hypot(px - START_X, pz - START_Z) > max_r(y)
                        or not self.clear(bx, bz, y, last)):
                    ok = False
                    break
                last = self.place(bx, y, bz, last, br['id'],
                                  f=(px, pz, h))
                placed.append(last)
            if ok and self.landing_for_tail(br, tip_idx, placed):
                return True
            for i in reversed(placed):
                self.pop_block(i)
        self.rstats['ld_nofit'] += 1
        return False

    def landing_for_tail(self, br, tip_idx, placed):
        # second half of splice_landing: given a freshly placed tail
        # (LIFO-unwindable by the caller), find a junction + connector
        # turn-sequence whose backwards-solved translation erects a
        # legal landing corridor. Commits everything and returns True,
        # or touches nothing and returns False
        S = [tip_idx] + list(placed)
        sb = [self.blocks[i] for i in S]
        c7 = sb[-1]
        h_end = c7['h']
        cpts = self.tube_pts(S)
        cbox = self.tube_box(cpts)
        # the new tail tube must not fight any existing stamp tube
        if any(self.tubes_clash(cpts, cbox, tpts, tbox)
               for tpts, tbox, _ in self.tail_tubes) \\
                or any(self.tubes_clash(cpts, cbox, opts, obox)
                       for opts, obox in self.win_tubes):
            self.rstats['ld_tailtube'] += 1
            return False
        tails = {c for sp in self.splices for c in sp['copy']}

        def stable(bid):
            # the landing merges INTO this corridor: it must never be
            # chewed later, or the junction (and with it the window
            # the tail mirrors) would dangle
            if not (isinstance(bid, int)
                    and 0 <= bid < len(self.branches)):
                return False
            b2 = self.branches[bid]
            return (b2['golden'] or b2['funnel'] or b2.get('braid')
                    or b2.get('landing') or b2['spliced']) \\
                and not b2['alive']

        ms = list(range(3, 9))
        self.rng.shuffle(ms)
        for m in ms:
            ylo = c7['y'] - 1 - m + MIN_RISE
            yhi = c7['y'] - 1 - m + SPLICE_MAX_RISE
            rows = []
            for yy in range(ylo, yhi + 1):
                rows.extend(self.by_y.get(yy, ()))
            self.rng.shuffle(rows)
            tried_j = 0
            for J in rows:
                if tried_j >= 24:
                    break
                jb = self.blocks[J]
                if jb is None or jb['h'] is None or jb['px'] is None \\
                        or jb['prev2'] is not None:
                    continue
                if J in self.win_used or J in tails \\
                        or not stable(jb['br']):
                    continue
                kids = [k for k in self.kids.get(J, ())
                        if self.blocks[k] is not None]
                if len(kids) != 1 or kids[0] in self.win_used \\
                        or self.is_multi(kids[0]):
                    continue
                kb = self.blocks[kids[0]]
                if kb['h'] is None or kb['prev2'] is not None:
                    continue
                pv = jb['prev']
                if pv is not None and (self.blocks[pv] is None
                                       or self.is_multi(pv)
                                       or pv in self.win_used):
                    continue
                t = hwrap(hn(kb['h']) - hn(jb['h']))
                if abs(t) != 1:
                    continue
                tried_j += 1
                arr2 = jb['h'] + 2 * t * TURN
                sx = jb['px'] - CHORD * math.cos(arr2)
                sz = jb['pz'] - CHORD * math.sin(arr2)
                dy = (jb['y'] + 1 + m) - c7['y']
                seqs = []
                for fin_off in (-1, 1):
                    gap = hwrap(hn(arr2) + fin_off - hn(h_end))
                    seqs.extend(turn_seqs(m, gap))
                self.rng.shuffle(seqs)
                for seq in seqs[:16]:
                    offx = offz = 0.0
                    h = h_end
                    pts = []
                    for tt in seq:
                        h += tt * TURN
                        offx += CHORD * math.cos(h)
                        offz += CHORD * math.sin(h)
                        pts.append((offx, offz, h))
                    dx = rnd((sx - offx) - c7['px'])
                    dz = rnd((sz - offz) - c7['pz'])
                    if max(abs(dx), abs(dz)) > SPLICE_MAX_D:
                        continue
                    if max(abs(dx), abs(dz)) < 14 and abs(dy) < 20:
                        continue      # decoration tube separation
                    if math.hypot(c7['px'] + dx + offx - sx,
                                  c7['pz'] + dz + offz - sz) \\
                            > MERGE_TOL:
                        continue      # integer rounding broke arrival
                    wpts = [(x + dx, z + dz, y2 + dy)
                            for x, z, y2 in cpts]
                    wbox = self.tube_box(wpts)
                    if any(self.tubes_clash(wpts, wbox, tpts, tbox)
                           for tpts, tbox, _ in self.tail_tubes):
                        continue
                    # place the 9 landing blocks (exact translation)
                    lplaced = []
                    last = None
                    ok = True
                    for bsrc in sb:
                        lx, ly, lz = (bsrc['x'] + dx, bsrc['y'] + dy,
                                      bsrc['z'] + dz)
                        if (math.hypot(bsrc['px'] + dx - START_X,
                                       bsrc['pz'] + dz - START_Z)
                                > max_r(ly)
                                or not self.clear(lx, lz, ly, last)):
                            ok = False
                            break
                        last = self.place(lx, ly, lz, last, -3,
                                          f=(bsrc['px'] + dx,
                                             bsrc['pz'] + dz,
                                             bsrc['h']))
                        lplaced.append(last)
                    if ok:
                        # connector down onto the junction slot
                        for si, (ox, oz, hh) in enumerate(pts):
                            fx = c7['px'] + dx + ox
                            fz = c7['pz'] + dz + oz
                            yy = c7['y'] + dy - si - 1
                            if (math.hypot(fx - START_X, fz - START_Z)
                                    > max_r(yy)
                                    or not self.clear(
                                        rnd(fx), rnd(fz), yy, last,
                                        extra=[(J, m - si)])):
                                ok = False
                                break
                            last = self.place(rnd(fx), yy, rnd(fz),
                                              last, -3, f=(fx, fz, hh))
                            lplaced.append(last)
                    if not ok:
                        for i in reversed(lplaced):
                            self.pop_block(i)
                        continue
                    # commit: the landing is its own (unreachable)
                    # branch; the junction ties it into the maze
                    lastb = self.blocks[last]
                    lb = self.new_branch(lastb['px'], lastb['pz'],
                                         lastb['h'], t, lastb['y'],
                                         last)
                    lb['alive'] = False
                    lb['landing'] = True
                    lb['merged'] = True
                    lb['blocks'] = list(lplaced)
                    for i in lplaced:
                        self.blocks[i]['br'] = lb['id']
                    self.set_prev(J, last)
                    jb['h2'] = arr2
                    win = lplaced[:WINDOW + 1]
                    copy = list(placed)
                    self.tail_tubes.append((cpts, cbox,
                                            set(copy) | {tip_idx}))
                    self.win_tubes.append((wpts, wbox))
                    self.splices.append({
                        'branch': br['id'],
                        'delta': (dx, dy, dz),
                        'w0': win[0],
                        'novel': True,
                        'doomed_dest': False,
                        'copy': copy, 'win': list(win)})
                    self.win_used.update(win)
                    br['blocks'].extend(placed)
                    br['last'] = copy[-1]
                    # the tail is a chain window; the landing corridor
                    # itself offers fresh never-visited windows too
                    self.windows.append({'blocks': [tip_idx] + copy,
                                         'y': self.blocks[tip_idx]['y'],
                                         'dw': hwrap(
                                             hn(sb[1]['h'])
                                             - hn(sb[0]['h']))})
                    self.register_branch_windows(br)
                    self.scan_seq_windows(lb['blocks'], self.windows)
                    self.rstats['ld_ok'] += 1
                    return True
        return False

'''
src = src[:start] + func + src[end:]

# ---- 2. chew_leaves: landing attempts once per arm, not per position ----
old = """            if self.splice_tail(br, tip_idx=i) \\
                    or self.splice_landing(br, tip_idx=i):
                br['spliced'] = True
                tail_ends.add(self.splices[-1]['copy'][-1])
                continue"""
new = """            if self.splice_tail(br, tip_idx=i):
                br['spliced'] = True
                tail_ends.add(self.splices[-1]['copy'][-1])
                continue"""
assert src.count(old) == 1
src = src.replace(old, new)

# ---- 3. chew_leaves: guard the double-erase (defense in depth) ----------
old = """            parents = [p for p in (b['prev'], b['prev2'])
                       if p is not None]
            self.erase_block(i)
            self.unspliced += 1     # counts erased blocks"""
new = """            parents = [p for p in (b['prev'], b['prev2'])
                       if p is not None]
            if self.blocks[i] is not None:
                self.erase_block(i)
            self.unspliced += 1     # counts erased blocks"""
assert src.count(old) == 1
src = src.replace(old, new)

open(P, 'w', encoding='utf-8', newline='').write(src)
print('patched')
