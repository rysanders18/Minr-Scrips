// engine.js — faithful JavaScript recreation of the rychess MSC engine.
//
// Ported 1:1 from the .msc sources so that chooseMove() returns the exact
// same move the in-game engine plays. Everything that affects move choice
// is replicated:
//   - move encoding: move = from + to*64 + promo*4096 + flags*32768
//   - genAllPseudoLegal square scan order (0..63) and per-piece offset order
//   - genOrderedLegalMoves scoring (MVV/LVA +10000 for captures, destination
//     PST for quiet moves) and its stable sort (desc score, asc index)
//   - chooseMove: searchDepth=2, maxBranches=20, per-move legality filter,
//     strict '>' tie-break (first move in order wins ties)
//   - searchInner: maxBranches=5, fail-soft alpha-beta, depth-1 leaves go
//     to recapture-only qsearch seeded with moveTo(move)
//   - qsearch: stand-pat, in-check evasion branch over full legal moves,
//     recapture loop over pseudo-legal flags==1 captures onto recaptureSq,
//     hard cap at qsDepth >= 8
//   - evaluate: incrementally-maintained material+PST score (white POV),
//     sign-flipped for black
//   - variant pawn rules: lateral move/capture, double-push from any rank,
//     auto-queen on back rank, lateral pawn attacks in isSquareAttacked
//   - makeMove/unmakeMove including the exact castling-rights updates
//
// Pieces: 0=empty, 1-6 white P N B R Q K, 7-12 black P N B R Q K.
// Squares: 0=a1, 7=h1, 56=a8, 63=h8. file=sq%8, rank=sq>>3.

'use strict';

// ---------------------------------------------------------------- constants

const VALUES = [0, 100, 320, 330, 500, 900, 20000];

const PAWN_PST = [0, 0, 0, 0, 0, 0, 0, 0, -5, 0, 0, -30, -30, 0, 0, -5, 5, -5, -10, 0, 0, -10, -5, 5, 0, 0, 0, 20, 20, 0, 0, 0, 5, 5, 10, 25, 25, 10, 5, 5, 10, 10, 20, 30, 30, 20, 10, 10, 50, 50, 50, 50, 50, 50, 50, 50, 0, 0, 0, 0, 0, 0, 0, 0];
const KNIGHT_PST = [-50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 5, 5, 0, -20, -40, -30, 5, 10, 15, 15, 10, 5, -30, -30, 0, 15, 20, 20, 15, 0, -30, -30, 5, 15, 20, 20, 15, 5, -30, -30, 0, 10, 15, 15, 10, 0, -30, -40, -20, 0, 0, 0, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50];
const BISHOP_PST = [-20, -10, -10, -10, -10, -10, -10, -20, -10, 5, 0, 0, 0, 0, 5, -10, -10, 10, 10, 10, 10, 10, 10, -10, -10, 0, 10, 10, 10, 10, 0, -10, -10, 5, 5, 10, 10, 5, 5, -10, -10, 0, 5, 10, 10, 5, 0, -10, -10, 0, 0, 0, 0, 0, 0, -10, -20, -10, -10, -10, -10, -10, -10, -20];
const ROOK_PST = [-50, 0, 0, 5, 5, 0, 0, -50, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, 5, 10, 10, 10, 10, 10, 10, 5, 0, 0, 0, 0, 0, 0, 0, 0];
const QUEEN_PST = [-20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 5, 0, 0, 0, 0, -10, -10, 5, 5, 5, 5, 5, 0, -10, 0, 0, 5, 5, 5, 5, 0, -5, -5, 0, 5, 5, 5, 5, 0, -5, -10, 0, 5, 5, 5, 5, 0, -10, -10, 0, 0, 0, 0, 0, 0, -10, -20, -10, -10, -5, -5, -10, -10, -20];
const KING_PST = [20, 30, 10, 0, 0, 10, 30, 20, 20, 20, 0, 0, 0, 0, 20, 20, -10, -20, -20, -20, -20, -20, -20, -10, -20, -30, -30, -40, -40, -30, -30, -20, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30];

