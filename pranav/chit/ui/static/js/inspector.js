(() => {
    const canvas = document.getElementById('brainCanvas');
    const ctx = canvas.getContext('2d');

    const statusHudTitle = document.getElementById('brainTitle');
    const statusVerdictDot = document.getElementById('verdictDot');
    const statusVerdict = document.getElementById('brainVerdict');
    const compFill = document.getElementById('compFill');
    const compCounts = document.getElementById('compCounts');
    const ckptStamp = document.getElementById('ckptStamp');
    const lobeStrip = document.getElementById('lobeStrip');
    const zoomLabel = document.getElementById('zoomLabel');

    const pathCard = document.getElementById('pathCard');
    const cardTitle = document.getElementById('cardTitle');
    const cardSubtitle = document.getElementById('cardSubtitle');
    const cardBadge = document.getElementById('cardBadge');
    const cardPrompt = document.getElementById('cardPrompt');
    const cardRawAnswer = document.getElementById('cardRawAnswer');
    const cardReason = document.getElementById('cardReason');
    const cardChatCompareWrap = document.getElementById('cardChatCompareWrap');
    const cardChatAnswer = document.getElementById('cardChatAnswer');

    const unlockOverlay = document.getElementById('unlockOverlay');
    const unlockForm = document.getElementById('unlockForm');
    const unlockKey = document.getElementById('unlockKey');
    const unlockError = document.getElementById('unlockError');

    const probeForm = document.getElementById('probeForm');
    const probeInput = document.getElementById('probeInput');
    const probeSubmit = document.getElementById('probeSubmit');
    const compareChatChk = document.getElementById('compareChatChk');

    let dpr = Math.max(1, window.devicePixelRatio || 1);
    let viewW = window.innerWidth;
    let viewH = window.innerHeight;

    // Camera in normalized brain coordinates (-1..1 centered at 0,0)
    const cam = {
        x: 0.0,
        y: 0.03,
        zoom: 1.0,
        targetX: 0.0,
        targetY: 0.03,
        targetZoom: 1.0,
    };

    const MIN_ZOOM = 0.55;
    const MAX_ZOOM = 5.0;

    let xrayData = null;
    let activeProbe = null;
    let probeAnimStart = 0;
    let selectedPathId = null;
    let selectedLobeId = null;
    let hoveredItem = null; // { kind: 'path' | 'lobe', item }
    let pointerDown = false;
    let dragMoved = false;
    let lastMouse = { x: 0, y: 0 };

    // Colors: obsidian black void + electric blue healthy brain + amber weak + crimson broken
    const COLORS = {
        healthy: { main: '#38bdf8', glow: '#0ea5e9', soft: 'rgba(14, 165, 233, 0.22)', text: '#e0f2fe' },
        weak: { main: '#fbbf24', glow: '#f59e0b', soft: 'rgba(245, 158, 11, 0.16)', text: '#fef3c7' },
        broken: { main: '#fb7185', glow: '#e11d48', soft: 'rgba(225, 29, 72, 0.18)', text: '#ffe4e6' },
        empty: { main: '#1e3a5f', glow: '#0c4a6e', soft: 'rgba(12, 74, 110, 0.12)', text: '#7dd3fc' },
    };

    // Anatomical outer brain contour (side-profile cerebral cortex + cerebellum + brainstem)
    const CORTEX_OUTLINE = [
        [-0.95, 0.04], [-0.94, -0.18], [-0.82, -0.40], [-0.58, -0.58],
        [-0.25, -0.68], [0.12, -0.68], [0.46, -0.58], [0.74, -0.40],
        [0.92, -0.16], [0.94, 0.06], [0.83, 0.24], [0.68, 0.30],
        [0.64, 0.45], [0.46, 0.52], [0.28, 0.46], [0.18, 0.40],
        [0.14, 0.72], [-0.02, 0.74], [0.00, 0.38], [-0.22, 0.34],
        [-0.48, 0.36], [-0.74, 0.28], [-0.90, 0.18],
    ];

    // Cortical folds (gyri/sulci grooves drawn inside the electric blue brain)
    const CORTEX_FOLDS = [
        [[-0.78, -0.18], [-0.56, -0.28], [-0.36, -0.18]],
        [[-0.64, -0.44], [-0.42, -0.40], [-0.26, -0.52]],
        [[-0.20, -0.60], [-0.02, -0.44], [0.18, -0.54]],
        [[0.18, -0.60], [0.36, -0.44], [0.58, -0.42]],
        [[0.46, -0.34], [0.66, -0.24], [0.80, -0.06]],
        [[-0.74, 0.12], [-0.50, 0.04], [-0.26, 0.14]],
        [[-0.20, 0.04], [0.04, -0.06], [0.28, 0.06]],
        [[0.24, 0.16], [0.48, 0.10], [0.72, 0.18]],
        [[0.36, 0.38], [0.50, 0.36], [0.60, 0.40]], // cerebellum fold
    ];

    function apiUrl(path) {
        return `${BASE || ''}${path}`;
    }

    async function fetchJson(path, opts) {
        const res = await fetch(apiUrl(path), opts);
        let data = null;
        try { data = await res.json(); } catch { data = null; }
        return { ok: res.ok, status: res.status, data };
    }

    async function callApi(method, path, body = null) {
        return fetchJson('/_ui/proxy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ method, path, query: {}, body }),
        });
    }

    function resize() {
        dpr = Math.max(1, window.devicePixelRatio || 1);
        viewW = window.innerWidth;
        viewH = window.innerHeight;
        canvas.width = Math.floor(viewW * dpr);
        canvas.height = Math.floor(viewH * dpr);
    }
    window.addEventListener('resize', resize);
    resize();

    function baseScale() {
        return Math.min(viewW, viewH) * 0.37;
    }

    function worldToScreen(wx, wy) {
        const s = baseScale() * cam.zoom;
        return [
            viewW * 0.5 + (wx - cam.x) * s,
            viewH * 0.48 + (wy - cam.y) * s,
        ];
    }

    function screenToWorld(sx, sy) {
        const s = baseScale() * cam.zoom;
        return [
            cam.x + (sx - viewW * 0.5) / s,
            cam.y + (sy - viewH * 0.48) / s,
        ];
    }

    function clampZoom(z) {
        return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, z));
    }

    function setZoomTarget(nextZoom, anchorSx = viewW * 0.5, anchorSy = viewH * 0.48) {
        const clamped = clampZoom(nextZoom);
        const [wx, wy] = screenToWorld(anchorSx, anchorSy);
        const nextScale = baseScale() * clamped;
        cam.targetZoom = clamped;
        cam.targetX = wx - (anchorSx - viewW * 0.5) / nextScale;
        cam.targetY = wy - (anchorSy - viewH * 0.48) / nextScale;
    }

    function flyTo(wx, wy, targetZoom) {
        cam.targetX = wx;
        cam.targetY = wy;
        cam.targetZoom = clampZoom(targetZoom);
    }

    function resetView() {
        selectedLobeId = null;
        selectedPathId = null;
        flyTo(0.0, 0.03, 1.0);
        updateLobePills();
    }

    // Smooth curve drawing helper through closed or open points
    function traceSmoothPath(points, closed = false) {
        if (!points.length) return;
        ctx.beginPath();
        if (closed) {
            const last = points[points.length - 1];
            const first = points[0];
            ctx.moveTo((last[0] + first[0]) * 0.5, (last[1] + first[1]) * 0.5);
            for (let i = 0; i < points.length; i++) {
                const curr = points[i];
                const next = points[(i + 1) % points.length];
                ctx.quadraticCurveTo(curr[0], curr[1], (curr[0] + next[0]) * 0.5, (curr[1] + next[1]) * 0.5);
            }
            ctx.closePath();
        } else {
            ctx.moveTo(points[0][0], points[0][1]);
            for (let i = 1; i < points.length - 1; i++) {
                const mx = (points[i][0] + points[i + 1][0]) * 0.5;
                const my = (points[i][1] + points[i + 1][1]) * 0.5;
                ctx.quadraticCurveTo(points[i][0], points[i][1], mx, my);
            }
            const end = points[points.length - 1];
            ctx.lineTo(end[0], end[1]);
        }
    }

    function formatSavedTime(iso) {
        if (!iso) return 'unknown';
        try {
            const d = new Date(iso);
            return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
        } catch {
            return 'unknown';
        }
    }

    function updateStatusHud() {
        if (!xrayData) {
            statusHudTitle.textContent = 'No Brain Loaded';
            statusVerdictDot.className = 'pulse-dot broken';
            statusVerdict.textContent = 'No trained checkpoint is currently active on the server.';
            compFill.style.width = '0%';
            compCounts.textContent = 'Paths: 0 / 0';
            ckptStamp.textContent = 'Saved: --';
            return;
        }
        const pct = xrayData.completeness_pct ?? 0;
        statusHudTitle.textContent = `${xrayData.verdict} · ${pct}%`;
        const cls = pct >= 75 ? '' : (pct >= 42 ? 'weak' : 'broken');
        statusVerdictDot.className = `pulse-dot ${cls}`.trim();
        statusVerdict.textContent = xrayData.verdict_detail || '';
        compFill.style.width = `${Math.max(4, pct)}%`;
        compFill.style.background = pct >= 75
            ? 'linear-gradient(90deg, #0284c7, #38bdf8)'
            : (pct >= 42 ? 'linear-gradient(90deg, #d97706, #fbbf24)' : 'linear-gradient(90deg, #be123c, #fb7185)');
        const c = xrayData.counts || {};
        compCounts.textContent = `${c.healthy || 0} healthy · ${c.weak || 0} weak · ${c.broken || 0} broken`;
        ckptStamp.textContent = `Saved: ${formatSavedTime(xrayData.checkpoint?.saved_at)}`;
    }

    function updateLobePills() {
        if (!xrayData || !xrayData.lobes) {
            lobeStrip.replaceChildren();
            return;
        }
        lobeStrip.replaceChildren();
        xrayData.lobes.forEach(lobe => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'lobe-pill' + (selectedLobeId === lobe.id ? ' active' : '');
            const dot = document.createElement('span');
            dot.style.cssText = `width:7px;height:7px;border-radius:50%;background:${COLORS[lobe.status]?.main || '#38bdf8'};box-shadow:0 0 6px ${COLORS[lobe.status]?.main || '#38bdf8'};`;
            const lbl = document.createElement('span');
            lbl.textContent = lobe.name;
            btn.append(dot, lbl);
            btn.onclick = () => {
                selectedLobeId = lobe.id;
                selectedPathId = null;
                updateLobePills();
                flyTo(lobe.cx, lobe.cy, 2.25);
            };
            lobeStrip.appendChild(btn);
        });
    }

    function openPathCard(pathway) {
        selectedPathId = pathway.id;
        selectedLobeId = pathway.lobe;
        updateLobePills();

        const lobeObj = xrayData?.lobes?.find(l => l.id === pathway.lobe);
        cardTitle.textContent = pathway.label;
        cardSubtitle.textContent = `${lobeObj ? lobeObj.name : pathway.lobe} · Confidence ${Math.round((pathway.confidence || 0) * 100)}%`;

        cardBadge.className = `card-badge badge-${pathway.status}`;
        cardBadge.textContent = pathway.status === 'healthy' ? 'Healthy Path' : (pathway.status === 'weak' ? 'Weak Path' : 'Broken / Misbehaving');

        cardPrompt.textContent = pathway.prompt;
        cardRawAnswer.textContent = pathway.raw_answer;
        cardRawAnswer.className = pathway.status === 'broken' ? 'box-text alert' : 'box-text';
        cardReason.textContent = pathway.reason;
        cardReason.className = pathway.status === 'broken' ? 'box-text alert' : 'box-text';
        cardChatCompareWrap.style.display = 'none';
        pathCard.classList.add('visible');
    }

    function openProbeCard(probe) {
        const rb = probe.raw_brain || {};
        const status = rb.status || 'weak';
        cardTitle.textContent = probe.misbehaved ? '⚠️ Brain / Chat Misbehavior Trace' : '✓ Neural Signal Trace';
        const lobeObj = xrayData?.lobes?.find(l => l.id === probe.primary_lobe);
        cardSubtitle.textContent = `Primary region: ${lobeObj ? lobeObj.name : probe.primary_lobe} · Raw certainty ${Math.round((rb.confidence || 0) * 100)}%`;

        cardBadge.className = `card-badge badge-${status}`;
        cardBadge.textContent = probe.misbehaved ? 'Misbehavior Flagged' : 'Behaving Cleanly';

        cardPrompt.textContent = probe.prompt;
        cardRawAnswer.textContent = rb.text || '(empty)';
        cardRawAnswer.className = status === 'broken' ? 'box-text alert' : 'box-text';
        cardReason.textContent = probe.diagnosis || rb.reason || '';
        cardReason.className = probe.misbehaved ? 'box-text alert' : 'box-text';

        if (probe.chat) {
            cardChatCompareWrap.style.display = 'block';
            const helperNote = probe.chat.web_grounded
                ? ' [Web Search covered this]'
                : (probe.chat.memory_used ? ' [Memory Note used]' : (probe.chat.source === 'tool' ? ' [Calculator]' : ''));
            cardChatAnswer.textContent = `${probe.chat.text}${helperNote}`;
        } else {
            cardChatCompareWrap.style.display = 'none';
        }
        pathCard.classList.add('visible');
    }

    document.getElementById('closeCardBtn').onclick = () => {
        pathCard.classList.remove('visible');
    };

    // Core canvas renderer (60 fps animated bioluminescent electric-blue brain on black background)
    function render(nowMs) {
        const t = nowMs * 0.001;

        // Smooth camera interpolation
        cam.x += (cam.targetX - cam.x) * 0.14;
        cam.y += (cam.targetY - cam.y) * 0.14;
        cam.zoom += (cam.targetZoom - cam.zoom) * 0.14;
        zoomLabel.textContent = `${Math.round(cam.zoom * 100)}%`;

        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        // 1. Deep black void with faint blue radial aura in center
        ctx.fillStyle = '#02040a';
        ctx.fillRect(0, 0, viewW, viewH);

        const [cxScreen, cyScreen] = worldToScreen(0.0, 0.0);
        const s = baseScale() * cam.zoom;

        const voidGrad = ctx.createRadialGradient(cxScreen, cyScreen, s * 0.1, cxScreen, cyScreen, s * 1.45);
        voidGrad.addColorStop(0, 'rgba(14, 165, 233, 0.11)');
        voidGrad.addColorStop(0.55, 'rgba(8, 47, 73, 0.05)');
        voidGrad.addColorStop(1, 'rgba(2, 4, 10, 0)');
        ctx.fillStyle = voidGrad;
        ctx.fillRect(0, 0, viewW, viewH);

        // Zoom in detail crossfades cleanly by cam.zoom:
        const macroAlpha = Math.max(0.28, Math.min(1.0, 1.55 - cam.zoom * 0.35));
        const pathAlpha = Math.max(0.45, Math.min(1.0, (cam.zoom - 0.72) * 0.9));
        const deepZoom = cam.zoom >= 2.5;

        // 2. Glowing blue cortical brain silhouette (dim/fractured if incomplete!)
        const completeness = xrayData ? (xrayData.completeness_pct / 100) : 0.0;
        const cortexPointsScreen = CORTEX_OUTLINE.map(([px, py]) => worldToScreen(px, py));

        ctx.save();
        traceSmoothPath(cortexPointsScreen, true);
        const bodyGrad = ctx.createRadialGradient(cxScreen, cyScreen, s * 0.05, cxScreen, cyScreen, s * 1.05);
        bodyGrad.addColorStop(0, `rgba(14, 165, 233, ${0.06 + 0.08 * completeness})`);
        bodyGrad.addColorStop(0.75, `rgba(8, 51, 92, ${0.05 + 0.06 * completeness})`);
        bodyGrad.addColorStop(1, 'rgba(2, 4, 10, 0.0)');
        ctx.fillStyle = bodyGrad;
        ctx.fill();

        // Outer electric-blue silhouette stroke: solid if healthy, broken/dashed if incomplete
        ctx.lineWidth = Math.max(1.5, 2.8 * Math.min(1.6, cam.zoom));
        ctx.shadowColor = completeness < 0.4 ? 'rgba(56, 189, 248, 0.35)' : '#0ea5e9';
        ctx.shadowBlur = (14 + 14 * completeness) * macroAlpha;
        ctx.strokeStyle = `rgba(56, 189, 248, ${(0.28 + 0.65 * completeness) * macroAlpha})`;
        if (completeness < 0.45) {
            ctx.setLineDash([12, 7]);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();

        // Subtle cortical gyri/sulci folds inside the blue brain
        ctx.save();
        ctx.lineWidth = Math.max(1.0, 1.6 * Math.min(1.4, cam.zoom));
        ctx.strokeStyle = `rgba(56, 189, 248, ${(0.14 + 0.16 * completeness) * macroAlpha})`;
        CORTEX_FOLDS.forEach(fold => {
            traceSmoothPath(fold.map(([fx, fy]) => worldToScreen(fx, fy)), false);
            ctx.stroke();
        });
        ctx.restore();

        if (!xrayData) {
            // Hollow standby outline if API isn't unlocked or no model loaded
            ctx.fillStyle = 'rgba(125, 211, 252, 0.5)';
            ctx.font = '500 14px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Awaiting live checkpoint signal…', cxScreen, cyScreen);
            requestAnimationFrame(render);
            return;
        }

        const lobes = xrayData.lobes || [];
        const pathways = xrayData.pathways || [];
        const synapses = xrayData.synapses || [];
        const pathById = Object.fromEntries(pathways.map(p => [p.id, p]));
        const lobeById = Object.fromEntries(lobes.map(l => [l.id, l]));

        // 3. Transformer Layer Core Rings at brain center (real n_layer rings)
        const nLayers = Math.max(2, Math.min(12, xrayData.checkpoint?.layers || 6));
        const activeLayerTrace = activeProbe?.layer_activity || [];
        const probeElapsed = activeProbe ? (t - probeAnimStart) : 999;

        for (let l = 0; l < nLayers; l++) {
            const rad = (0.045 + l * 0.021) * s;
            const layerAct = activeLayerTrace[l] ?? 0.35;
            const wavePhase = Math.max(0, 1.0 - Math.abs(probeElapsed * 2.6 - l * 0.45));
            const pulseHit = activeProbe ? wavePhase * layerAct : 0;
            const col = activeProbe?.misbehaved && pulseHit > 0.25 ? '#fb7185' : '#38bdf8';

            ctx.save();
            ctx.beginPath();
            ctx.arc(cxScreen, cyScreen, rad, 0, Math.PI * 2);
            ctx.lineWidth = 1.2 + pulseHit * 2.2;
            ctx.strokeStyle = activeProbe?.misbehaved && pulseHit > 0.25
                ? `rgba(251, 113, 133, ${0.28 + pulseHit * 0.7})`
                : `rgba(56, 189, 248, ${0.14 + 0.16 * completeness + pulseHit * 0.6})`;
            if (pulseHit > 0.2) {
                ctx.shadowColor = col;
                ctx.shadowBlur = 12 * pulseHit;
            }
            ctx.stroke();
            ctx.restore();
        }

        // 4. Lobe Halos & Fractures (viewer sees completeness per lobe immediately!)
        lobes.forEach(lobe => {
            const [lx, ly] = worldToScreen(lobe.cx, lobe.cy);
            const rPx = Math.max(lobe.rx, lobe.ry) * s;
            const cSet = COLORS[lobe.status] || COLORS.weak;
            const isSel = selectedLobeId === lobe.id;
            const isHovered = hoveredItem?.kind === 'lobe' && hoveredItem.item.id === lobe.id;

            ctx.save();
            const g = ctx.createRadialGradient(lx, ly, rPx * 0.08, lx, ly, rPx);
            const alphaMult = lobe.status === 'healthy' ? 1.0 : (lobe.status === 'weak' ? 0.72 : 0.65);
            g.addColorStop(0, cSet.soft);
            g.addColorStop(1, 'rgba(2, 4, 10, 0)');
            ctx.fillStyle = g;
            ctx.beginPath();
            ctx.arc(lx, ly, rPx, 0, Math.PI * 2);
            ctx.fill();

            // Lobe perimeter ring (solid glowing blue when healthy, fractured dashed when broken)
            ctx.beginPath();
            ctx.ellipse(lx, ly, lobe.rx * s * 0.85, lobe.ry * s * 0.85, 0, 0, Math.PI * 2);
            ctx.lineWidth = (isSel || isHovered ? 2.2 : 1.25);
            ctx.strokeStyle = cSet.main;
            ctx.globalAlpha = (isSel || isHovered ? 0.88 : 0.36) * alphaMult * macroAlpha;
            if (lobe.status === 'broken') {
                ctx.setLineDash([6, 6]);
            }
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.restore();
        });

        // 5. Cross-lobe Synaptic Connections (real cosine similarity graph)
        ctx.save();
        synapses.forEach(syn => {
            const a = pathById[syn.from];
            const b = pathById[syn.to];
            if (!a || !b) return;
            const [ax, ay] = worldToScreen(a.x, a.y);
            const [bx, by] = worldToScreen(b.x, b.y);
            const cSet = COLORS[syn.status] || COLORS.weak;

            ctx.beginPath();
            const mx = (ax + bx) * 0.5 + (ay - by) * 0.12;
            const my = (ay + by) * 0.5 + (bx - ax) * 0.12;
            ctx.moveTo(ax, ay);
            ctx.quadraticCurveTo(mx, my, bx, by);
            ctx.lineWidth = (0.7 + syn.strength * 1.1) * Math.min(1.5, cam.zoom * 0.75);
            ctx.strokeStyle = cSet.main;
            ctx.globalAlpha = (syn.status === 'healthy' ? 0.24 : 0.16) * pathAlpha;
            if (syn.status === 'broken') ctx.setLineDash([4, 5]);
            ctx.stroke();
            ctx.setLineDash([]);
        });
        ctx.restore();

        // 6. Core-to-Pathway Neural Trunks + Flowing Signal Particles
        const firedIds = new Set((activeProbe?.activated_pathways || []).map(p => p.id));

        pathways.forEach((p, idx) => {
            const [px, py] = worldToScreen(p.x, p.y);
            const cSet = COLORS[p.status] || COLORS.weak;
            const isSelected = selectedPathId === p.id;
            const isHovered = hoveredItem?.kind === 'path' && hoveredItem.item.id === p.id;
            const isFired = firedIds.has(p.id);

            // Curved axon trunk from brain core (0,0) -> pathway synapse
            const ctrlX = cxScreen + (px - cxScreen) * 0.45 - (py - cyScreen) * 0.16;
            const ctrlY = cyScreen + (py - cyScreen) * 0.45 + (px - cxScreen) * 0.16;

            ctx.save();
            ctx.beginPath();
            ctx.moveTo(cxScreen, cyScreen);
            ctx.quadraticCurveTo(ctrlX, ctrlY, px, py);
            ctx.lineWidth = isSelected || isFired ? 2.6 : (isHovered ? 2.0 : 1.15);
            ctx.strokeStyle = isFired && activeProbe?.misbehaved ? COLORS.broken.main : cSet.main;
            ctx.globalAlpha = isSelected || isFired ? 0.92 : (p.status === 'healthy' ? 0.42 : 0.28) * pathAlpha;
            if (p.status === 'broken') {
                ctx.setLineDash([5, 6]);
            }
            if (isSelected || isFired || p.status === 'healthy') {
                ctx.shadowColor = isFired && activeProbe?.misbehaved ? COLORS.broken.glow : cSet.glow;
                ctx.shadowBlur = (isSelected || isFired) ? 14 : 6;
            }
            ctx.stroke();
            ctx.setLineDash([]);

            // Traveling blue pulse particle along healthy/fired pathways
            if (p.status === 'healthy' || isFired) {
                const speed = isFired ? 0.95 : 0.28;
                const u = (t * speed + idx * 0.19) % 1.0;
                const inv = 1 - u;
                const dotX = inv * inv * cxScreen + 2 * inv * u * ctrlX + u * u * px;
                const dotY = inv * inv * cyScreen + 2 * inv * u * ctrlY + u * u * py;
                ctx.beginPath();
                ctx.arc(dotX, dotY, isFired ? 3.8 : 2.3, 0, Math.PI * 2);
                ctx.fillStyle = isFired && activeProbe?.misbehaved ? '#fda4af' : '#e0f2fe';
                ctx.globalAlpha = 0.95;
                ctx.fill();
            }
            ctx.restore();
        });

        // 7. Neural Synapse Nodes (always sharp; details expand as you zoom in!)
        pathways.forEach(p => {
            const [px, py] = worldToScreen(p.x, p.y);
            const cSet = COLORS[p.status] || COLORS.weak;
            const isSelected = selectedPathId === p.id;
            const isHovered = hoveredItem?.kind === 'path' && hoveredItem.item.id === p.id;
            const isFired = firedIds.has(p.id);

            const r = (isSelected || isHovered || isFired ? 7.5 : 5.0) * Math.min(1.6, 0.75 + cam.zoom * 0.28);

            ctx.save();
            ctx.beginPath();
            ctx.arc(px, py, r, 0, Math.PI * 2);
            ctx.fillStyle = p.status === 'broken' ? '#4c0519' : '#03152e';
            ctx.fill();
            ctx.lineWidth = isSelected || isFired ? 2.8 : 2.0;
            ctx.strokeStyle = isFired && activeProbe?.misbehaved ? '#fb7185' : cSet.main;
            ctx.shadowColor = isFired && activeProbe?.misbehaved ? '#e11d48' : cSet.glow;
            ctx.shadowBlur = isSelected || isHovered || isFired ? 18 : 9;
            ctx.stroke();

            // Inner glowing core dot
            ctx.beginPath();
            ctx.arc(px, py, r * 0.42, 0, Math.PI * 2);
            ctx.fillStyle = cSet.main;
            ctx.fill();

            // Mid-zoom & deep-zoom neural path labels
            if (cam.zoom >= 1.32 || isSelected || isHovered || isFired) {
                ctx.font = `${isSelected || isHovered ? '700' : '600'} 12px Inter, sans-serif`;
                ctx.textAlign = 'center';
                ctx.shadowBlur = 6;
                ctx.shadowColor = '#02040a';
                ctx.fillStyle = cSet.text;
                ctx.fillText(p.label, px, py - r - 7);

                // Deep zoom directly inside a neural path: render inline preview right next to synapse!
                if (deepZoom && (isSelected || cam.zoom >= 3.1)) {
                    const snippet = p.raw_answer.length > 68 ? p.raw_answer.slice(0, 68) + '…' : p.raw_answer;
                    const tag = p.status === 'healthy' ? '✓ Healthy' : (p.status === 'weak' ? '⚠ Weak' : '✕ Misbehaving');
                    ctx.font = '500 10.5px Inter, sans-serif';
                    ctx.fillStyle = cSet.main;
                    ctx.fillText(`${tag} · ${Math.round((p.confidence || 0) * 100)}%`, px, py + r + 14);
                    ctx.fillStyle = 'rgba(226, 241, 255, 0.85)';
                    ctx.fillText(`"${snippet}"`, px, py + r + 29);
                }
            }
            ctx.restore();
        });

        // 8. Macro Lobe Labels (fade gently once zoomed deep inside individual pathways)
        if (cam.zoom < 2.2) {
            const lblAlpha = Math.max(0.0, Math.min(1.0, (2.2 - cam.zoom) * 1.1));
            lobes.forEach(lobe => {
                const [lx, ly] = worldToScreen(lobe.cx, lobe.cy);
                const cSet = COLORS[lobe.status] || COLORS.weak;
                ctx.save();
                ctx.globalAlpha = lblAlpha;
                ctx.textAlign = 'center';
                ctx.shadowColor = '#02040a';
                ctx.shadowBlur = 10;
                ctx.font = '700 13px Inter, sans-serif';
                ctx.fillStyle = cSet.text;
                ctx.fillText(lobe.name, lx, ly - lobe.ry * s * 0.85 - 10);
                ctx.font = '600 11px Inter, sans-serif';
                ctx.fillStyle = cSet.main;
                const stateTxt = lobe.status === 'healthy' ? 'Healthy' : (lobe.status === 'weak' ? 'Weak' : 'Broken');
                ctx.fillText(`${lobe.completeness_pct}% · ${stateTxt}`, lx, ly - lobe.ry * s * 0.85 + 5);
                ctx.restore();
            });
        }

        // Faint brainstem root indicator at bottom of brain
        const [bx, by] = worldToScreen(0.06, 0.65);
        ctx.save();
        ctx.textAlign = 'center';
        ctx.font = '500 11px Inter, sans-serif';
        ctx.fillStyle = 'rgba(125, 211, 252, 0.45)';
        ctx.fillText('Scroll to zoom into neural paths · Drag to pan · Click any glowing node', viewW * 0.5, viewH - 96);
        if (activeProbe) {
            ctx.beginPath();
            ctx.arc(bx, by, 5 + Math.sin(t * 6) * 1.5, 0, Math.PI * 2);
            ctx.fillStyle = activeProbe.misbehaved ? '#fb7185' : '#38bdf8';
            ctx.fill();
        }
        ctx.restore();

        requestAnimationFrame(render);
    }

    // Hit detection in screen pixels
    function hitTest(sx, sy) {
        if (!xrayData) return null;
        const s = baseScale() * cam.zoom;
        let bestPath = null;
        let bestDist = Infinity;
        for (const p of (xrayData.pathways || [])) {
            const [px, py] = worldToScreen(p.x, p.y);
            const d = Math.hypot(sx - px, sy - py);
            if (d < 18 && d < bestDist) {
                bestDist = d;
                bestPath = p;
            }
        }
        if (bestPath) return { kind: 'path', item: bestPath };

        for (const lobe of (xrayData.lobes || [])) {
            const [lx, ly] = worldToScreen(lobe.cx, lobe.cy);
            const dx = (sx - lx) / (lobe.rx * s * 0.85);
            const dy = (sy - ly) / (lobe.ry * s * 0.85);
            if (dx * dx + dy * dy <= 1.0) {
                return { kind: 'lobe', item: lobe };
            }
        }
        return null;
    }

    // Mouse / wheel zoom & pan interactions
    canvas.addEventListener('wheel', (e) => {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.16 : 0.86;
        setZoomTarget(cam.targetZoom * factor, e.clientX, e.clientY);
    }, { passive: false });

    canvas.addEventListener('pointerdown', (e) => {
        pointerDown = true;
        dragMoved = false;
        lastMouse = { x: e.clientX, y: e.clientY };
        canvas.classList.add('dragging');
    });

    window.addEventListener('pointermove', (e) => {
        if (pointerDown) {
            const dx = e.clientX - lastMouse.x;
            const dy = e.clientY - lastMouse.y;
            if (Math.hypot(dx, dy) > 3) dragMoved = true;
            const s = baseScale() * cam.zoom;
            cam.x -= dx / s;
            cam.y -= dy / s;
            cam.targetX = cam.x;
            cam.targetY = cam.y;
            lastMouse = { x: e.clientX, y: e.clientY };
            return;
        }
        const hit = hitTest(e.clientX, e.clientY);
        hoveredItem = hit;
        canvas.classList.toggle('hovering', Boolean(hit));
    });

    window.addEventListener('pointerup', (e) => {
        if (!pointerDown) return;
        pointerDown = false;
        canvas.classList.remove('dragging');
        if (!dragMoved) {
            const hit = hitTest(e.clientX, e.clientY);
            if (hit?.kind === 'path') {
                openPathCard(hit.item);
                flyTo(hit.item.x, hit.item.y, Math.max(cam.targetZoom, 3.2));
            } else if (hit?.kind === 'lobe') {
                selectedLobeId = hit.item.id;
                selectedPathId = null;
                updateLobePills();
                flyTo(hit.item.cx, hit.item.cy, 2.25);
            }
        }
    });

    document.getElementById('zoomInBtn').onclick = () => setZoomTarget(cam.targetZoom * 1.35);
    document.getElementById('zoomOutBtn').onclick = () => setZoomTarget(cam.targetZoom * 0.74);
    document.getElementById('resetViewBtn').onclick = resetView;
    document.getElementById('rescanBtn').onclick = () => loadXray();

    async function loadXray() {
        statusHudTitle.textContent = "Scanning Chit's Brain…";
        const r = await callApi('GET', '/model/xray');
        if (r.status === 401) {
            unlockOverlay.classList.add('visible');
            return;
        }
        if (!r.ok) {
            xrayData = null;
            updateStatusHud();
            statusVerdict.textContent = r.data?.detail || 'Could not inspect checkpoint.';
            return;
        }
        xrayData = r.data;
        updateStatusHud();
        updateLobePills();
    }

    async function runProbe(promptText) {
        const clean = promptText.trim();
        if (!clean) return;
        probeSubmit.disabled = true;
        probeSubmit.textContent = 'Probing…';
        try {
            const r = await callApi('POST', '/model/xray/probe', {
                prompt: clean,
                task: 'chat',
                think: false,
                compare_chat: compareChatChk.checked,
            });
            if (r.status === 401) {
                unlockOverlay.classList.add('visible');
                return;
            }
            if (!r.ok) {
                statusVerdict.textContent = r.data?.detail || 'Probe failed.';
                return;
            }
            activeProbe = r.data;
            probeAnimStart = performance.now() * 0.001;
            openProbeCard(activeProbe);

            // Smoothly zoom toward the activated brain pathway!
            const topId = activeProbe.activated_pathways?.[0]?.id;
            const targetPath = (xrayData?.pathways || []).find(p => p.id === topId);
            if (targetPath) {
                selectedPathId = targetPath.id;
                selectedLobeId = targetPath.lobe;
                updateLobePills();
                flyTo(targetPath.x, targetPath.y, 2.35);
            }
        } finally {
            probeSubmit.disabled = false;
            probeSubmit.textContent = 'Send Thought';
        }
    }

    probeForm.addEventListener('submit', (e) => {
        e.preventDefault();
        runProbe(probeInput.value);
    });

    document.querySelectorAll('.quick-chip').forEach(btn => {
        btn.addEventListener('click', () => {
            probeInput.value = btn.dataset.q || '';
            runProbe(probeInput.value);
        });
    });

    unlockForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        unlockError.textContent = '';
        const r = await fetchJson('/_ui/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: unlockKey.value }),
        });
        unlockKey.value = '';
        if (!r.ok) {
            unlockError.textContent = r.data?.detail || 'Invalid API key.';
            return;
        }
        unlockOverlay.classList.remove('visible');
        await loadXray();
    });

    async function bootstrap() {
        const s = await fetchJson('/_ui/session');
        if (s.ok && s.data?.authenticated) {
            unlockOverlay.classList.remove('visible');
            await loadXray();
        } else {
            unlockOverlay.classList.add('visible');
        }
    }

    requestAnimationFrame(render);
    bootstrap();
})();
