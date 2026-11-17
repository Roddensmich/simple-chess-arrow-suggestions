import os
from typing import Tuple

def elo_to_sf_params(elo: int) -> Tuple[int, int]:
    elo = max(800, min(3000, elo))
    if elo < 1000: return (1, 5)
    if elo < 1200: return (3, 6)
    if elo < 1400: return (5, 7)
    if elo < 1600: return (8, 9)
    if elo < 1800: return (11, 11)
    if elo < 2000: return (14, 12)
    if elo < 2200: return (16, 14)
    if elo < 2400: return (18, 16)
    if elo < 2600: return (19, 18)
    return (20, 20)

PLAYSTYLES = {
    "magnus": {"softmax_temp": 120, "quick_move_rate": 0.08, "long_think_rate": 0.10, "think_mu_scale": 1.0, "mistake_rate": 0.03, "candidate_weights": [0.78, 0.16, 0.06]},
    "hikaru": {"softmax_temp": 90, "quick_move_rate": 0.20, "long_think_rate": 0.04, "think_mu_scale": 0.55, "mistake_rate": 0.05, "candidate_weights": [0.72, 0.20, 0.08]},
    "gotham": {"softmax_temp": 200, "quick_move_rate": 0.06, "long_think_rate": 0.08, "think_mu_scale": 1.2, "mistake_rate": 0.12, "candidate_weights": [0.60, 0.28, 0.12]},
}

JS_DRAW_ARROWS = """
(function() {
    const arrows = %s;
    const board = document.querySelector('wc-chess-board') || document.querySelector('chess-board') || document.querySelector('.board');
    if (!board || !arrows.length) return false;

    const NS = 'http://www.w3.org/2000/svg';
    const layerId = 'ks_arrows';

    let svg = document.getElementById(layerId);
    if (!svg) {
        svg = document.createElementNS(NS, 'svg');
        svg.id = layerId;
        Object.assign(svg.style, { position: 'fixed', pointerEvents: 'none', overflow: 'visible', zIndex: '2147483647' });
        document.body.appendChild(svg);
    }

    const rect = board.getBoundingClientRect();
    svg.style.left = rect.left + 'px'; 
    svg.style.top = rect.top + 'px';
    svg.style.width = rect.width + 'px'; 
    svg.style.height = rect.height + 'px';
    svg.setAttribute('width', rect.width); 
    svg.setAttribute('height', rect.height);
    svg.setAttribute('viewBox', `0 0 ${rect.width} ${rect.height}`);

    while (svg.firstChild) svg.removeChild(svg.firstChild);

    const size = rect.width / 8;
    const flip = board.classList.contains('flipped');
    const colMap = {a:0,b:1,c:2,d:3,e:4,f:5,g:6,h:7};

    function sqCenter(sq) {
        const fi = colMap[sq[0]], ri = parseInt(sq[1]) - 1;
        return [ (flip ? (7-fi) : fi) * size + size / 2, (flip ? ri : (7-ri)) * size + size / 2 ];
    }

    arrows.forEach(a => {
        const [x1, y1] = sqCenter(a.from); 
        const [x2, y2] = sqCenter(a.to);
        
        const dx = x2 - x1;
        const dy = y2 - y1;
        const len = Math.sqrt(dx * dx + dy * dy);
        if (len === 0) return;

        const strokeW = size * 0.12;
        const stopX = x2 - (dx / len) * (size * 0.15);
        const stopY = y2 - (dy / len) * (size * 0.15);

        const line = document.createElementNS(NS, 'line');
        line.setAttribute('x1', x1); line.setAttribute('y1', y1);
        line.setAttribute('x2', stopX); line.setAttribute('y2', stopY);
        line.setAttribute('stroke', a.color); 
        line.setAttribute('stroke-width', strokeW);
        line.setAttribute('stroke-linecap', 'round'); 
        line.setAttribute('opacity', a.alpha || 0.85);
        
        const angle = Math.atan2(dy, dx);
        const hSize = size * 0.3;
        const p1 = `${x2 - hSize * Math.cos(angle - Math.PI / 7)},${y2 - hSize * Math.sin(angle - Math.PI / 7)}`;
        const p2 = `${x2 - hSize * Math.cos(angle + Math.PI / 7)},${y2 - hSize * Math.sin(angle + Math.PI / 7)}`;
        
        const poly = document.createElementNS(NS, 'polygon');
        poly.setAttribute('points', `${x2},${y2} ${p1} ${p2}`);
        poly.setAttribute('fill', a.color); 
        poly.setAttribute('opacity', a.alpha || 0.85);
        
        svg.appendChild(line); 
        svg.appendChild(poly);
    });
    return true;
})()
"""

JS_CLEAR_ARROWS = """
(function() {
    const svg = document.getElementById('ks_arrows');
    if (svg) svg.remove();
})()
"""

JS_IS_GAME_OVER = "!!document.querySelector('.game-over-modal-header-inner')"

