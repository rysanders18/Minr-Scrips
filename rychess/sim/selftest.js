// selftest.js — validation of the engine.js port.
//  1. perft(1)=20, perft(2)=400 (match testPerft.msc expectations; note the
//     in-repo "expected 8902" for depth 3 is the STANDARD-chess value and
//     predates the variant pawn rules — laterals first appear at depth 3,
//     so the variant count must exceed 8902).
//  2. make/unmake round-trip integrity over a random playout.
//  3. runningScore always equals the from-scratch CONTRIB sum.
//  4. Deterministic engine self-play game (white=engine too) printed for
//     eyeballing; also the engine's reply to a few common openings.

'use strict';
const E = require('./engine.js');

let failures = 0;
function check(label, got, want) {
    const ok = got === want;
    if (!ok) failures++;
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}: got ${got}${ok ? '' : `, want ${want}`}`);
}

// ---- 1. perft
{
    const st = E.startPos();
    check('perft(1)', E.perft(st, 1), 20);
    check('perft(2)', E.perft(st, 2), 400);
    const t = Date.now();
    const p3 = E.perft(st, 3);
    console.log(`info  perft(3) = ${p3} (variant; standard chess would be 8902) [${Date.now() - t}ms]`);
    if (p3 <= 8902) { failures++; console.log('FAIL  perft(3) should exceed 8902 with variant pawn rules'); }
}

// ---- 2+3. make/unmake integrity + incremental eval on a random playout
{
    const st = E.startPos();
    const snap = () => JSON.stringify([Array.from(st.board), st.stm, st.castling, st.ep, st.halfmove, st.fullmove, st.running]);
    const recompute = () => { let t = 0; for (let sq = 0; sq < 64; sq++) t += E.CONTRIB[st.board[sq]][sq]; return t; };
    let seed = 12345;
    const rnd = n => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) % n;
    let ok = true;
    for (let ply = 0; ply < 300; ply++) {
        const moves = E.genLegalMoves(st);
        if (moves.length === 0) break;
        const before = snap();
        const mv = moves[rnd(moves.length)];
        E.makeMove(st, mv);
        if (st.running !== recompute()) { ok = false; console.log(`FAIL  runningScore drift at ply ${ply} after ${E.moveName(mv)}`); break; }
        E.unmakeMove(st, mv);
        if (snap() !== before) { ok = false; console.log(`FAIL  make/unmake round-trip at ply ${ply} for ${E.moveName(mv)}`); break; }
        E.makeMove(st, mv); // actually advance
    }
    if (ok) console.log('PASS  make/unmake round-trip + incremental eval over random playout');
    else failures++;
}

// ---- 4. deterministic sample: engine replies to common human openings
{
    for (const opening of ['e2e4', 'd2d4', 'g1f3']) {
        const st = E.startPos();
        const from = (opening.charCodeAt(0) - 97) + (opening[1] - 1) * 8;
        const to = (opening.charCodeAt(2) - 97) + (opening[3] - 1) * 8;
        const mv = E.genLegalMoves(st).find(m => E.moveFrom(m) === from && E.moveTo(m) === to);
        E.makeMove(st, mv);
        const reply = E.chooseMove(st);
        console.log(`info  after 1.${opening} engine plays: ${E.moveName(reply)}`);
    }
}

// ---- engine vs engine full game (both sides deterministic)
{
    const st = E.startPos();
    const line = [];
    for (let ply = 0; ply < 300; ply++) {
        const status = E.gameStatus(st);
        if (status !== 'ongoing') { console.log(`info  self-play ends: ${status} after ${ply} plies`); break; }
        const mv = E.chooseMove(st);
        line.push(E.moveName(mv));
        E.makeMove(st, mv);
        if (ply === 299) console.log('info  self-play hit 300-ply cap');
    }
    console.log('info  self-play game: ' + line.join(' '));
}

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
