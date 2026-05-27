import os
from typing import Tuple

def elo_to_sf_params(elo: int) -> Tuple[int, int]:
    elo = max(800, min(3000, elo))
    if elo < 1000:
        return (1, 5)
    if elo < 1200:
        return (3, 6)
    if elo < 1400:
        return (5, 7)
    if elo < 1600:
        return (8, 9)
    if elo < 1800:
        return (11, 11)
    if elo < 2000:
        return (14, 12)
    if elo < 2200:
        return (16, 14)
    if elo < 2400:
        return (18, 16)
    if elo < 2600:
        return (19, 18)
    return (20, 20)

PLAYSTYLES = {
    "magnus": {
        "desc": "Universal genius — positional, precise endgames",
        "softmax_temp": 120,
        "quick_move_rate": 0.08,
        "long_think_rate": 0.10,
        "think_mu_scale": 1.0,
        "mistake_rate": 0.03,
        "prefer_tactical": False,
        "opening_speed": 0.7,
        "time_pressure_scale": 1.4,
        "candidate_weights": [0.78, 0.16, 0.06],
    },
    "hikaru": {
        "desc": "Blitz king — fast, tactical, sharp",
        "softmax_temp": 90,
        "quick_move_rate": 0.20,
        "long_think_rate": 0.04,
        "think_mu_scale": 0.55,
        "mistake_rate": 0.05,
        "prefer_tactical": True,
        "opening_speed": 0.95,
        "time_pressure_scale": 1.8,
        "candidate_weights": [0.72, 0.20, 0.08],
    },
    "bobby": {
        "desc": "Aggressive — open games, forcing sequences",
        "softmax_temp": 100,
        "quick_move_rate": 0.10,
        "long_think_rate": 0.12,
        "think_mu_scale": 1.1,
        "mistake_rate": 0.04,
        "prefer_tactical": True,
        "opening_speed": 0.8,
        "time_pressure_scale": 1.3,
        "candidate_weights": [0.80, 0.14, 0.06],
    },
    "tal": {
        "desc": "Deep positional — slow build-up, rarely blunders",
        "softmax_temp": 80,
        "quick_move_rate": 0.03,
        "long_think_rate": 0.20,
        "think_mu_scale": 1.6,
        "mistake_rate": 0.01,
        "prefer_tactical": False,
        "opening_speed": 0.5,
        "time_pressure_scale": 1.1,
        "candidate_weights": [0.88, 0.10, 0.02],
    },
    "gotham": {
        "desc": "Club player — instructive, occasional inaccuracies",
        "softmax_temp": 200,
        "quick_move_rate": 0.06,
        "long_think_rate": 0.08,
        "think_mu_scale": 1.2,
        "mistake_rate": 0.12,
        "prefer_tactical": False,
        "opening_speed": 0.6,
        "time_pressure_scale": 1.5,
        "candidate_weights": [0.60, 0.28, 0.12],
    },
    "hitler": {
        "desc": "NEIN NEIN NEIN NEIN! MEIN REICH",
        "softmax_temp": 55,
        "quick_move_rate": 0.35,
        "long_think_rate": 0.03,
        "think_mu_scale": 0.38,
        "mistake_rate": 0.18,
        "prefer_tactical": True,
        "opening_speed": 1.0,
        "time_pressure_scale": 2.2,
        "candidate_weights": [0.42, 0.32, 0.18, 0.08],
        "sac_bias": 2.8,
        "force_tactical": True,
    },
    "hirohito": {
        "desc": "BANZAII",
        "softmax_temp": 30,
        "quick_move_rate": 0.35,
        "long_think_rate": 0.03,
        "think_mu_scale": 0.38,
        "mistake_rate": 0.18,
        "prefer_tactical": True,
        "opening_speed": 1.0,
        "time_pressure_scale": 2.2,
        "candidate_weights": [0.42, 0.32, 0.18, 0.08],
        "sac_bias": 4.2,
        "force_tactical": True,
    },
    "von": {
        "desc": "Aggressive street style",
        "softmax_temp": 75,
        "quick_move_rate": 0.22,
        "long_think_rate": 0.05,
        "think_mu_scale": 0.55,
        "mistake_rate": 0.09,
        "prefer_tactical": True,
        "opening_speed": 0.92,
        "time_pressure_scale": 1.9,
        "candidate_weights": [0.52, 0.28, 0.14, 0.06],
        "sac_bias": 1.6,
        "force_tactical": False,
    },
}

