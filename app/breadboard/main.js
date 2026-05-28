import { state, CONSTANTS, setStatus } from './state.js';
import { loadData, saveLayout, reloadLayout } from './api.js';
import {
  colFromX,
  getMousePos,
  getHoleFromMouse,
  colX,
  rowY,
  rowFromY,
  pinKey,
  buildPinMap,
  computeConnectivity,
  draw,
  hitTestComponent,
  findWireAt,
  findBridgeAt,
  recomputeComponentPins
} from './board.js';

function comp_type_width(comp) {
  if (comp.type === '2pin') return 5;
  if (comp.type === '3pin') return 3;
  if (comp.type === 'ic') return 4;
  return 1;
}

// Show tooltip helper
function showTooltip(e, info) {
  const lines = [
    `${info.component} pin ${info.pinLabel}`,
    `Net: ${info.netName}`,
    `Type: ${info.compType}`,
  ];
  if (info.compValue) lines.push(`Value: ${info.compValue}`);

  const status = state.connectivity.get(info.netName);
  if (status === 'disconnected') lines.push('⚠ DISCONNECTED');

  const colNets = state.busNets.get(state.hoveredHole.col);
  if (colNets && colNets.size > 1) {
    const realNets = [...colNets].filter(n => n !== 'nc');
    if (realNets.length > 1) {
      lines.push(`⛔ BUS CONFLICT: ${realNets.join(', ')}`);
    }
  }

  state.tooltip.textContent = lines.join('\n');
  state.tooltip.style.display = 'block';
  positionTooltip(e);
}

function showTooltipText(e, text) {
  state.tooltip.textContent = text;
  state.tooltip.style.display = 'block';
  positionTooltip(e);
}

function positionTooltip(e) {
  const rect = state.canvasWrap.getBoundingClientRect();
  state.tooltip.style.left = (e.clientX - rect.left + 12) + 'px';
  state.tooltip.style.top = (e.clientY - rect.top - 10) + 'px';
}

function hideTooltip() {
  state.tooltip.style.display = 'none';
}

// Click and interaction handlers
function handleWireClick(hole) {
  if (!state.wireStart) {
    if (!CONSTANTS.ALL_SIGNAL_ROWS.includes(hole.row)) {
      setStatus('Wires must be on signal rows (a-j)');
      return;
    }
    state.wireStart = hole;
    setStatus(`Wire start: col ${hole.col + 1}, row ${CONSTANTS.ROW_LABELS[hole.row]} — click end point`);
  } else {
    if (hole.row !== state.wireStart.row) {
      setStatus('Wires must be horizontal (same row). Use Bridge for cross-gap.');
      state.wireStart = null;
      return;
    }
    if (hole.col === state.wireStart.col) {
      state.wireStart = null;
      setStatus('Wire cancelled (same hole)');
      return;
    }

    const c1 = state.wireStart.col, c2 = hole.col;
    if (!state.layoutData.wires) state.layoutData.wires = [];
    state.layoutData.wires.push({ row: hole.row, col1: c1, col2: c2, color: '#40a0ff' });
    state.wireStart = null;
    computeConnectivity();
    draw();
    setStatus(`Wire added: col ${Math.min(c1, c2) + 1}–${Math.max(c1, c2) + 1}`);
  }
}

function handleBridgeClick(hole) {
  if (!CONSTANTS.TOP_BUS_ROWS.includes(hole.row) && !CONSTANTS.BOTTOM_BUS_ROWS.includes(hole.row)) {
    setStatus('Bridges connect signal rows across the center gap');
    return;
  }
  if (!state.layoutData.bridges) state.layoutData.bridges = [];
  const exists = state.layoutData.bridges.find(b => b.col === hole.col);
  if (exists) {
    setStatus(`Bridge already exists at col ${hole.col + 1}`);
    return;
  }
  state.layoutData.bridges.push({ col: hole.col, color: '#ff8040' });
  computeConnectivity();
  draw();
  setStatus(`Bridge added at col ${hole.col + 1}`);
}

