// opponents_factory.js — same reference opponents as opponents.js, but bound
// to an arbitrary engine module (variant engine.js or engine_standard.js).

'use strict';

module.exports = function makeOpponents(E) {
    const VALUES = [0, 100, 320, 330, 500, 900, 20000];

    function orderedLegal(st) {
        const moves = E.genLegalMoves(st);
        const b = st.board;
        const keyed = moves.map((m, i) => {
            const flags = (m >> 15) & 7;
            let s = 0;
            if (flags === 1 || flags === 3) {
                const vp = flags === 1 ? b[(m >> 6) & 63] : 0;
                const victim = flags === 1 ? (vp >= 7 ? vp - 6 : vp) : 1;
                const ap = b[m & 63];
                s = 10000 + VALUES[victim] * 100 - VALUES[ap >= 7 ? ap - 6 : ap];
            }
            return [s, i, m];
        });
        keyed.sort((a, c) => c[0] - a[0] || a[1] - c[1]);
        return keyed.map(k => k[2]);
    }

    function qsearchFull(st, alpha, beta) {
        let best = E.evaluate(st);
        if (best >= beta) return best;
        let ca = alpha > best ? alpha : best;
        const caps = orderedLegal(st).filter(m => { const f = (m >> 15) & 7; return f === 1 || f === 3; });
        for (const m of caps) {
            E.makeMove(st, m);
            const score = -qsearchFull(st, -beta, -ca);
            E.unmakeMove(st, m);
            if (score > best) best = score;
            if (best > ca) ca = best;
            if (ca >= beta) return best;
        }
        return best;
    }

    function absearch(st, depth, alpha, beta, ply) {
        if (depth === 0) return qsearchFull(st, alpha, beta);
        const moves = orderedLegal(st);
        if (moves.length === 0) return E.inCheck(st) ? -(100000 - ply) : 0;
        let best = -Infinity, ca = alpha;
        for (const m of moves) {
            E.makeMove(st, m);
            const score = -absearch(st, depth - 1, -beta, -ca, ply + 1);
            E.unmakeMove(st, m);
            if (score > best) best = score;
            if (best > ca) ca = best;
            if (ca >= beta) return best;
        }
        return best;
    }

    function fullWidthAI(depth) {
        return st => {
            const moves = orderedLegal(st);
            let bestMove = 0, best = -Infinity;
            for (const m of moves) {
                E.makeMove(st, m);
                const score = -absearch(st, depth - 1, -Infinity, -best, 1);
                E.unmakeMove(st, m);
                if (score > best) { best = score; bestMove = m; }
            }
            return bestMove;
        };
    }

    function greedyAI() {
        return st => {
            const moves = orderedLegal(st);
            let bestMove = 0, best = -Infinity;
            for (const m of moves) {
                E.makeMove(st, m);
                const score = -E.evaluate(st);
                E.unmakeMove(st, m);
                if (score > best) { best = score; bestMove = m; }
            }
            return bestMove;
        };
    }

    function randomAI(rng) {
        return st => {
            const moves = E.genLegalMoves(st);
            return moves[rng(moves.length)];
        };
    }

    function makeRng(seed) {
        let s = seed >>> 0;
        return n => {
            s = (s * 1664525 + 1013904223) >>> 0;
            return s % n;
        };
    }

    return { orderedLegal, fullWidthAI, greedyAI, randomAI, makeRng };
};