JS_DRAW_ARROWS = """
(function() {
    const arrows = %s;
    const board = document.querySelector('wc-chess-board') ||
                  document.querySelector('chess-board') ||
                  document.querySelector('.board');
    if (!board || !arrows.length) return false;

    window.__ksArrows = arrows;

    const NS = 'http://www.w3.org/2000/svg';

    function getBoard() {
        return document.querySelector('wc-chess-board') ||
               document.querySelector('chess-board') ||
               document.querySelector('.board');
    }

    function ensureSvg(rect) {
        let svg = document.getElementById('ks-suggestion-layer');

        if (!svg) {
            svg = document.createElementNS(NS, 'svg');
            svg.id = 'ks-suggestion-layer';
            Object.assign(svg.style, {
                position: 'fixed',
                pointerEvents: 'none',
                overflow: 'visible',
                zIndex: '2147483647'
            });
        }

        svg.style.display = '';
        svg.style.left = rect.left + 'px';
        svg.style.top = rect.top + 'px';
        svg.style.width = rect.width + 'px';
        svg.style.height = rect.height + 'px';
        svg.setAttribute('width', rect.width);
        svg.setAttribute('height', rect.height);

        if (svg.parentNode !== document.body) {
            document.body.appendChild(svg);
        }

        return svg;
    }

    function clearSvg(svg) {
        while (svg.firstChild) svg.removeChild(svg.firstChild);
    }

    function draw(arrowList) {
        const board = getBoard();
        if (!board) return;

        const rect = board.getBoundingClientRect();
        if (!rect.width || !rect.height) return;

        const W = rect.width;
        const H = rect.height;
        const size = W / 8;
        const flip = board.classList.contains('flipped');
        const colMap = {a:0,b:1,c:2,d:3,e:4,f:5,g:6,h:7};

        function sqCenter(sq) {
            const fi = colMap[sq[0]], ri = parseInt(sq[1]) - 1;
            return [
                (flip ? (7-fi) : fi) * size + size / 2,
                (flip ? ri : (7-ri)) * size + size / 2
            ];
        }

        function sqOrigin(sq) {
            const fi = colMap[sq[0]], ri = parseInt(sq[1]) - 1;
            return [
                (flip ? (7-fi) : fi) * size,
                (flip ? ri : (7-ri)) * size
            ];
        }

        const svg = ensureSvg(rect);
        clearSvg(svg);

        const defs = document.createElementNS(NS, 'defs');

        const filt = document.createElementNS(NS, 'filter');
        filt.id = 'ks-glow';
        filt.setAttribute('x', '-40%%');
        filt.setAttribute('y', '-40%%');
        filt.setAttribute('width', '180%%');
        filt.setAttribute('height', '180%%');

        const blur = document.createElementNS(NS, 'feGaussianBlur');
        blur.setAttribute('in', 'SourceGraphic');
        blur.setAttribute('stdDeviation', '3');
        blur.setAttribute('result', 'blurred');

        const merge = document.createElementNS(NS, 'feMerge');
        ['blurred', 'SourceGraphic'].forEach(n => {
            const mn = document.createElementNS(NS, 'feMergeNode');
            mn.setAttribute('in', n);
            merge.appendChild(mn);
        });

        filt.appendChild(blur);
        filt.appendChild(merge);
        defs.appendChild(filt);

        [...new Set(arrowList.map(a => a.color))].forEach(c => {
            const mid = c.replace('#', '');
            const m = document.createElementNS(NS, 'marker');
            m.id = 'ks-ah-' + mid;
            m.setAttribute('markerUnits', 'strokeWidth');
            m.setAttribute('markerWidth', '2.4');
            m.setAttribute('markerHeight', '2.4');
            m.setAttribute('refX', '0.1');
            m.setAttribute('refY', '1.2');
            m.setAttribute('orient', 'auto');
            const poly = document.createElementNS(NS, 'polygon');
            poly.setAttribute('points', '0 0, 2.4 1.2, 0 2.4');
            poly.setAttribute('fill', c);
            m.appendChild(poly);
            defs.appendChild(m);
        });

        svg.appendChild(defs);

        arrowList.forEach(a => {
            const alpha = a.alpha !== undefined ? a.alpha : 0.85;
            const mid = a.color.replace('#', '');
            const [x1, y1] = sqCenter(a.from);
            const [x2, y2] = sqCenter(a.to);
            const dx = x2 - x1, dy = y2 - y1, len = Math.sqrt(dx * dx + dy * dy);
            if (!len) return;

            const sw = size * 0.155;
            const shrink = sw * 2.6;

            const [ox, oy] = sqOrigin(a.to);
            const hi = document.createElementNS(NS, 'rect');
            hi.setAttribute('x', ox);
            hi.setAttribute('y', oy);
            hi.setAttribute('width', size);
            hi.setAttribute('height', size);
            hi.setAttribute('fill', a.color);
            hi.setAttribute('opacity', (alpha * 0.28).toFixed(2));
            hi.setAttribute('rx', '3');
            svg.appendChild(hi);

            const glow = document.createElementNS(NS, 'line');
            glow.setAttribute('x1', x1);
            glow.setAttribute('y1', y1);
            glow.setAttribute('x2', x2 - (dx / len) * shrink);
            glow.setAttribute('y2', y2 - (dy / len) * shrink);
            glow.setAttribute('stroke', a.color);
            glow.setAttribute('stroke-width', sw * 2.6);
            glow.setAttribute('stroke-linecap', 'round');
            glow.setAttribute('opacity', (alpha * 0.22).toFixed(2));
            glow.setAttribute('filter', 'url(#ks-glow)');
            svg.appendChild(glow);

            const line = document.createElementNS(NS, 'line');
            line.setAttribute('x1', x1);
            line.setAttribute('y1', y1);
            line.setAttribute('x2', x2 - (dx / len) * shrink);
            line.setAttribute('y2', y2 - (dy / len) * shrink);
            line.setAttribute('stroke', a.color);
            line.setAttribute('stroke-width', sw);
            line.setAttribute('stroke-linecap', 'round');
            line.setAttribute('opacity', alpha.toFixed(2));
            line.setAttribute('marker-end', 'url(#ks-ah-' + mid + ')');
            svg.appendChild(line);

            const dot = document.createElementNS(NS, 'circle');
            dot.setAttribute('cx', x1);
            dot.setAttribute('cy', y1);
            dot.setAttribute('r', sw * 0.72);
            dot.setAttribute('fill', a.color);
            dot.setAttribute('opacity', (alpha * 0.70).toFixed(2));
            svg.appendChild(dot);
        });
    }

    draw(arrows);

    if (window.__ksObserver) {
        window.__ksObserver.disconnect();
        window.__ksObserver = null;
    }

    window.__ksObserver = new MutationObserver(() => {
        if (!window.__ksArrows) return;
        if (window.__ksDebounce) clearTimeout(window.__ksDebounce);
        window.__ksDebounce = setTimeout(() => {
            if (!window.__ksArrows) return;
            draw(window.__ksArrows);
        }, 10);
    });

    window.__ksObserver.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['class', 'style']
    });

    if (window.__ksInterval) clearInterval(window.__ksInterval);
    window.__ksInterval = setInterval(() => {
        if (!window.__ksArrows) return;
        draw(window.__ksArrows);
    }, 120);

    if (window.__ksResizeHandler) {
        window.removeEventListener('resize', window.__ksResizeHandler);
    }
    window.__ksResizeHandler = () => {
        if (window.__ksArrows) draw(window.__ksArrows);
    };
    window.addEventListener('resize', window.__ksResizeHandler);

    return true;
})()
"""