function handleDeleteClick(hole) {
  if (state.layoutData.wires) {
    const wireIdx = state.layoutData.wires.findIndex(w =>
      w.row === hole.row &&
      hole.col >= Math.min(w.col1, w.col2) &&
      hole.col <= Math.max(w.col1, w.col2)
    );
    if (wireIdx >= 0) {
      state.layoutData.wires.splice(wireIdx, 1);
      computeConnectivity();
      draw();
      setStatus('Wire deleted');
      return;
    }
  }
  if (state.layoutData.bridges) {
    const bridgeIdx = state.layoutData.bridges.findIndex(b => b.col === hole.col);
    if (bridgeIdx >= 0) {
      state.layoutData.bridges.splice(bridgeIdx, 1);
      computeConnectivity();
      draw();
      setStatus('Bridge deleted');
      return;
    }
  }
  setStatus('Nothing to delete here');
}

// Mode setting function
function setMode(newMode) {
  state.mode = newMode;
  state.wireStart = null;
  state.dragComp = null;
  state.dragGhostCol = null;
  state.dragGhostRow = null;
  state.dragOffsetRow = 0;
  document.querySelectorAll('.toolbar button').forEach(b => b.classList.remove('active'));
  const btnId = {
    select: 'btn-select',
    move: 'btn-move',
    wire: 'btn-wire',
    bridge: 'btn-bridge',
    delete: 'btn-delete',
  }[newMode];
  if (btnId) document.getElementById(btnId).classList.add('active');

  if (newMode === 'move') {
    state.canvas.style.cursor = 'grab';
  } else if (newMode === 'select') {
    state.canvas.style.cursor = 'default';
  } else {
    state.canvas.style.cursor = 'crosshair';
  }
  setStatus(`Mode: ${newMode}`);
  draw();
}

// Event Listeners
state.canvas.addEventListener('mousemove', (e) => {
  const pos = getMousePos(e);

  // Handle drag
  if (state.dragComp) {
    const newCol = colFromX(pos.x) - state.dragOffset;
    // Clamp to board bounds
    const maxCol = comp_type_width(state.dragComp);
    state.dragGhostCol = Math.max(0, Math.min(state.totalCols - maxCol, newCol));

    if (state.dragComp.type !== 'ic') {
      const newRow = rowFromY(pos.y) - state.dragOffsetRow;
      // Clamp to signal rows only (indices 2-11, rows a-j)
      state.dragGhostRow = Math.max(2, Math.min(11, newRow));
    } else {
      state.dragGhostRow = null;
    }

    draw();

    if (state.dragComp.type !== 'ic' && state.dragGhostRow != null) {
      const rowLabel = CONSTANTS.ROW_LABELS[state.dragGhostRow];
      setStatus(`Moving ${state.dragComp.name} → col ${state.dragGhostCol + 1}, row ${rowLabel}`);
    } else {
      setStatus(`Moving ${state.dragComp.name} → col ${state.dragGhostCol + 1}`);
    }
    return;
  }

  const hole = getHoleFromMouse(e);
  state.hoveredHole = hole;

  if (hole) {
    const info = state.pinMap.get(pinKey(hole.col, hole.row));
    if (info) {
      state.hoveredNet = info.netName;
      showTooltip(e, info);
    } else {
      state.hoveredNet = null;
      const wireInfo = findWireAt(hole.col, hole.row);
      const bridgeInfo = findBridgeAt(hole.col);
      if (wireInfo) {
        showTooltipText(e, `Wire: col ${wireInfo.col1+1}–${wireInfo.col2+1}, row ${CONSTANTS.ROW_LABELS[wireInfo.row]}`);
      } else if (bridgeInfo) {
        showTooltipText(e, `Bridge: col ${bridgeInfo.col+1}`);
      } else {
        hideTooltip();
      }
    }
  } else {
    state.hoveredNet = null;
    hideTooltip();
  }

  // In move mode, update cursor based on what's under the mouse
  if (state.mode === 'move') {
    const comp = hitTestComponent(pos.x, pos.y);
    state.canvas.style.cursor = comp ? 'grab' : 'default';
  }

  draw();
});

