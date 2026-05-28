import { state, CONSTANTS } from './state.js';

export function rowY(row) {
  if (row <= 6) {
    return CONSTANTS.PAD_TOP + row * CONSTANTS.CELL;
  } else {
    return CONSTANTS.PAD_TOP + row * CONSTANTS.CELL + CONSTANTS.ROW_GAP;
  }
}

export function rowFromY(py) {
  let bestRow = 0;
  let bestDist = Infinity;
  for (let r = 0; r < CONSTANTS.TOTAL_ROWS; r++) {
    const dist = Math.abs(py - rowY(r));
    if (dist < bestDist) {
      bestDist = dist;
      bestRow = r;
    }
  }
  return bestRow;
}

export function colX(col) {
  return CONSTANTS.PAD_LEFT + col * CONSTANTS.CELL;
}

export function colFromX(px) {
  return Math.round((px - CONSTANTS.PAD_LEFT) / CONSTANTS.CELL);
}

export function getMousePos(e) {
  const rect = state.canvas.getBoundingClientRect();
  return {
    x: e.clientX - rect.left + state.canvasWrap.scrollLeft,
    y: e.clientY - rect.top + state.canvasWrap.scrollTop,
  };
}

export function getHoleFromMouse(e) {
  const pos = getMousePos(e);
  const mx = pos.x;
  const my = pos.y;

  let bestDist = Infinity;
  let bestHole = null;

  for (let r = 0; r < CONSTANTS.TOTAL_ROWS; r++) {
    for (let c = 0; c < state.totalCols; c++) {
      const hx = colX(c);
      const hy = rowY(r);
      const dx = mx - hx;
      const dy = my - hy;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < CONSTANTS.CELL * 0.6 && dist < bestDist) {
        bestDist = dist;
        bestHole = { col: c, row: r };
      }
    }
  }

  return bestHole;
}

export function placeComponents() {
  state.placedComponents = [];

  if (!state.netlistData || !state.netlistData.components) return;

  // Separate components by type for placement
  const ics = [];
  const small = []; // 2pin and 3pin

  for (const comp of state.netlistData.components) {
    if (comp.type === 'ic') {
      ics.push(comp);
    } else {
      small.push(comp);
    }
  }

  // --- Place ICs straddling the center gap ---
  // ICs go at the center gap (rows e/f = rows 6/7)
  let icCol = 1;
  for (const comp of ics) {
    const savedCol = state.layoutData.component_positions?.[comp.name];
    const startCol = savedCol != null ? savedCol : icCol;

    state.placedComponents.push({
      ...comp,
      col: startCol,
      pinCols: [startCol, startCol+1, startCol+2, startCol+3,
                startCol+3, startCol+2, startCol+1, startCol],
      pinRows: [6, 6, 6, 6, 7, 7, 7, 7],
      section: 'both',
    });
    if (savedCol == null) icCol = startCol + 4 + CONSTANTS.COMPONENT_GAP + 1;
  }

  // --- Place small components in available rows ---
  const placementRows = [3, 4, 8, 9]; // rows b, c, h, i
  let currentRowIdx = 0;
  let col = 1;

  for (const comp of small) {
    const savedCol = state.layoutData.component_positions?.[comp.name];

    if (comp.type === '2pin') {
      const neededWidth = 5; // 2-pin spans 5 holes
      const startCol = savedCol != null ? savedCol : col;

      // Determine placement row
      let placementRow;
      if (savedCol != null) {
        placementRow = state.layoutData.component_rows?.[comp.name] ?? placementRows[currentRowIdx % placementRows.length];
      } else {
        // Check if we need to wrap to next row
        if (col + neededWidth > state.totalCols - 1) {
          currentRowIdx++;
          col = 1;
        }
        placementRow = placementRows[currentRowIdx % placementRows.length];
      }

      state.placedComponents.push({
        ...comp,
        col: startCol,
        pinCols: [startCol, startCol + 4],
        pinRows: [placementRow, placementRow],
        section: CONSTANTS.TOP_BUS_ROWS.includes(placementRow) ? 'top' : 'bottom',
        placementRow: placementRow,
      });
      if (savedCol == null) col = startCol + neededWidth + CONSTANTS.COMPONENT_GAP;

    } else if (comp.type === '3pin') {
      const neededWidth = 3;
      const startCol = savedCol != null ? savedCol : col;

      let placementRow;
      if (savedCol != null) {
        placementRow = state.layoutData.component_rows?.[comp.name] ?? placementRows[currentRowIdx % placementRows.length];
      } else {
        if (col + neededWidth > state.totalCols - 1) {
          currentRowIdx++;
          col = 1;
        }
        placementRow = placementRows[currentRowIdx % placementRows.length];
      }

      state.placedComponents.push({
        ...comp,
        col: startCol,
        pinCols: [startCol, startCol + 1, startCol + 2],
        pinRows: [placementRow, placementRow, placementRow],
        section: CONSTANTS.TOP_BUS_ROWS.includes(placementRow) ? 'top' : 'bottom',
        placementRow: placementRow,
      });
      if (savedCol == null) col = startCol + neededWidth + CONSTANTS.COMPONENT_GAP;
    }
  }
}