JS_CLEAR_ARROWS = """
(function() {
    if (window.__ksObserver) { window.__ksObserver.disconnect(); window.__ksObserver = null; }
    if (window.__ksInterval) { clearInterval(window.__ksInterval); window.__ksInterval = null; }
    if (window.__ksDebounce) { clearTimeout(window.__ksDebounce); window.__ksDebounce = null; }
    if (window.__ksResizeHandler) {
        window.removeEventListener('resize', window.__ksResizeHandler);
        window.__ksResizeHandler = null;
    }
    window.__ksArrows = null;
    const el = document.getElementById('ks-suggestion-layer');
    if (el) {
        while (el.firstChild) el.removeChild(el.firstChild);
        el.style.display = 'none';
    }
})()
"""

JS_IS_GAME_OVER = "!!document.querySelector('.game-over-modal-header-inner')"

JS_CLICK_SQUARE = """
(function(sq) {
    const board = document.querySelector('wc-chess-board') ||
                  document.querySelector('chess-board') ||
                  document.querySelector('.board');
    if (!board) return false;
    const rect = board.getBoundingClientRect();
    const size = rect.width / 8;
    const flip = board.classList.contains('flipped');
    const colMap = {a:1,b:2,c:3,d:4,e:5,f:6,g:7,h:8};
    const file = colMap[sq[0]], rank = parseInt(sq[1]);
    const x = rect.left + (flip ? (8-file) : (file-1)) * size + size/2;
    const y = rect.top + (flip ? (rank-1) : (8-rank)) * size + size/2;
    const el = document.elementFromPoint(x, y);
    if (!el) return false;
    ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type => {
        el.dispatchEvent(new MouseEvent(type, {
            bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, buttons: 1
        }));
    });
    return true;
})('%s')
"""