const PSTS = [null, PAWN_PST, KNIGHT_PST, BISHOP_PST, ROOK_PST, QUEEN_PST, KING_PST];

// CONTRIB[piece][sq] = signed material+PST contribution (pieceContrib.msc)
const CONTRIB = [];
for (let piece = 0; piece <= 12; piece++) {
    const row = new Int32Array(64);
    if (piece !== 0) {
        const type = piece >= 7 ? piece - 6 : piece;
        const sign = piece >= 7 ? -1 : 1;
        for (let sq = 0; sq < 64; sq++) {
            const pstSq = sign === -1 ? (7 - (sq >> 3)) * 8 + (sq & 7) : sq;
            row[sq] = sign * (VALUES[type] + PSTS[type][pstSq]);
        }
    }
    CONTRIB.push(row);
}

// Precomputed target lists, preserving the MSC offset ORDER exactly.
// Knight: dx=[-2,-1,1,2,2,1,-1,-2], dy=[-1,-2,-2,-1,1,2,2,1]
// King:   dx=[-1,0,1,1,1,0,-1,-1],  dy=[-1,-1,-1,0,1,1,1,0]
const KNIGHT_TGT = [], KING_TGT = [];
{
    const kdx = [-2, -1, 1, 2, 2, 1, -1, -2], kdy = [-1, -2, -2, -1, 1, 2, 2, 1];
    const gdx = [-1, 0, 1, 1, 1, 0, -1, -1], gdy = [-1, -1, -1, 0, 1, 1, 1, 0];
    for (let sq = 0; sq < 64; sq++) {
        const f = sq & 7, r = sq >> 3;
        const kn = [], kg = [];
        for (let i = 0; i < 8; i++) {
            const tf = f + kdx[i], tr = r + kdy[i];
            if (tf >= 0 && tf <= 7 && tr >= 0 && tr <= 7) kn.push(tr * 8 + tf);
        }
        for (let i = 0; i < 8; i++) {
            const tf = f + gdx[i], tr = r + gdy[i];
            if (tf >= 0 && tf <= 7 && tr >= 0 && tr <= 7) kg.push(tr * 8 + tf);
        }
        KNIGHT_TGT.push(kn);
        KING_TGT.push(kg);
    }
}

// Rays per square, preserving direction order.
// Rook dirs:   (0,1),(1,0),(0,-1),(-1,0)   Bishop dirs: (1,1),(1,-1),(-1,-1),(-1,1)
function buildRays(dxs, dys) {
    const all = [];
    for (let sq = 0; sq < 64; sq++) {
        const f = sq & 7, r = sq >> 3;
        const rays = [];
        for (let d = 0; d < 4; d++) {
            const ray = [];
            let cf = f, cr = r;
            for (let s = 0; s < 7; s++) {
                cf += dxs[d]; cr += dys[d];
                if (cf < 0 || cf > 7 || cr < 0 || cr > 7) break;
                ray.push(cr * 8 + cf);
            }
            rays.push(ray);
        }
        all.push(rays);
    }
    return all;
}
const ROOK_RAYS = buildRays([0, 1, 0, -1], [1, 0, -1, 0]);
const BISHOP_RAYS = buildRays([1, 1, -1, -1], [1, -1, -1, 1]);

// ------------------------------------------------------------------- state

function newState() {
    return {
        board: new Int8Array(64),
        stm: 0,          // 0 = white, 1 = black
        castling: 15,    // 1=WK 2=WQ 4=BK 8=BQ
        ep: -1,
        halfmove: 0,
        fullmove: 1,
        running: 0,      // incremental material+PST, white POV
        undo: [],        // stack of [capturedPiece, castling, ep, halfmove, running]
    };
}

