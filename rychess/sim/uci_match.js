// uci_match.js — standard-chess calibration match vs Stockfish.
//
// Plays engine_standard.js opponents against Stockfish with UCI_LimitStrength
// at a given UCI_Elo, using paired random openings (colors swapped). Reports
// score and the implied Elo of our side (SF_Elo + 400*log10(s/(1-s))).
//
// Usage: node uci_match.js [sfElo] [openings] [side]
//   side: 'rychess' (default) | 'fw2' | 'fw3'   — who plays vs Stockfish
//
// Stockfish's UCI_Elo model is itself an approximation, so treat the output
// as an anchor with ~±100 Elo of systematic uncertainty.

'use strict';
const { spawn } = require('child_process');
const path = require('path');
const E = require('./engine_standard.js');
const O = require('./opponents_factory.js')(E);

const SF_PATH = 'C:\\Users\\ryanp\\AppData\\Local\\Temp\\claude\\C--Users-ryanp-code-Minr-Scrips-rychess\\db2a8560-6f86-4e8e-85d7-194750a51568\\scratchpad\\stockfish\\stockfish\\stockfish-windows-x86-64-avx2.exe';
const SF_ELO = parseInt(process.argv[2] || '1320', 10);
const N_OPENINGS = parseInt(process.argv[3] || '25', 10);
const SIDE = process.argv[4] || 'rychess';
const MOVETIME = 60;

const ourAI = SIDE === 'rychess' ? (st => E.chooseMove(st))
    : SIDE === 'fw2' ? O.fullWidthAI(2)
        : SIDE === 'fw3' ? O.fullWidthAI(3)
            : null;
if (!ourAI) { console.error('unknown side ' + SIDE); process.exit(1); }

// ------------------------------------------------------------ SF process

const sf = spawn(SF_PATH);
let buffer = '';
let waiter = null; // {predicate, resolve}
sf.stdout.on('data', d => {
    buffer += d.toString();
    let idx;
    while ((idx = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (waiter && waiter.predicate(line)) {
            const w = waiter; waiter = null;
            w.resolve(line);
        }
    }
});
sf.on('error', e => { console.error('stockfish spawn error', e); process.exit(1); });

const send = cmd => sf.stdin.write(cmd + '\n');
const waitFor = predicate => new Promise(resolve => { waiter = { predicate, resolve }; });

// ---------------------------------------------------------------- helpers

const uciOf = m => {
    let s = E.squareName(E.moveFrom(m)) + E.squareName(E.moveTo(m));
    if (E.movePromo(m)) s += 'qnbr'[[4, 1, 2, 3].indexOf(E.movePromo(m))];
    return s;
};

function moveFromUci(st, uci) {
    const from = (uci.charCodeAt(0) - 97) + (uci.charCodeAt(1) - 49) * 8;
    const to = (uci.charCodeAt(2) - 97) + (uci.charCodeAt(3) - 49) * 8;
    const legal = E.genLegalMoves(st);
    let match = legal.find(m => E.moveFrom(m) === from && E.moveTo(m) === to);
    if (match === undefined) return null;
    if (uci.length > 4) {
        // honor SF underpromotions so boards stay in sync (our gen emits q only)
        const promo = { q: 4, n: 1, b: 2, r: 3 }[uci[4]];
        match = (match & ~(7 << 12)) | (promo << 12);
    }
    return match;
}

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
        if (Math.abs(st.running) > 150) continue;
        openings.push(line);
    }
    return openings;
}

// ------------------------------------------------------------- game loop

async function playGame(opening, weAreWhite) {
    send('ucinewgame');
    send('isready');
    await waitFor(l => l === 'readyok');

    const st = E.startPos();
    const uciMoves = [];
    const seen = new Map();
    for (const mv of opening) { E.makeMove(st, mv); uciMoves.push(uciOf(mv)); }

    for (let ply = 0; ply < 400; ply++) {
        const status = E.gameStatus(st);
        if (status === 'checkmate') return st.stm === 0 ? 0 : 1; // 1 = white wins
        if (status !== 'ongoing') return 0.5;
        const k = E.posKey(st);
        const c = (seen.get(k) || 0) + 1;
        seen.set(k, c);
        if (c >= 3) return 0.5;

        const ourTurn = (st.stm === 0) === weAreWhite;
        let mv;
        if (ourTurn) {
            mv = ourAI(st);
        } else {
            send('position startpos moves ' + uciMoves.join(' '));
            send(`go movetime ${MOVETIME}`);
            const line = await waitFor(l => l.startsWith('bestmove'));
            const uci = line.split(/\s+/)[1];
            mv = moveFromUci(st, uci);
            if (mv === null) { console.error(`SF move ${uci} not legal in our state — desync!`); process.exit(1); }
        }
        uciMoves.push(uciOf(mv));
        E.makeMove(st, mv);
    }
    return 0.5;
}

function eloDiff(score) {
    const s = Math.min(Math.max(score, 0.001), 0.999);
    return 400 * Math.log10(s / (1 - s));
}

(async () => {
    send('uci');
    await waitFor(l => l === 'uciok');
    send('setoption name Threads value 1');
    send('setoption name Hash value 16');
    send('setoption name UCI_LimitStrength value true');
    send(`setoption name UCI_Elo value ${SF_ELO}`);
    send('isready');
    await waitFor(l => l === 'readyok');

    const openings = genOpenings(N_OPENINGS, 246813579);
    console.log(`${SIDE} vs Stockfish 17.1 (UCI_Elo ${SF_ELO}, movetime ${MOVETIME}ms): ${openings.length * 2} games`);

    let pts = 0, w = 0, d = 0, l = 0, n = 0;
    const t0 = Date.now();
    for (const opening of openings) {
        for (const weAreWhite of [true, false]) {
            const r = await playGame(opening, weAreWhite);
            const s = weAreWhite ? r : 1 - r;
            pts += s; n++;
            if (s === 1) w++; else if (s === 0.5) d++; else l++;
            process.stdout.write(`\r  ${n} games: ${w}W ${d}D ${l}L (${((Date.now() - t0) / 1000).toFixed(0)}s)   `);
        }
    }
    const score = pts / n;
    const varGame = (w * (1 - score) ** 2 + d * (0.5 - score) ** 2 + l * (0 - score) ** 2) / n;
    const se = Math.sqrt(varGame / n);
    console.log(`\nscore ${(100 * score).toFixed(1)}%  -> ${SIDE} Elo ~= ${(SF_ELO + eloDiff(score)).toFixed(0)}` +
        ` [${(SF_ELO + eloDiff(Math.max(score - 1.96 * se, 0))).toFixed(0)}, ${(SF_ELO + eloDiff(Math.min(score + 1.96 * se, 1))).toFixed(0)}]` +
        ` (diff ${eloDiff(score).toFixed(0)})`);
    send('quit');
    process.exit(0);
})();