PROFILES = {
    "human": (2.2, 1.1, 0.4, 0.18, 0.05, 0.10),
    "fast": (0.6, 0.3, 0.15, 0.09, 0.02, 0.05),
    "instant": (0.04, 0.01, 0.02, 0.03, 0.01, 0.02),
}

BROWSERS = {
    "brave": [
        r"C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
        r"C:/Program Files (x86)/BraveSoftware/Brave-Browser/Application/brave.exe",
        os.path.join(os.path.expandvars("%LOCALAPPDATA%"), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/usr/bin/brave-browser",
        "/usr/bin/brave",
    ],
    "chrome": [
        r"C:/Program Files/Google/Chrome/Application/chrome.exe",
        r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        os.path.join(os.path.expandvars("%LOCALAPPDATA%"), "Google", "Chrome", "Application", "chrome.exe"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
    ],
    "edge": [
        r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        r"C:/Program Files/Microsoft/Edge/Application/msedge.exe",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/usr/bin/microsoft-edge",
    ],
    "opera": [
        os.path.join(os.path.expandvars("%LOCALAPPDATA%"), "Programs", "Opera", "opera.exe"),
        os.path.join(os.path.expandvars("%LOCALAPPDATA%"), "Programs", "Opera GX", "opera.exe"),
        "/usr/bin/opera",
        "/Applications/Opera.app/Contents/MacOS/Opera",
    ],
    "vivaldi": [
        r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
        os.path.join(os.path.expandvars("%LOCALAPPDATA%"), "Vivaldi", "Application", "vivaldi.exe"),
        "/usr/bin/vivaldi",
        "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
    ],
}

JS_MASK_WEBDRIVER = """
(function() {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    if (!window.chrome) window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
    if (!navigator.languages || !navigator.languages.length)
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    if (navigator.plugins.length === 0) {
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const fakes = ['Chrome PDF Plugin','Chrome PDF Viewer','Native Client'];
                const arr = fakes.map(n => ({name:n, filename:n, description:''}));
                arr.item = i => arr[i];
                arr.namedItem = n => arr.find(p => p.name===n)||null;
                arr.length = fakes.length;
                return arr;
            }
        });
    }
    const origToString = Function.prototype.toString;
    Function.prototype.toString = function() {
        if (this === Function.prototype.toString) return origToString.call(origToString);
        return origToString.call(this);
    };
})();
"""

JS_GET_STATE = """
(function() {
    const board = document.querySelector('wc-chess-board') ||
                  document.querySelector('chess-board') ||
                  document.querySelector('.board');
    if (!board) return null;
    const rect = board.getBoundingClientRect();
    const size = rect.width / 8;
    const flip = board.classList.contains('flipped');
    const pieceMap = {
        wp:'P',wn:'N',wb:'B',wr:'R',wq:'Q',wk:'K',
        bp:'p',bn:'n',bb:'b',br:'r',bq:'q',bk:'k'
    };

    const isDragging =
        !!board.querySelector('.piece.dragging') ||
        !!board.querySelector('.piece[style*="pointer-events: none"]') ||
        !!document.querySelector('.piece.dragging') ||
        !!document.querySelector('[class*="piece"][class*="drag"]');

    if (isDragging) return { dragging: true };

    const grid = Array.from({length:8}, () => Array(8).fill(null));
    document.querySelectorAll('.piece').forEach(p => {
        const cls = [...p.classList];
        const type = cls.find(c => pieceMap[c]);
        const sq = cls.find(c => c.startsWith('square-'));
        if (type && sq) {
            const [col, row] = sq.split('-')[1].split('').map(Number);
            grid[8-row][col-1] = pieceMap[type];
        }
    });

    const fenRows = grid.map(r => {
        let s = '', e = 0;
        r.forEach(cell => cell ? (e && (s += e, e = 0), s += cell) : e++);
        return e ? s + e : s;
    });

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

    let myClock = null, oppClock = null, gameActive = false;
    try {
        const clockEls = document.querySelectorAll('.clock-time-monospace, .clock-component');
        if (clockEls.length >= 2) {
            gameActive = true;
            const myIdx = flip ? 0 : 1, oppIdx = flip ? 1 : 0;
            const parse = txt => {
                const parts = txt.trim().split(':');
                return parts.length === 2 ? parseInt(parts[0]) * 60 + parseInt(parts[1]) : null;
            };
            myClock = parse(clockEls[myIdx].textContent);
            oppClock = parse(clockEls[oppIdx].textContent);
        }
    } catch(e) {}

    return {
        fen: fenRows.join('/') + ' ' + side + ' - - 0 1',
        myColor: flip ? 'b' : 'w',
        active: side,
        myClock: myClock,
        oppClock: oppClock,
        gameActive: gameActive,
        boardRect: { left: rect.left, top: rect.top, width: rect.width }
    };
})()
"""

JS_SQUARE_CENTER = """
(function(sq, flip) {
    const board = document.querySelector('wc-chess-board') ||
                  document.querySelector('chess-board') ||
                  document.querySelector('.board');
    if (!board) return null;
    const rect = board.getBoundingClientRect();
    const size = rect.width / 8;
    const colMap = {a:1,b:2,c:3,d:4,e:5,f:6,g:7,h:8};
    const file = colMap[sq[0]], rank = parseInt(sq[1]);
    const x = flip ? (8-file)*size : (file-1)*size;
    const y = flip ? (rank-1)*size : (8-rank)*size;
    const jitter = size * 0.12;
    return {
        x: rect.left + x + size/2 + (Math.random()-0.5)*jitter,
        y: rect.top + y + size/2 + (Math.random()-0.5)*jitter
    };
})('%s', %s)
"""

JS_FIND_PROMOTION = """
(function(piece, myColor) {
    const win = document.querySelector('.promotion-window');
    if (!win) return null;
    const p = piece.toLowerCase();
    for (const sel of [
        '.promotion-piece.'+myColor+p,
        '.promotion-piece.w'+p,
        '.promotion-piece.b'+p,
    ]) {
        const el = win.querySelector(sel);
        if (el) {
            const r = el.getBoundingClientRect();
            return { x: r.left + r.width/2, y: r.top + r.height/2 };
        }
    }
    const idx = {b:0,n:1,q:2,r:3}[p] ?? 2;
    const all = win.querySelectorAll('.promotion-piece');
    if (all[idx]) {
        const r = all[idx].getBoundingClientRect();
        return { x: r.left + r.width/2, y: r.top + r.height/2 };
    }
    return null;
})('%s', '%s')
"""