function startPos() {
    const st = newState();
    st.board.set([4, 2, 3, 5, 6, 3, 2, 4, 1, 1, 1, 1, 1, 1, 1, 1,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        7, 7, 7, 7, 7, 7, 7, 7, 10, 8, 9, 11, 12, 9, 8, 10]);
    let total = 0;
    for (let sq = 0; sq < 64; sq++) total += CONTRIB[st.board[sq]][sq];
    st.running = total; // 0 from the symmetric start, computed anyway (boardStartPos.msc)
    return st;
}

// --------------------------------------------------------------- move codec

const moveFrom = m => m & 63;
const moveTo = m => (m >> 6) & 63;
const movePromo = m => (m >> 12) & 7;
const moveFlags = m => (m >> 15) & 7;
const enc = (from, to, promo, flags) => from + to * 64 + promo * 4096 + flags * 32768;

const FILES = 'abcdefgh';
const squareName = sq => FILES[sq & 7] + ((sq >> 3) + 1);
function moveName(m) {
    const f = moveFlags(m);
    let s = squareName(moveFrom(m)) + squareName(moveTo(m));
    if (movePromo(m)) s += '=Q';
    if (f === 3) s += ' e.p.';
    if (f === 4) s += ' (O-O)';
    if (f === 5) s += ' (O-O-O)';
    return s;
}

// ---------------------------------------------------------------- move gen

// genPawnMoves.msc — order: single push, double push, cap left, cap right,
// ep left, ep right, lateral left, lateral right.
function genPawnMoves(st, sq, out) {
    const b = st.board;
    const piece = b[sq];
    const white = piece <= 6;
    const file = sq & 7, rank = sq >> 3;
    const forward = white ? 8 : -8;
    const backRank = white ? 7 : 0;
    const step = white ? 1 : -1;

    if (rank !== backRank) {
        const onePushPromo = (rank + step) === backRank ? 4 : 0;
        const twoPushPromo = (rank + 2 * step) === backRank ? 4 : 0;

        const oneStep = sq + forward;
        if (b[oneStep] === 0) out.push(enc(sq, oneStep, onePushPromo, 0));

        const twoStep = sq + 2 * forward;
        if (twoStep >= 0 && twoStep <= 63 && b[oneStep] === 0 && b[twoStep] === 0)
            out.push(enc(sq, twoStep, twoPushPromo, 2));

        if (file > 0) {
            const cl = sq + forward - 1, p = b[cl];
            if (p !== 0 && (p <= 6) !== white) out.push(enc(sq, cl, onePushPromo, 1));
        }
        if (file < 7) {
            const cr = sq + forward + 1, p = b[cr];
            if (p !== 0 && (p <= 6) !== white) out.push(enc(sq, cr, onePushPromo, 1));
        }
        const ep = st.ep;
        if (ep >= 0) {
            if (file > 0 && sq + forward - 1 === ep) out.push(enc(sq, ep, onePushPromo, 3));
            if (file < 7 && sq + forward + 1 === ep) out.push(enc(sq, ep, onePushPromo, 3));
        }
    }
    // VARIANT: lateral move or capture
    if (file > 0) {
        const l = sq - 1, p = b[l];
        if (p === 0) out.push(enc(sq, l, 0, 0));
        else if ((p <= 6) !== white) out.push(enc(sq, l, 0, 1));
    }
    if (file < 7) {
        const r = sq + 1, p = b[r];
        if (p === 0) out.push(enc(sq, r, 0, 0));
        else if ((p <= 6) !== white) out.push(enc(sq, r, 0, 1));
    }
}

function genJumpMoves(st, sq, targets, out) { // knight & plain king steps
    const b = st.board;
    const white = b[sq] <= 6;
    for (const t of targets) {
        const p = b[t];
        if (p === 0) out.push(enc(sq, t, 0, 0));
        else if ((p <= 6) !== white) out.push(enc(sq, t, 0, 1));
    }
}

