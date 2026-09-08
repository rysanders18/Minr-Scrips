// tourney.js — gauntlet: rychess engine vs the reference ladder, variant rules.
//
// Methodology (standard engine-testing practice):
//   - K random balanced openings (4 random plies, |eval| <= 200cp, game ongoing)
//   - each opening played TWICE with colors swapped (bias cancels)
//   - both players deterministic -> variance comes from openings only
//   - adjudication: checkmate / stalemate / 50-move / threefold / 400-ply cap
//   - Elo diff from score: d = 400*log10(s/(1-s)), with 95% CI via normal approx
//
// Usage: node tourney.js [openingsPerPair]

'use strict';
const E = require('./engine.js');
const O = require('./opponents.js');

const K = parseInt(process.argv[2] || '50', 10);

const rychessAI = st => E.chooseMove(st);

function genOpenings(count, seed) {
    const rng = O.makeRng(seed);
    const openings = [];
    let guard = 0;
    while (openings.length < count && guard++ < 10000) {
        const st = E.startPos();
        const line = [];
        let ok = true;
        for (let i = 0; i < 4; i++) {
            const moves = E.genLegalMoves(st);
            if (moves.length === 0) { ok = false; break; }
            const mv = moves[rng(moves.length)];
            line.push(mv);
            E.makeMove(st, mv);
        }
        if (!ok) continue;
        if (E.gameStatus(st) !== 'ongoing') continue;
        if (Math.abs(st.running) > 200) continue; // keep openings roughly balanced
        openings.push(line);
    }
    return openings;
}

function playGame(whiteAI, blackAI, opening) {
    const st = E.startPos();
    const seen = new Map();
    for (const mv of opening) E.makeMove(st, mv);
    for (let ply = 0; ply < 400; ply++) {
        const status = E.gameStatus(st);
        if (status === 'checkmate') return st.stm === 0 ? 0 : 1; // side to move is mated; 1 = white wins
        if (status !== 'ongoing') return 0.5;
        const k = E.posKey(st);
        const c = (seen.get(k) || 0) + 1;
        seen.set(k, c);
        if (c >= 3) return 0.5;
        const ai = st.stm === 0 ? whiteAI : blackAI;
        const mv = ai(st);
        E.makeMove(st, mv);
    }
    return 0.5;
}

function eloDiff(score) {
    const s = Math.min(Math.max(score, 0.001), 0.999);
    return 400 * Math.log10(s / (1 - s));
}

function match(name, opponentAI, openings) {
    let pts = 0, w = 0, d = 0, l = 0;
    const t = Date.now();
    for (const opening of openings) {
        for (const rychessIsWhite of [true, false]) {
            const white = rychessIsWhite ? rychessAI : opponentAI;
            const black = rychessIsWhite ? opponentAI : rychessAI;
            const r = playGame(white, black, opening);
            const s = rychessIsWhite ? r : 1 - r;
            pts += s;
            if (s === 1) w++; else if (s === 0.5) d++; else l++;
        }
    }
    const n = openings.length * 2;
    const score = pts / n;
    // std error of the mean score (treating games as independent)
    const varGame = (w * (1 - score) ** 2 + d * (0.5 - score) ** 2 + l * (0 - score) ** 2) / n;
    const se = Math.sqrt(varGame / n);
    const lo = eloDiff(score - 1.96 * se), hi = eloDiff(score + 1.96 * se);
    console.log(`rychess vs ${name.padEnd(8)} : ${w}W ${d}D ${l}L  score ${(100 * score).toFixed(1)}%  ` +
        `Elo ${eloDiff(score) >= 0 ? '+' : ''}${eloDiff(score).toFixed(0)} [${lo.toFixed(0)}, ${hi.toFixed(0)}]  ` +
        `(${((Date.now() - t) / 1000).toFixed(0)}s)`);
    return { name, score, elo: eloDiff(score) };
}

const openings = genOpenings(K, 987654321);
console.log(`${openings.length} paired openings -> ${openings.length * 2} games per pairing\n`);

const rngRandom = O.makeRng(42);
match('random', O.randomAI(rngRandom), openings);
match('greedy', O.greedyAI(), openings);
match('fw2', O.fullWidthAI(2), openings);
match('fw3', O.fullWidthAI(3), openings);

// fw4 is slow; time-box with fewer openings
const few = openings.slice(0, Math.min(15, openings.length));
console.log(`\nfw4 uses ${few.length} openings (${few.length * 2} games):`);
match('fw4', O.fullWidthAI(4), few);

// ladder consistency cross-checks
console.log('\nLadder cross-checks:');
{
    const save = rychessAI; // not used; direct pair matches below
    function pair(nameA, aiA, nameB, aiB, ops) {
        let pts = 0;
        for (const opening of ops) {
            for (const aIsWhite of [true, false]) {
                const r = playGame(aIsWhite ? aiA : aiB, aIsWhite ? aiB : aiA, opening);
                pts += aIsWhite ? r : 1 - r;
            }
        }
        const s = pts / (ops.length * 2);
        console.log(`${nameA} vs ${nameB}: ${(100 * s).toFixed(1)}%  (Elo ${eloDiff(s).toFixed(0)})`);
    }
    pair('greedy', O.greedyAI(), 'random', O.randomAI(O.makeRng(7)), openings);
    pair('fw2', O.fullWidthAI(2), 'greedy', O.greedyAI(), openings);
    pair('fw3', O.fullWidthAI(3), 'fw2', O.fullWidthAI(2), openings.slice(0, 25));
}
