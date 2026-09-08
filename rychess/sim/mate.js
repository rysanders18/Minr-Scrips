// mate.js — find the shortest checkmate against the deterministic rychess
// engine. Human plays White (playerColor defaults to 0 in-game; the engine
// is Black and replies via chooseMove, which is fully deterministic).
//
// The game tree branches ONLY at human moves — every engine node has exactly
// one child (chooseMove's pick). Iterative deepening on the number of human
// moves N guarantees the first mate found is the shortest possible.
//
// Pruning that preserves exhaustiveness:
//   - engine replies memoized by position key (board+stm+castling+ep)
//   - fail memo: positions proven mate-free within n human moves are skipped
//     when reached again with <= n budget (transpositions)
//
// Usage: node mate.js [maxDepth] [humanColor]
//   maxDepth   default 4
//   humanColor default 0 (white). 1 = human plays black (engine moves first).

'use strict';
const E = require('./engine.js');

const MAX_DEPTH = parseInt(process.argv[2] || '4', 10);
const HUMAN = parseInt(process.argv[3] || '0', 10);

const replyMemo = new Map(); // posKey -> engine move
const failMemo = new Map();  // posKey -> max n proven to contain no mate
let replies = 0, replyHits = 0, nodes = 0;

function engineReply(st) {
    const key = E.posKey(st);
    let mv = replyMemo.get(key);
    if (mv !== undefined) { replyHits++; return mv; }
    mv = E.chooseMove(st);
    replies++;
    replyMemo.set(key, mv);
    return mv;
}

// Human to move; n >= 1 human moves left in the budget.
// Returns the winning line [humanMv, engineMv, humanMv, ...] or null.
function tryMate(st, n, topLevel) {
    const key = E.posKey(st);
    const seen = failMemo.get(key);
    if (seen !== undefined && seen >= n) return null;

    const moves = E.genLegalMoves(st);
    for (let i = 0; i < moves.length; i++) {
        const mv = moves[i];
        if (topLevel) process.stdout.write(`\r  depth ${n}: root move ${i + 1}/${moves.length} (${E.moveName(mv)})        `);
        nodes++;
        E.makeMove(st, mv);
        let result = null;
        const engineLegal = E.genLegalMoves(st);
        if (engineLegal.length === 0) {
            if (E.inCheck(st)) result = [mv]; // engine checkmated
            // else stalemate: draw, dead end
        } else if (n > 1 && st.halfmove < 100) {
            const reply = engineReply(st); // nonzero: engineLegal is nonempty
            E.makeMove(st, reply);
            const sub = tryMate(st, n - 1, false);
            E.unmakeMove(st, reply);
            if (sub) result = [mv, reply, ...sub];
        }
        E.unmakeMove(st, mv);
        if (result) return result;
    }
    failMemo.set(key, Math.max(seen ?? 0, n));
    return null;
}

function initialState() {
    const st = E.startPos();
    const pre = [];
    if (HUMAN === 1) { // engine (white) moves first
        const mv = engineReply(st);
        E.makeMove(st, mv);
        pre.push(mv);
    }
    return { st, pre };
}

function verifyLine(line, pre) {
    // Replay from scratch, independently re-deriving every engine move.
    const st = E.startPos();
    const all = [...pre, ...line];
    for (let i = 0; i < all.length; i++) {
        const mv = all[i];
        const isEngineTurn = st.stm !== HUMAN;
        if (isEngineTurn) {
            const want = E.chooseMove(st);
            if (want !== mv) return `engine move mismatch at ply ${i}: line has ${E.moveName(mv)}, engine plays ${E.moveName(want)}`;
        } else {
            if (!E.genLegalMoves(st).includes(mv)) return `human move ${E.moveName(mv)} illegal at ply ${i}`;
        }
        E.makeMove(st, mv);
    }
    if (E.gameStatus(st) !== 'checkmate') return `final position is not checkmate (${E.gameStatus(st)})`;
    if (st.stm === HUMAN) return 'checkmated side is the HUMAN, not the engine';
    return null;
}

console.log(`Searching for the shortest mate. Human = ${HUMAN === 0 ? 'White' : 'Black'}, engine = ${HUMAN === 0 ? 'Black' : 'White'}.`);
const t0 = Date.now();
const { st, pre } = initialState();

for (let depth = 1; depth <= MAX_DEPTH; depth++) {
    const t = Date.now();
    const line = tryMate(st, depth, true);
    process.stdout.write('\r' + ' '.repeat(70) + '\r');
    console.log(`depth ${depth}: ${line ? 'MATE FOUND' : 'no mate'} ` +
        `[${((Date.now() - t) / 1000).toFixed(1)}s, ${replies} engine replies (${replyHits} cache hits), ${nodes} human nodes]`);
    if (line) {
        const err = verifyLine(line, pre);
        console.log(err ? `VERIFY FAILED: ${err}` : 'VERIFY OK: independent replay reproduces every engine move; final position is checkmate.');

        // Pretty-print the game.
        const full = [...pre, ...line];
        const replay = E.startPos();
        let out = '', moveNo = 1;
        for (let i = 0; i < full.length; i++) {
            if (replay.stm === 0) out += `${moveNo}. `;
            out += E.moveName(full[i]) + ' ';
            if (replay.stm === 1) moveNo++;
            E.makeMove(replay, full[i]);
        }
        console.log(`\nShortest mate: ${depth} human move(s)`);
        console.log(out.trim() + '#');
        console.log('\nFinal position:');
        console.log(E.boardAscii(replay));
        console.log(`\nTotal time: ${((Date.now() - t0) / 1000).toFixed(1)}s`);
        process.exit(0);
    }
}
console.log(`No mate within ${MAX_DEPTH} human moves. Total time: ${((Date.now() - t0) / 1000).toFixed(1)}s`);