function genRayMoves(st, sq, rays, out) {
    const b = st.board;
    const white = b[sq] <= 6;
    for (const ray of rays) {
        for (const t of ray) {
            const p = b[t];
            if (p === 0) { out.push(enc(sq, t, 0, 0)); continue; }
            if ((p <= 6) !== white) out.push(enc(sq, t, 0, 1));
            break;
        }
    }
}

// genKingMoves.msc — 8 steps then castling (pre-filtered for check/through-check)
function genKingMoves(st, sq, out) {
    genJumpMoves(st, sq, KING_TGT[sq], out);
    const b = st.board, c = st.castling;
    const white = b[sq] <= 6;
    if (white && sq === 4) {
        if ((c & 1) && b[5] === 0 && b[6] === 0 &&
            !isSquareAttacked(st, 4, 1) && !isSquareAttacked(st, 5, 1) && !isSquareAttacked(st, 6, 1))
            out.push(enc(4, 6, 0, 4));
        if ((c & 2) && b[1] === 0 && b[2] === 0 && b[3] === 0 &&
            !isSquareAttacked(st, 4, 1) && !isSquareAttacked(st, 3, 1) && !isSquareAttacked(st, 2, 1))
            out.push(enc(4, 2, 0, 5));
    }
    if (!white && sq === 60) {
        if ((c & 4) && b[61] === 0 && b[62] === 0 &&
            !isSquareAttacked(st, 60, 0) && !isSquareAttacked(st, 61, 0) && !isSquareAttacked(st, 62, 0))
            out.push(enc(60, 62, 0, 4));
        if ((c & 8) && b[57] === 0 && b[58] === 0 && b[59] === 0 &&
            !isSquareAttacked(st, 60, 0) && !isSquareAttacked(st, 59, 0) && !isSquareAttacked(st, 58, 0))
            out.push(enc(60, 58, 0, 5));
    }
}

// genAllPseudoLegal.msc — squares 0..63 in order, dispatch by piece type
function genAllPseudoLegal(st) {
    const out = [];
    const b = st.board, stm = st.stm;
    for (let sq = 0; sq < 64; sq++) {
        const piece = b[sq];
        if (piece === 0) continue;
        if ((piece <= 6 ? 0 : 1) !== stm) continue;
        const type = piece >= 7 ? piece - 6 : piece;
        switch (type) {
            case 1: genPawnMoves(st, sq, out); break;
            case 2: genJumpMoves(st, sq, KNIGHT_TGT[sq], out); break;
            case 3: genRayMoves(st, sq, BISHOP_RAYS[sq], out); break;
            case 4: genRayMoves(st, sq, ROOK_RAYS[sq], out); break;
            case 5: genRayMoves(st, sq, ROOK_RAYS[sq], out); genRayMoves(st, sq, BISHOP_RAYS[sq], out); break; // queen = rook then bishop
            case 6: genKingMoves(st, sq, out); break;
        }
    }
    return out;
}

// -------------------------------------------------------------- attack test

// isSquareAttacked.msc — pawn diagonals, VARIANT pawn laterals, knight,
// king, rook/queen rays, bishop/queen rays. Same order (order only matters
// for speed, result is a boolean).
function isSquareAttacked(st, sq, byColor) {
    const b = st.board;
    const f = sq & 7, r = sq >> 3;
    const pawn = byColor === 1 ? 7 : 1;
    if (byColor === 0) {
        if (f > 0 && r > 0 && b[sq - 9] === pawn) return true;
        if (f < 7 && r > 0 && b[sq - 7] === pawn) return true;
    } else {
        if (f > 0 && r < 7 && b[sq + 7] === pawn) return true;
        if (f < 7 && r < 7 && b[sq + 9] === pawn) return true;
    }
    if (f > 0 && b[sq - 1] === pawn) return true; // variant lateral
    if (f < 7 && b[sq + 1] === pawn) return true;

    const knight = byColor === 1 ? 8 : 2;
    for (const t of KNIGHT_TGT[sq]) if (b[t] === knight) return true;

    const king = byColor === 1 ? 12 : 6;
    for (const t of KING_TGT[sq]) if (b[t] === king) return true;

    const rook = byColor === 1 ? 10 : 4;
    const queen = byColor === 1 ? 11 : 5;
    for (const ray of ROOK_RAYS[sq]) {
        for (const t of ray) {
            const p = b[t];
            if (p === 0) continue;
            if (p === rook || p === queen) return true;
            break;
        }
    }
    const bishop = byColor === 1 ? 9 : 3;
    for (const ray of BISHOP_RAYS[sq]) {
        for (const t of ray) {
            const p = b[t];
            if (p === 0) continue;
            if (p === bishop || p === queen) return true;
            break;
        }
    }
    return false;
}