export function recomputeComponentPins(comp) {
  const c = comp.col;
  if (comp.type === '2pin') {
    comp.pinCols = [c, c + 4];
    const r = comp.placementRow ?? comp.pinRows[0];
    comp.pinRows = [r, r];
  } else if (comp.type === '3pin') {
    comp.pinCols = [c, c + 1, c + 2];
    const r = comp.placementRow ?? comp.pinRows[0];
    comp.pinRows = [r, r, r];
  } else if (comp.type === 'ic') {
    comp.pinCols = [c, c+1, c+2, c+3, c+3, c+2, c+1, c];
    comp.pinRows = [6, 6, 6, 6, 7, 7, 7, 7];
  }
}

export function pinKey(col, row) {
  return `${col},${row}`;
}

export function buildPinMap() {
  state.pinMap.clear();
  state.busNets.clear();

  for (const comp of state.placedComponents) {
    for (let i = 0; i < comp.pins.length; i++) {
      const netName = comp.pins[i].toLowerCase();
      if (netName === 'nc') continue;
      const c = comp.pinCols[i];
      const r = comp.pinRows[i];

      state.pinMap.set(pinKey(c, r), {
        component: comp.name,
        pinIndex: i,
        pinLabel: comp.pin_labels[i],
        netName: netName,
        compType: comp.type,
        compValue: comp.value,
      });

      // Track nets per vertical bus (column)
      if (!state.busNets.has(c)) state.busNets.set(c, new Set());
      state.busNets.get(c).add(netName);
    }
  }
}

export function computeConnectivity() {
  state.connectivity.clear();

  const netCols = new Map();
  for (const comp of state.placedComponents) {
    for (let i = 0; i < comp.pins.length; i++) {
      const net = comp.pins[i].toLowerCase();
      if (net === 'nc') continue;
      const c = comp.pinCols[i];
      const r = comp.pinRows[i];
      const section = CONSTANTS.TOP_BUS_ROWS.includes(r) ? 'top' : 'bottom';

      if (!netCols.has(net)) netCols.set(net, new Set());
      netCols.get(net).add(`${c}:${section}`);
    }
  }

  // Union-find
  const parent = new Map();
  function find(x) {
    if (!parent.has(x)) parent.set(x, x);
    if (parent.get(x) !== x) parent.set(x, find(parent.get(x)));
    return parent.get(x);
  }
  function union(a, b) {
    const ra = find(a), rb = find(b);
    if (ra !== rb) parent.set(ra, rb);
  }

  // Wires connect columns in same section
  const wires = state.layoutData.wires || [];
  for (const wire of wires) {
    const section = CONSTANTS.TOP_BUS_ROWS.includes(wire.row) ? 'top' : 'bottom';
    for (let c = Math.min(wire.col1, wire.col2); c < Math.max(wire.col1, wire.col2); c++) {
      union(`${c}:${section}`, `${c+1}:${section}`);
    }
  }

  // Bridges connect top and bottom of same column
  const bridges = state.layoutData.bridges || [];
  for (const bridge of bridges) {
    union(`${bridge.col}:top`, `${bridge.col}:bottom`);
  }

  // Power nets: all their occurrences are connected
  for (const pnet of CONSTANTS.POWER_NETS) {
    if (netCols.has(pnet)) {
      const locs = [...netCols.get(pnet)];
      for (let i = 1; i < locs.length; i++) {
        union(locs[0], locs[i]);
      }
    }
  }

  // Determine connectivity status for each net
  for (const [net, locs] of netCols) {
    const locArr = [...locs];
    if (CONSTANTS.POWER_NETS.has(net)) {
      state.connectivity.set(net, 'connected');
      continue;
    }
    if (locArr.length <= 1) {
      state.connectivity.set(net, 'connected');
      continue;
    }
    const root = find(locArr[0]);
    let allConnected = true;
    for (let i = 1; i < locArr.length; i++) {
      if (find(locArr[i]) !== root) {
        allConnected = false;
        break;
      }
    }
    state.connectivity.set(net, allConnected ? 'connected' : 'disconnected');
  }
}

