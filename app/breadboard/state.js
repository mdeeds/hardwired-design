export const state = {
  canvas: document.getElementById('board'),
  canvasWrap: document.getElementById('canvas-wrap'),
  tooltip: document.getElementById('tooltip'),
  netlistData: null,
  layoutData: { wires: [], bridges: [], component_positions: {}, component_rows: {} },
  placedComponents: [],
  totalCols: 50,
  mode: 'select', // 'select', 'move', 'wire', 'bridge', 'delete'
  hoveredHole: null,  // {col, row}
  hoveredNet: null,
  wireStart: null,    // {col, row} for wire drawing
  dragComp: null,      // The component being dragged
  dragOffset: 0,       // Column offset from mouse to component origin
  dragGhostCol: null,  // Current ghost position column during drag
  dragOffsetRow: 0,    // Row offset from mouse to component origin
  dragGhostRow: null,  // Current ghost position row during drag
  pinMap: new Map(),   // (col,row) -> pin info
  busNets: new Map(),  // col -> Set of netNames
  connectivity: new Map() // netName -> 'connected' | 'disconnected'
};

export const CONSTANTS = {
  CELL: 20,
  HOLE_R: 4,
  PIN_R: 3,
  PAD_LEFT: 60,
  PAD_TOP: 60,
  ROW_GAP: 10,
  COMPONENT_GAP: 1,
  POWER_NETS: new Set(['vcc', 'vee', 'gnd', '0']),
  ROW_LABELS: ['+', '−', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', '+', '−'],
  TOTAL_ROWS: 14,
  TOP_BUS_ROWS: [2, 3, 4, 5, 6],      // rows a-e
  BOTTOM_BUS_ROWS: [7, 8, 9, 10, 11], // rows f-j
  TOP_POWER: [0, 1],
  BOTTOM_POWER: [12, 13],
  get ALL_SIGNAL_ROWS() {
    return [...this.TOP_BUS_ROWS, ...this.BOTTOM_BUS_ROWS];
  }
};

export function setStatus(msg) {
  const statusBar = document.getElementById('status-bar');
  if (statusBar) {
    statusBar.textContent = msg;
  }
}