function findKing(st, color) {
    const code = color === 1 ? 12 : 6;
    const b = st.board;
    for (let sq = 0; sq < 64; sq++) if (b[sq] === code) return sq;
    return -1;
}

function inCheck(st) {
    const k = findKing(st, st.stm);
    if (k < 0) return false;
    return isSquareAttacked(st, k, 1 - st.stm);
}

// ------------------------------------------------------------- make/unmake

// makeMove.msc
function makeMove(st, move) {
    const b = st.board;
    const from = move & 63, to = (move >> 6) & 63, flags = (move >> 15) & 7;
    const moving = b[from];
    const mColor = moving >= 7 ? 1 : 0;
    const mType = moving >= 7 ? moving - 6 : moving;

    let capSq = to, cap = b[to];
    if (flags === 3) {
        const fwd = mColor === 1 ? -8 : 8;
        capSq = to - fwd;
        cap = b[capSq];
        b[capSq] = 0;
    }

    st.undo.push(cap, st.castling, st.ep, st.halfmove, st.running);

    b[from] = 0;
    let placed = moving;
    if ((move >> 12) & 7) placed = mColor === 0 ? 5 : 11;
    b[to] = placed;

    let delta = CONTRIB[placed][to] - CONTRIB[moving][from];
    if (flags === 4) {
        b[to - 1] = b[to + 1]; b[to + 1] = 0;
        const rk = b[to - 1];
        delta += CONTRIB[rk][to - 1] - CONTRIB[rk][to + 1];
    } else if (flags === 5) {
        b[to + 1] = b[to - 2]; b[to - 2] = 0;
        const rk = b[to + 1];
        delta += CONTRIB[rk][to + 1] - CONTRIB[rk][to - 2];
    }
    if (cap !== 0) delta -= CONTRIB[cap][capSq];
    st.running += delta;

    st.halfmove = (mType === 1 || cap !== 0) ? 0 : st.halfmove + 1;
    st.ep = flags === 2 ? (from + to) >> 1 : -1;

    let c = st.castling;
    if (mType === 6) c &= mColor === 0 ? ~3 : ~12;
    if (from === 0 || to === 0) c &= ~2;
    if (from === 7 || to === 7) c &= ~1;
    if (from === 56 || to === 56) c &= ~8;
    if (from === 63 || to === 63) c &= ~4;
    st.castling = c;

    st.stm = 1 - st.stm;
    if (st.stm === 0) st.fullmove++;
}

// unmakeMove.msc
function unmakeMove(st, move) {
    const b = st.board;
    const from = move & 63, to = (move >> 6) & 63, flags = (move >> 15) & 7;

    const u = st.undo;
    st.running = u.pop(); st.halfmove = u.pop(); st.ep = u.pop(); st.castling = u.pop();
    const cap = u.pop();

    let moved = b[to];
    const mColor = moved >= 7 ? 1 : 0;
    if ((move >> 12) & 7) moved = mColor === 1 ? 7 : 1;
    b[from] = moved;

    if (flags === 3) {
        b[to] = 0;
        const fwd = mColor === 1 ? -8 : 8;
        b[to - fwd] = cap;
    } else if (flags === 4) {
        b[to] = 0; b[to + 1] = b[to - 1]; b[to - 1] = 0;
    } else if (flags === 5) {
        b[to] = 0; b[to - 2] = b[to + 1]; b[to + 1] = 0;
    } else {
        b[to] = cap;
    }

    if (st.stm === 0) st.fullmove--;
    st.stm = 1 - st.stm;
}