export function resizeCanvas() {
  const w = CONSTANTS.PAD_LEFT + state.totalCols * CONSTANTS.CELL + 40;
  const h = CONSTANTS.PAD_TOP + CONSTANTS.TOTAL_ROWS * CONSTANTS.CELL + CONSTANTS.ROW_GAP + 40;
  state.canvas.width = w;
  state.canvas.height = h;
}

export function hitTestComponent(mx, my) {
  // Check components in reverse order (top-most first)
  for (let i = state.placedComponents.length - 1; i >= 0; i--) {
    const comp = state.placedComponents[i];
    if (comp.type === '2pin') {
      const x1 = colX(comp.pinCols[0]);
      const x2 = colX(comp.pinCols[1]);
      const y = rowY(comp.pinRows[0]);
      const margin = CONSTANTS.CELL * 0.5;
      if (mx >= x1 - margin && mx <= x2 + margin &&
          my >= y - margin && my <= y + margin) {
        return comp;
      }
    } else if (comp.type === '3pin') {
      const x1 = colX(comp.pinCols[0]);
      const x3 = colX(comp.pinCols[2]);
      const y = rowY(comp.pinRows[0]);
      const margin = CONSTANTS.CELL * 0.5;
      if (mx >= x1 - margin && mx <= x3 + margin &&
          my >= y - margin && my <= y + margin) {
        return comp;
      }
    } else if (comp.type === 'ic') {
      const x1 = colX(comp.col) - 8;
      const x2 = colX(comp.col + 3) + 8;
      const y1 = rowY(6) - CONSTANTS.CELL * 0.5;
      const y2 = rowY(7) + CONSTANTS.CELL * 0.5;
      if (mx >= x1 && mx <= x2 && my >= y1 && my <= y2) {
        return comp;
      }
    }
  }
  return null;
}

export function findWireAt(col, row) {
  const wires = state.layoutData.wires || [];
  return wires.find(w =>
    w.row === row &&
    col >= Math.min(w.col1, w.col2) &&
    col <= Math.max(w.col1, w.col2)
  );
}

export function findBridgeAt(col) {
  const bridges = state.layoutData.bridges || [];
  return bridges.find(b => b.col === col);
}

// --- Drawing Helpers ---

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
}

function drawPowerStripes(ctx, boardX, boardW) {
  // Top power rails
  for (const r of CONSTANTS.TOP_POWER) {
    const y = rowY(r) - CONSTANTS.CELL / 2 + 2;
    ctx.fillStyle = r === 0 ? '#e8d4d4' : '#d4e0e8';
    ctx.fillRect(boardX + 4, y, boardW - 8, CONSTANTS.CELL - 4);
  }
  // Bottom power rails
  for (const r of CONSTANTS.BOTTOM_POWER) {
    const y = rowY(r) - CONSTANTS.CELL / 2 + 2;
    ctx.fillStyle = r === 12 ? '#e8d4d4' : '#d4e0e8';
    ctx.fillRect(boardX + 4, y, boardW - 8, CONSTANTS.CELL - 4);
  }
}