state.canvas.addEventListener('mouseleave', () => {
  if (!state.dragComp) {
    state.hoveredHole = null;
    state.hoveredNet = null;
    hideTooltip();
    draw();
  }
});

state.canvas.addEventListener('mousedown', (e) => {
  if (state.mode !== 'move') return;
  if (e.button !== 0) return;

  const pos = getMousePos(e);
  const comp = hitTestComponent(pos.x, pos.y);
  if (!comp) return;

  state.dragComp = comp;
  state.dragOffset = colFromX(pos.x) - comp.col;
  state.dragGhostCol = comp.col;

  if (comp.type !== 'ic') {
    const compRow = comp.placementRow ?? comp.pinRows[0];
    state.dragOffsetRow = rowFromY(pos.y) - compRow;
    state.dragGhostRow = compRow;
  } else {
    state.dragOffsetRow = 0;
    state.dragGhostRow = null;
  }

  state.canvas.style.cursor = 'grabbing';
  hideTooltip();
  setStatus(`Dragging ${comp.name}...`);
  draw();
});

state.canvas.addEventListener('mouseup', (e) => {
  if (!state.dragComp) return;

  // Commit the drag
  if (state.dragGhostCol != null) {
    state.dragComp.col = state.dragGhostCol;

    if (state.dragComp.type !== 'ic' && state.dragGhostRow != null) {
      state.dragComp.placementRow = state.dragGhostRow;
      state.dragComp.section = CONSTANTS.TOP_BUS_ROWS.includes(state.dragGhostRow) ? 'top' : 'bottom';
    }

    recomputeComponentPins(state.dragComp);

    // Save position
    if (!state.layoutData.component_positions) state.layoutData.component_positions = {};
    state.layoutData.component_positions[state.dragComp.name] = state.dragComp.col;

    // Save row info too
    if (!state.layoutData.component_rows) state.layoutData.component_rows = {};
    if (state.dragComp.placementRow != null) {
      state.layoutData.component_rows[state.dragComp.name] = state.dragComp.placementRow;
    }
  }

  const movedName = state.dragComp.name;
  state.dragComp = null;
  state.dragGhostCol = null;
  state.dragGhostRow = null;
  state.dragOffset = 0;
  state.dragOffsetRow = 0;
  state.canvas.style.cursor = 'grab';

  // Rebuild everything
  buildPinMap();
  computeConnectivity();
  draw();
  setStatus(`Moved ${movedName} ✓`);
});

state.canvas.addEventListener('click', (e) => {
  if (state.mode === 'move') return; // Handled by mousedown/mouseup
  const hole = getHoleFromMouse(e);
  if (!hole) return;

  if (state.mode === 'wire') {
    handleWireClick(hole);
  } else if (state.mode === 'bridge') {
    handleBridgeClick(hole);
  } else if (state.mode === 'delete') {
    handleDeleteClick(hole);
  }
});

// Toolbar click listeners
document.getElementById('btn-select').addEventListener('click', () => setMode('select'));
document.getElementById('btn-move').addEventListener('click', () => setMode('move'));
document.getElementById('btn-wire').addEventListener('click', () => setMode('wire'));
document.getElementById('btn-bridge').addEventListener('click', () => setMode('bridge'));
document.getElementById('btn-delete').addEventListener('click', () => setMode('delete'));

document.getElementById('btn-save').addEventListener('click', saveLayout);
document.getElementById('btn-load').addEventListener('click', reloadLayout);

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    state.wireStart = null;
    if (state.dragComp) {
      state.dragComp = null;
      state.dragGhostCol = null;
      state.dragGhostRow = null;
      state.dragOffset = 0;
      state.dragOffsetRow = 0;
      draw();
    }
    setMode('select');
  }
  else if (e.key === 'w') setMode('wire');
  else if (e.key === 'b') setMode('bridge');
  else if (e.key === 'd') setMode('delete');
  else if (e.key === 'i') setMode('select');
  else if (e.key === 'm') setMode('move');
  else if (e.key === 's' && e.ctrlKey) {
    e.preventDefault();
    saveLayout();
  }
});

// Initialization
loadData();