// ---------------------------------------------------------------- legality

// genLegalMoves.msc — pseudo-legal filtered by "own king not attacked after"
function genLegalMoves(st) {
    const pseudo = genAllPseudoLegal(st);
    const legal = [];
    for (const move of pseudo) {
        const mover = st.stm;
        makeMove(st, move);
        const k = findKing(st, mover);
        const illegal = k >= 0 && isSquareAttacked(st, k, st.stm);
        unmakeMove(st, move);
        if (!illegal) legal.push(move);
    }
    return legal;
}

// ------------------------------------------------------------------ search

// evaluate.msc — O(1) read of the incremental score
function evaluate(st) {
    return st.stm === 1 ? -st.running : st.running;
}

// genOrderedLegalMoves.msc — actually pseudo-legal, sorted best-first.
// Stable: descending score, ties by original index (verified equivalent to
// the MSC prevScore/prevIdx selection loop).
function genOrderedLegalMoves(st) {
    const all = genAllPseudoLegal(st);
    const b = st.board;
    const n = all.length;
    const keyed = new Array(n);
    for (let i = 0; i < n; i++) {
        const move = all[i];
        const from = move & 63, to = (move >> 6) & 63, flags = (move >> 15) & 7;
        const piece = b[from];
        const type = piece >= 7 ? piece - 6 : piece;
        let score;
        if (flags === 1 || flags === 3) {
            let victim = 1;
            if (flags === 1) {
                const vp = b[to];
                victim = vp >= 7 ? vp - 6 : vp;
            }
            score = 10000 + VALUES[victim] * 100 - VALUES[type];
        } else {
            const color = piece >= 7 ? 1 : 0;
            const pstSq = color === 1 ? (7 - (to >> 3)) * 8 + (to & 7) : to;
            score = PSTS[type][pstSq];
        }
        keyed[i] = [score, i, move];
    }
    keyed.sort((a, c) => c[0] - a[0] || a[1] - c[1]);
    return keyed.map(k => k[2]);
}

// qsearch.msc — recapture-only quiescence
function qsearch(st, alpha, beta, recaptureSq, qsDepth) {
    if (qsDepth >= 8) return evaluate(st);

    if (inCheck(st)) {
        const evasions = genLegalMoves(st);
        if (evasions.length === 0) return -100000;
        let best = -200000, ca = alpha;
        for (const move of evasions) {
            makeMove(st, move);
            const score = -qsearch(st, -beta, -ca, (move >> 6) & 63, qsDepth + 1);
            unmakeMove(st, move);
            if (score > best) best = score;
            if (best > ca) ca = best;
            if (ca >= beta) return best;
        }
        return best;
    }

    let best = evaluate(st);
    if (best >= beta) return best;
    let ca = alpha;
    if (best > ca) ca = best;

    if (isSquareAttacked(st, recaptureSq, st.stm)) {
        const all = genAllPseudoLegal(st);
        for (const move of all) {
            if (((move >> 6) & 63) !== recaptureSq || ((move >> 15) & 7) !== 1) continue;
            makeMove(st, move);
            const score = -qsearch(st, -beta, -ca, recaptureSq, qsDepth + 1);
            unmakeMove(st, move);
            if (score > best) best = score;
            if (best > ca) ca = best;
            if (ca >= beta) return best;
        }
    }
    return best;
}

