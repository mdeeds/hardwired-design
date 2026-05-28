# Breadboard Layout Visualizer

An interactive web-based visualizer for prototyping and auditing analog Eurorack module designs on a breadboard. It parses SPICE netlist files (`.net`) and generates a high-fidelity visual representation of the circuit, allowing designers to plan physical breadboard layouts, drag components to reposition them, and route custom jumper wires.

---

## Directory Architecture

The breadboard application is structured as a clean, modular ES6-based frontend paired with a lightweight Python backend server. Below is an overview of the core files:

### Frontend Entry Points & Styling
*   **[`index.html`](file:///C:/Users/ADMIN/Documents/GitHub/hardwired-design/app/breadboard/index.html)**
    *   Defines the HTML5 semantic structure of the visualizer interface.
    *   Establishes the interactive toolbar (Inspect, Move, Wire, Bridge, Delete, Save, Reload), status indicators, rendering canvas wrapper, and color-coded legend guide.
*   **[`style.css`](file:///C:/Users/ADMIN/Documents/GitHub/hardwired-design/app/breadboard/style.css)**
    *   Implements the premium dark-mode styling system using curated HSL color tokens.
    *   Styles responsive toolbar button states, custom glassmorphism-based hover tooltips, scrollable canvas containers, and absolute legend overlays.

### Frontend Modules (ES6)
*   **[`state.js`](file:///C:/Users/ADMIN/Documents/GitHub/hardwired-design/app/breadboard/state.js)**
    *   *Role:* Data storage and shared configuration.
    *   Maintains the global reactive state object (active netlist, placed components, layout data, active drag states, currently hovered net, and active mode).
    *   Houses structural board constants (grid `CELL` dimensions, hole radii, label mappings, and power rail configurations).
*   **[`api.js`](file:///C:/Users/ADMIN/Documents/GitHub/hardwired-design/app/breadboard/api.js)**
    *   *Role:* Backend communications client.
    *   Handles asynchronous API requests to fetch netlist coordinates and persist user layouts.
    *   Manages serializing placed components, horizontal wiring, and vertical bridges, and handles saving/reloading actions.
*   **[`board.js`](file:///C:/Users/ADMIN/Documents/GitHub/hardwired-design/app/breadboard/board.js)**
    *   *Role:* Rendering pipeline and layout engine.
    *   Performs pixel-to-grid coordinate calculations and auto-placement heuristics for components based on their type (DIP ICs straddling the center gap, resistors/capacitors spanning signal lines, and three-pin transistors).
    *   Draws the highly detailed breadboard background, metal clip rails, and detailed component visualizations (such as lead wires, body color codes, and pin nodes).
    *   Implements Union-Find algorithms to dynamically determine if nets are fully connected, disconnected, or have a bus conflict (e.g. bridging two distinct signal nets in the same column section).
*   **[`main.js`](file:///C:/Users/ADMIN/Documents/GitHub/hardwired-design/app/breadboard/main.js)**
    *   *Role:* Event router and user interaction layer.
    *   Manages event listeners for canvas mouse actions (`mousemove` for tooltips/previews, `mousedown` and `mouseup` to capture component grab/dragging).
    *   Translates inputs into editing commands (like dropping wire coordinates or deleting existing bridges) and binds global keyboard hotkeys.

### Backend Server
*   **[`server.py`](file:///C:/Users/ADMIN/Documents/GitHub/hardwired-design/app/breadboard/server.py)**
    *   *Role:* Custom lightweight web server.
    *   Contains a custom SPICE Netlist parser that extracts components, pins, and signal connections from a standard `.net` simulation deck.
    *   Serves frontend assets, exposes JSON endpoints (`/api/netlist` and `/api/layout`), and persists the active state to an adjacent layout file (`.bb`) on save.

---

## Running the Application

To run the visualizer with a specific netlist, launch the backend server using Python:

```bash
python server.py --netfile path/to/circuit.net --port 8000
```
Then navigate to `http://localhost:8000` in your web browser.