function drawHole(ctx, col, row) {
  const x = colX(col);
  const y = rowY(row);
  const isHovered = state.hoveredHole && state.hoveredHole.col === col && state.hoveredHole.row === row;

  ctx.beginPath();
  ctx.arc(x, y, CONSTANTS.HOLE_R, 0, Math.PI * 2);
  ctx.fillStyle = isHovered ? '#555' : '#333';
  ctx.fill();
  ctx.strokeStyle = '#666';
  ctx.lineWidth = 0.5;
  ctx.stroke();
}

function drawWire(ctx, wire) {
  const y = rowY(wire.row);
  const x1 = colX(Math.min(wire.col1, wire.col2));
  const x2 = colX(Math.max(wire.col1, wire.col2));

  ctx.strokeStyle = wire.color || '#40a0ff';
  ctx.lineWidth = 2.5;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(x1, y);
  ctx.lineTo(x2, y);
  ctx.stroke();

  // Endpoint dots
  for (const x of [x1, x2]) {
    ctx.beginPath();
    ctx.arc(x, y, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = wire.color || '#40a0ff';
    ctx.fill();
  }
}

function drawBridge(ctx, bridge) {
  const x = colX(bridge.col);
  const y1 = rowY(6);
  const y2 = rowY(7);

  const bulge = 12;
  ctx.strokeStyle = bridge.color || '#ff8040';
  ctx.lineWidth = 2.5;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(x, y1);
  ctx.bezierCurveTo(x + bulge, y1 + 4, x + bulge, y2 - 4, x, y2);
  ctx.stroke();

  for (const y of [y1, y2]) {
    ctx.beginPath();
    ctx.arc(x, y, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = bridge.color || '#ff8040';
    ctx.fill();
  }
}

function drawTwoPin(ctx, comp) {
  const x1 = colX(comp.pinCols[0]);
  const x2 = colX(comp.pinCols[1]);
  const y = rowY(comp.pinRows[0]);

  // Component body
  const bodyX = x1 + CONSTANTS.CELL * 0.8;
  const bodyW = x2 - x1 - CONSTANTS.CELL * 1.6;
  const bodyH = CONSTANTS.CELL * 0.7;

  // Lead wires
  ctx.strokeStyle = '#888';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x1, y);
  ctx.lineTo(bodyX, y);
  ctx.moveTo(bodyX + bodyW, y);
  ctx.lineTo(x2, y);
  ctx.stroke();

  // Body
  const prefix = comp.prefix;
  let bodyColor;
  if (prefix === 'R') bodyColor = '#aa8866';
  else if (prefix === 'C') bodyColor = '#6688aa';
  else if (prefix === 'L') bodyColor = '#88aa66';
  else if (prefix === 'D') bodyColor = '#aa6688';
  else if (prefix === 'V' || prefix === 'I') bodyColor = '#8866aa';
  else bodyColor = '#888';

  ctx.fillStyle = bodyColor;
  ctx.strokeStyle = '#555';
  ctx.lineWidth = 1;
  roundRect(ctx, bodyX, y - bodyH / 2, bodyW, bodyH, 3);

  // Label
  ctx.fillStyle = '#fff';
  ctx.font = 'bold 9px ' + getComputedStyle(document.body).getPropertyValue('--font-mono');
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(comp.name, (x1 + x2) / 2, y - 1);
  if (comp.value) {
    ctx.font = '8px ' + getComputedStyle(document.body).getPropertyValue('--font-mono');
    ctx.fillStyle = '#ddd';
    ctx.fillText(comp.value, (x1 + x2) / 2, y + 8);
  }
}

function drawThreePin(ctx, comp) {
  const y = rowY(comp.pinRows[0]);

  // Body (small rectangle spanning the 3 pins)
  const x1 = colX(comp.pinCols[0]);
  const x3 = colX(comp.pinCols[2]);
  const bodyX = x1 - 4;
  const bodyW = x3 - x1 + 8;
  const bodyH = CONSTANTS.CELL * 0.9;

  // Draw a D-shaped body for transistors
  ctx.fillStyle = comp.prefix === 'Q' || comp.prefix === 'J' || comp.prefix === 'M'
    ? '#556677' : '#667755';
  ctx.strokeStyle = '#444';
  ctx.lineWidth = 1;

  ctx.beginPath();
  ctx.moveTo(bodyX, y - bodyH / 2);
  ctx.lineTo(bodyX + bodyW, y - bodyH / 2);
  ctx.arc(bodyX + bodyW, y, bodyH / 2, -Math.PI / 2, Math.PI / 2);
  ctx.lineTo(bodyX, y + bodyH / 2);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();

  // Label
  ctx.fillStyle = '#fff';
  ctx.font = 'bold 9px ' + getComputedStyle(document.body).getPropertyValue('--font-mono');
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(comp.name, (x1 + x3) / 2, y - 1);
  if (comp.value) {
    ctx.font = '7px ' + getComputedStyle(document.body).getPropertyValue('--font-mono');
    ctx.fillStyle = '#ccc';
    ctx.fillText(comp.value, (x1 + x3) / 2, y + 8);
  }
}

function drawIC(ctx, comp) {
  const leftCol = comp.col;
  const rightCol = comp.col + 3;
  const x1 = colX(leftCol) - 6;
  const x2 = colX(rightCol) + 6;
  const y1 = rowY(6) - CONSTANTS.CELL * 0.4;
  const y2 = rowY(7) + CONSTANTS.CELL * 0.4;

  // Body
  ctx.fillStyle = '#2a2a2a';
  ctx.strokeStyle = '#555';
  ctx.lineWidth = 1.5;
  roundRect(ctx, x1, y1, x2 - x1, y2 - y1, 4);

  // Notch
  ctx.beginPath();
  ctx.arc(x1, (y1 + y2) / 2, 4, -Math.PI / 2, Math.PI / 2);
  ctx.fillStyle = '#444';
  ctx.fill();

  // Pin 1 dot
  ctx.beginPath();
  ctx.arc(x1 + 8, y1 + 8, 2, 0, Math.PI * 2);
  ctx.fillStyle = '#888';
  ctx.fill();

  // Label
  ctx.fillStyle = '#ccc';
  ctx.font = 'bold 9px ' + getComputedStyle(document.body).getPropertyValue('--font-mono');
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(comp.name, (x1 + x2) / 2, (y1 + y2) / 2 - 4);
  if (comp.value) {
    ctx.font = '7px ' + getComputedStyle(document.body).getPropertyValue('--font-mono');
    ctx.fillStyle = '#999';
    ctx.fillText(comp.value, (x1 + x2) / 2, (y1 + y2) / 2 + 6);
  }
}

function getPinColor(col, row, netName) {
  // Check for bus conflict
  const netsOnBus = state.busNets.get(col);
  if (netsOnBus && netsOnBus.size > 1) {
    const realNets = new Set([...netsOnBus].filter(n => n !== 'nc'));
    if (realNets.size > 1) {
      const section = CONSTANTS.TOP_BUS_ROWS.includes(row) ? CONSTANTS.TOP_BUS_ROWS : CONSTANTS.BOTTOM_BUS_ROWS;
      const sectionNets = new Set();
      for (const sr of section) {
        const info = state.pinMap.get(pinKey(col, sr));
        if (info && info.netName !== 'nc') {
          sectionNets.add(info.netName);
        }
      }
      if (sectionNets.size > 1) {
        return '#ff2020'; // Conflict!
      }
    }
  }

  if (CONSTANTS.POWER_NETS.has(netName)) {
    return '#aaa';
  }

  const status = state.connectivity.get(netName);
  if (status === 'disconnected') {
    return '#3060cc';
  }

  return '#aaa';
}

function drawPins(ctx, comp) {
  for (let i = 0; i < comp.pins.length; i++) {
    const net = comp.pins[i].toLowerCase();
    if (net === 'nc') continue;

    const c = comp.pinCols[i];
    const r = comp.pinRows[i];
    const x = colX(c);
    const y = rowY(r);

    // Determine pin color
    let color = getPinColor(c, r, net);

    // Check if this pin is highlighted
    if (state.hoveredNet && net === state.hoveredNet) {
      color = '#f0c040';
    }

    ctx.beginPath();
    ctx.arc(x, y, CONSTANTS.PIN_R, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = '#222';
    ctx.lineWidth = 0.5;
    ctx.stroke();
  }
}

function drawComponent(ctx, comp) {
  if (comp.type === '2pin') {
    drawTwoPin(ctx, comp);
  } else if (comp.type === '3pin') {
    drawThreePin(ctx, comp);
  } else if (comp.type === 'ic') {
    drawIC(ctx, comp);
  }
}

function drawDragGhost(ctx, comp, ghostCol, ghostRow) {
  ctx.save();
  ctx.globalAlpha = 0.6;

  // Create a temporary comp copy with the ghost position
  const ghost = { ...comp, col: ghostCol };
  if (comp.type !== 'ic' && ghostRow != null) {
    ghost.placementRow = ghostRow;
  }
  recomputeComponentPins(ghost);

  // Draw ghost with green tint
  if (ghost.type === '2pin') {
    const x1 = colX(ghost.pinCols[0]);
    const x2 = colX(ghost.pinCols[1]);
    const y = rowY(ghost.pinRows[0]);
    const bodyX = x1 + CONSTANTS.CELL * 0.8;
    const bodyW = x2 - x1 - CONSTANTS.CELL * 1.6;
    const bodyH = CONSTANTS.CELL * 0.7;

    ctx.strokeStyle = '#8f8';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x1, y); ctx.lineTo(bodyX, y);
    ctx.moveTo(bodyX + bodyW, y); ctx.lineTo(x2, y);
    ctx.stroke();

    ctx.fillStyle = '#4a8';
    ctx.strokeStyle = '#8f8';
    ctx.lineWidth = 2;
    roundRect(ctx, bodyX, y - bodyH / 2, bodyW, bodyH, 3);

    ctx.fillStyle = '#fff';
    ctx.font = 'bold 9px ' + getComputedStyle(document.body).getPropertyValue('--font-mono');
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(ghost.name, (x1 + x2) / 2, y);
  } else if (ghost.type === '3pin') {
    const x1 = colX(ghost.pinCols[0]);
    const x3 = colX(ghost.pinCols[2]);
    const y = rowY(ghost.pinRows[0]);
    const bodyX = x1 - 4;
    const bodyW = x3 - x1 + 8;
    const bodyH = CONSTANTS.CELL * 0.9;

    ctx.fillStyle = '#4a8';
    ctx.strokeStyle = '#8f8';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(bodyX, y - bodyH / 2);
    ctx.lineTo(bodyX + bodyW, y - bodyH / 2);
    ctx.arc(bodyX + bodyW, y, bodyH / 2, -Math.PI / 2, Math.PI / 2);
    ctx.lineTo(bodyX, y + bodyH / 2);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#fff';
    ctx.font = 'bold 9px ' + getComputedStyle(document.body).getPropertyValue('--font-mono');
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(ghost.name, (x1 + x3) / 2, y);
  } else if (ghost.type === 'ic') {
    const leftCol = ghost.col;
    const rightCol = ghost.col + 3;
    const x1 = colX(leftCol) - 6;
    const x2 = colX(rightCol) + 6;
    const y1 = rowY(6) - CONSTANTS.CELL * 0.4;
    const y2 = rowY(7) + CONSTANTS.CELL * 0.4;

    ctx.fillStyle = '#2a4a2a';
    ctx.strokeStyle = '#8f8';
    ctx.lineWidth = 2;
    roundRect(ctx, x1, y1, x2 - x1, y2 - y1, 4);

    ctx.fillStyle = '#8f8';
    ctx.font = 'bold 9px ' + getComputedStyle(document.body).getPropertyValue('--font-mono');
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(ghost.name, (x1 + x2) / 2, (y1 + y2) / 2);
  }

  // Draw ghost pins
  for (let i = 0; i < ghost.pins.length; i++) {
    if (ghost.pins[i].toLowerCase() === 'nc') continue;
    const x = colX(ghost.pinCols[i]);
    const y = rowY(ghost.pinRows[i]);
    ctx.beginPath();
    ctx.arc(x, y, CONSTANTS.PIN_R, 0, Math.PI * 2);
    ctx.fillStyle = '#8f8';
    ctx.fill();
    ctx.strokeStyle = '#4a4';
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  ctx.restore();
}

// --- Main draw function ---

export function draw() {
  if (!state.canvas) return;
  const ctx = state.canvas.getContext('2d');
  const w = state.canvas.width;
  const h = state.canvas.height;

  // Background
  ctx.fillStyle = '#1a1a2e';
  ctx.fillRect(0, 0, w, h);

  // Board background
  const boardX = CONSTANTS.PAD_LEFT - 10;
  const boardY = CONSTANTS.PAD_TOP - 10;
  const boardW = state.totalCols * CONSTANTS.CELL + 20;
  const boardH = CONSTANTS.TOTAL_ROWS * CONSTANTS.CELL + CONSTANTS.ROW_GAP + 20;
  ctx.fillStyle = '#e8e4d4';
  ctx.strokeStyle = '#999';
  ctx.lineWidth = 2;
  roundRect(ctx, boardX, boardY, boardW, boardH, 8);

  // Center gap
  const gapY = rowY(6) + CONSTANTS.CELL / 2 + 2;
  const gapH = CONSTANTS.ROW_GAP + CONSTANTS.CELL - 4;
  ctx.fillStyle = '#c8c4b0';
  ctx.fillRect(boardX + 4, gapY, boardW - 8, gapH);

  // Power rail stripes
  drawPowerStripes(ctx, boardX, boardW);

  // Row labels
  ctx.font = '11px ' + getComputedStyle(document.body).getPropertyValue('--font-mono');
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let r = 0; r < CONSTANTS.TOTAL_ROWS; r++) {
    const y = rowY(r);
    ctx.fillStyle = CONSTANTS.TOP_POWER.includes(r) || CONSTANTS.BOTTOM_POWER.includes(r) ? '#888' : '#666';
    ctx.fillText(CONSTANTS.ROW_LABELS[r], CONSTANTS.PAD_LEFT - 16, y);
  }

  // Column numbers
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  ctx.fillStyle = '#888';
  for (let c = 0; c < state.totalCols; c += 5) {
    ctx.fillText(String(c + 1), colX(c), CONSTANTS.PAD_TOP - 14);
  }

  // Draw holes
  for (let r = 0; r < CONSTANTS.TOTAL_ROWS; r++) {
    for (let c = 0; c < state.totalCols; c++) {
      drawHole(ctx, c, r);
    }
  }

  // Draw wires
  const wires = state.layoutData.wires || [];
  for (const wire of wires) {
    drawWire(ctx, wire);
  }

  // Draw bridges
  const bridges = state.layoutData.bridges || [];
  for (const bridge of bridges) {
    drawBridge(ctx, bridge);
  }

  // Draw components (skip the one being dragged - it's drawn as a ghost)
  for (const comp of state.placedComponents) {
    if (comp === state.dragComp) continue;
    drawComponent(ctx, comp);
  }

  // Draw pins (on top of everything, skip dragged component)
  for (const comp of state.placedComponents) {
    if (comp === state.dragComp) continue;
    drawPins(ctx, comp);
  }

  // Draw drag ghost
  if (state.dragComp && state.dragGhostCol != null) {
    drawDragGhost(ctx, state.dragComp, state.dragGhostCol, state.dragGhostRow);
  }

  // Wire being drawn
  if (state.wireStart && state.hoveredHole) {
    ctx.strokeStyle = state.mode === 'bridge' ? '#ff804080' : '#40a0ff80';
    ctx.lineWidth = 3;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(colX(state.wireStart.col), rowY(state.wireStart.row));
    ctx.lineTo(colX(state.hoveredHole.col), rowY(state.hoveredHole.row));
    ctx.stroke();
    ctx.setLineDash([]);
  }
}