// searchInner.msc — negamax alpha-beta, fail-soft, maxBranches=5
function searchInner(st, depth, alpha, beta) {
    if (depth === 0) return evaluate(st);

    const moves = genOrderedLegalMoves(st);
    if (moves.length === 0) return inCheck(st) ? -100000 : 0;

    let best = -200000, ca = alpha;
    const limit = Math.min(5, moves.length);
    for (let i = 0; i < limit; i++) {
        const move = moves[i];
        makeMove(st, move);
        const score = depth === 1
            ? -qsearch(st, -beta, -ca, (move >> 6) & 63, 0)
            : -searchInner(st, depth - 1, -beta, -ca);
        unmakeMove(st, move);
        if (score > best) best = score;
        if (best > ca) ca = best;
        if (ca >= beta) return best;
    }
    return best;
}

// chooseMove.msc — root: searchDepth=2, maxBranches=20 LEGAL moves searched,
// illegal pseudo-legal moves skipped without counting; strict '>' tie-break.
// Returns 0 if no legal move exists.
function chooseMove(st) {
    const SEARCH_DEPTH = 2;
    const MAX_BRANCHES = 20;

    const moves = genOrderedLegalMoves(st);
    if (moves.length === 0) return 0;

    let bestMove = 0, bestScore = -200000, curAlpha = -200000;
    const beta = 200000;
    let foundLegal = false, searched = 0;
    const myColor = st.stm;

    for (const move of moves) {
        if (searched >= MAX_BRANCHES) break; // MSC: `@if searchedCount < maxBranches` guard per iteration
        makeMove(st, move);
        const k = findKing(st, myColor);
        const legal = k >= 0 && !isSquareAttacked(st, k, st.stm);
        if (legal) {
            const score = -searchInner(st, SEARCH_DEPTH - 1, -beta, -curAlpha);
            if (!foundLegal) {
                foundLegal = true; bestMove = move; bestScore = score;
            } else if (score > bestScore) {
                bestScore = score; bestMove = move;
            }
            if (bestScore > curAlpha) curAlpha = bestScore;
            searched++;
        }
        unmakeMove(st, move);
    }
    if (!foundLegal) return 0;
    return bestMove;
}

// -------------------------------------------------------------- game logic

// checkGameOver.msc semantics
function gameStatus(st) { // side to move about to play
    const legal = genLegalMoves(st);
    if (legal.length === 0) return inCheck(st) ? 'checkmate' : 'stalemate';
    if (st.halfmove >= 100) return '50-move';
    return 'ongoing';
}

// -------------------------------------------------------------------- misc

function posKey(st) {
    // compact key: 64 board bytes + stm/castling/ep — everything chooseMove
    // and move generation depend on (halfmove only affects the 50-move rule)
    let s = '';
    const b = st.board;
    for (let i = 0; i < 64; i += 4)
        s += String.fromCharCode(b[i] | (b[i + 1] << 4) | (b[i + 2] << 8) | (b[i + 3] << 12));
    s += String.fromCharCode(st.stm | (st.castling << 1), st.ep + 1);
    return s;
}

function perft(st, depth) {
    if (depth === 0) return 1;
    const moves = genLegalMoves(st);
    if (depth === 1) return moves.length;
    let n = 0;
    for (const move of moves) {
        makeMove(st, move);
        n += perft(st, depth - 1);
        unmakeMove(st, move);
    }
    return n;
}

function boardAscii(st) {
    const glyphs = '.PNBRQKpnbrqk';
    let s = '';
    for (let r = 7; r >= 0; r--) {
        s += (r + 1) + '  ';
        for (let f = 0; f < 8; f++) s += glyphs[st.board[r * 8 + f]] + ' ';
        s += '\n';
    }
    return s + '   a b c d e f g h';
}

module.exports = {
    startPos, newState, makeMove, unmakeMove, genLegalMoves, genAllPseudoLegal,
    genOrderedLegalMoves, chooseMove, searchInner, qsearch, evaluate, inCheck,
    isSquareAttacked, findKing, gameStatus, perft, posKey,
    moveFrom, moveTo, movePromo, moveFlags, enc, squareName, moveName, boardAscii,
    CONTRIB,
};
