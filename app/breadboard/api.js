import { state, setStatus } from './state.js';
import { placeComponents, buildPinMap, computeConnectivity, resizeCanvas, draw } from './board.js';

export async function loadData() {
  try {
    const [netlistResp, layoutResp] = await Promise.all([
      fetch('/api/netlist'),
      fetch('/api/layout')
    ]);
    if (!netlistResp.ok || !layoutResp.ok) {
      throw new Error('Failed to fetch design data');
    }
    state.netlistData = await netlistResp.json();
    state.layoutData = await layoutResp.json();
    
    // Set title
    const titleEl = document.getElementById('circuit-title');
    if (titleEl) {
      titleEl.textContent = state.netlistData.title || 'Untitled Circuit';
    }

    placeComponents();
    buildPinMap();
    computeConnectivity();
    resizeCanvas();
    draw();

    const netCount = state.netlistData.nets ? Object.keys(state.netlistData.nets).length : 0;
    setStatus(`Loaded ${state.netlistData.components.length} components, ${netCount} nets`);
  } catch (e) {
    console.error(e);
    setStatus('Load failed: ' + e.message);
  }
}

export async function saveLayout() {
  state.layoutData.component_positions = {};
  state.layoutData.component_rows = {};
  for (const comp of state.placedComponents) {
    state.layoutData.component_positions[comp.name] = comp.col;
    if (comp.placementRow != null) {
      state.layoutData.component_rows[comp.name] = comp.placementRow;
    }
  }
  try {
    await fetch('/api/layout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state.layoutData)
    });
    setStatus('Layout saved ✓');
  } catch (e) {
    setStatus('Save failed: ' + e.message);
  }
}

export async function reloadLayout() {
  try {
    const resp = await fetch('/api/layout');
    state.layoutData = await resp.json();
    placeComponents();
    buildPinMap();
    computeConnectivity();
    draw();
    setStatus('Layout reloaded ✓');
  } catch (e) {
    setStatus('Reload failed: ' + e.message);
  }
}