JS_GET_STATE = """
(function() {
    const board = document.querySelector('wc-chess-board') || document.querySelector('chess-board') || document.querySelector('.board');
    if (!board) return null;
    
    if (!!board.querySelector('.piece.dragging') || !!document.querySelector('.piece.dragging')) return { dragging: true };

    const myNameEl = document.querySelector('a[data-user-activity-key="profile"]');
    let myName = null;
    if (myNameEl) {
        const match = myNameEl.href ? myNameEl.href.match(/member\\/([^/]+)/) : null; // FIX BUG 5
        if (match) myName = match[1].toLowerCase();
    }

    let oppName = null;
    let oppRatingDOM = null;
    const nameEls = Array.from(document.querySelectorAll('.cc-user-username-component, .user-tagline-username, .player-username'));
    
    for (let el of nameEls) {
        const name = el.textContent.trim();
        if (name && (!myName || name.toLowerCase() !== myName)) {
            if (name.toLowerCase() === 'opponent' || name.toLowerCase() === 'waiting') continue;
            
            oppName = name;
            const parent = el.closest('.user-tagline, .player-component, .board-layout-top, .board-layout-bottom, div[class*="player"]');
            if (parent) {
                const ratingEl = parent.querySelector('[data-test-element="user-tagline-rating"], .user-tagline-rating, .cc-user-rating-boldest');
                if (ratingEl) {
                    const parsed = parseInt(ratingEl.textContent.replace(/[^0-9]/g, ''));
                    if (parsed >= 100 && parsed <= 4000) oppRatingDOM = parsed;
                } else {
                    const match = parent.textContent.match(/\\((\\d{3,4})\\)/);
                    if (match) oppRatingDOM = parseInt(match[1]);
                }
            }
            break;
        }
    }

    const topContainer = document.querySelector('.board-layout-top') || document.querySelector('.player-top');
    const bottomContainer = document.querySelector('.board-layout-bottom') || document.querySelector('.player-bottom');
    const flip = board.classList.contains('flipped');
    let myColor = flip ? 'b' : 'w'; 
    
    let active = null;
    const activeClock = document.querySelector('.clock-player-turn');
    if (activeClock) {
        if (topContainer && topContainer.contains(activeClock)) active = flip ? 'w' : 'b';
        else if (bottomContainer && bottomContainer.contains(activeClock)) active = flip ? 'b' : 'w';
    }
    
    if (!active) {
        let side = 'w';
        for (const hl of document.querySelectorAll('.highlight')) {
            const hc = [...hl.classList].find(c => c.startsWith('square-'));
            if (!hc) continue;
            const piece = document.querySelector('.piece.' + hc);
            if (!piece) continue;
            const pc = [...piece.classList];
            if (pc.some(c => c.startsWith('w'))) { side = 'b'; break; }
            if (pc.some(c => c.startsWith('b'))) { side = 'w'; break; }
        }
        active = side;
    }

    let myClock = null, oppClock = null, gameActive = false;
    try {
        const clockEls = document.querySelectorAll('.clock-time-monospace, .clock-component');
        if (clockEls.length >= 2) {
            gameActive = true;
            const parse = txt => {                                                             // FIX BUG 4
                const parts = txt.trim().split(':');
                if (parts.length === 2) return parseInt(parts[0]) * 60 + parseInt(parts[1]);
                if (parts.length === 3) return parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(parts[2]);
                return null;
            };
            const myIdx = (myColor === 'w') ? (flip ? 0 : 1) : (flip ? 1 : 0);
            myClock = parse(clockEls[myIdx].textContent);
            oppClock = parse(clockEls[1 - myIdx].textContent);
        }
    } catch(e) {}

    const pieceMap = { wp:'P',wn:'N',wb:'B',wr:'R',wq:'Q',wk:'K', bp:'p',bn:'n',bb:'b',br:'r',bq:'q',bk:'k' };
    const grid = Array.from({length:8}, () => Array(8).fill(null));
    document.querySelectorAll('.piece').forEach(p => {
        const cls = [...p.classList];
        const type = cls.find(c => pieceMap[c]);
        const sq = cls.find(c => c.startsWith('square-'));
        if (type && sq) { const [col, row] = sq.split('-')[1].split('').map(Number); grid[8-row][col-1] = pieceMap[type]; }
    });
    const fenRows = grid.map(r => {
        let s = '', e = 0;
        r.forEach(cell => cell ? (e && (s += e, e = 0), s += cell) : e++);
        return e ? s + e : s;
    });

    return { 
        fen: fenRows.join('/') + ' ' + active + ' - - 0 1', 
        myColor: myColor, 
        active: active, 
        myClock: myClock, 
        oppClock: oppClock, 
        gameActive: gameActive,
        myUsername: myName,
        oppUsername: oppName,
        oppRatingDOM: oppRatingDOM
    };
})()
"""

BROWSERS = {
    "brave": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.join(os.path.expandvars("%LOCALAPPDATA%"), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    ],
}

JS_MASK_WEBDRIVER = """
(function() {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    if (!window.chrome) window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
})();
"""