#!/usr/bin/env python3
"""
Chart Digitizer — Convert datasheet plots to CSV by clicking on the image.

Usage:
    python scripts/chart_digitizer.py

Requirements:
    pip install Pillow

Controls:
    Ctrl+V          Paste image from clipboard
    Click           Add point to active trace
    Ctrl+Z          Undo last point
    Drag red lines  Adjust left/right axis boundaries (X axis)
    Drag blue lines Adjust top/bottom axis boundaries (Y axis)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import math
import csv
import os

try:
    from PIL import Image, ImageTk, ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


TRACE_COLORS = [
    '#FF4444', '#44AAFF', '#44FF88', '#FFAA22',
    '#FF44FF', '#22DDDD', '#FFFF44', '#FF8844',
]


class ChartDigitizer:
    def __init__(self, root):
        self.root = root
        self.root.title("Chart Digitizer")

        self.image = None
        self.photo = None
        self.img_offset = (10, 10)

        # Axis boundary positions in image-relative pixels
        self.bounds = {'left': 100, 'right': 500, 'top': 50, 'bottom': 450}

        # Axis limit variables
        self.x_min = tk.DoubleVar(value=0.0)
        self.x_max = tk.DoubleVar(value=1.0)
        self.y_min = tk.DoubleVar(value=0.1)
        self.y_max = tk.DoubleVar(value=100.0)
        self.x_log = tk.BooleanVar(value=False)
        self.y_log = tk.BooleanVar(value=True)

        # Axis metadata
        self.x_title = tk.StringVar(value='')
        self.x_units = tk.StringVar(value='')
        self.y_title = tk.StringVar(value='')
        self.y_units = tk.StringVar(value='')

        # Traces: name -> list of (x, y)
        self.traces = {'trace_1': []}
        self.active_trace = tk.StringVar(value='trace_1')

        # Drag state
        self.drag_line = None

        # Axis lock — hides boundary lines so you can click anywhere
        self.axes_locked = tk.BooleanVar(value=False)

        self._build_ui()
        self._redraw()
        self._update_list()   # seed trace listbox

        self.root.bind('<Control-v>', self.paste_image)
        self.root.bind('<Control-z>', self.undo_point)

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=5,
                               sashrelief='raised')
        pane.grid(row=0, column=0, sticky='nsew')

        # ---- Canvas ----
        cf = tk.Frame(pane, bg='#2a2a2a')
        pane.add(cf, width=820)
        cf.rowconfigure(0, weight=1)
        cf.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(cf, bg='#1e1e1e', cursor='crosshair')
        hbar = tk.Scrollbar(cf, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vbar = tk.Scrollbar(cf, orient=tk.VERTICAL,   command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set,
                               scrollregion=(0, 0, 2000, 2000))
        self.canvas.grid(row=0, column=0, sticky='nsew')
        vbar.grid(row=0, column=1, sticky='ns')
        hbar.grid(row=1, column=0, sticky='ew')

        self.canvas.bind('<Button-1>',       self._on_click)
        self.canvas.bind('<B1-Motion>',      self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.canvas.bind('<Motion>',         self._on_motion)

        # ---- Control panel ----
        ctrl = tk.Frame(pane, padx=8, pady=8)
        pane.add(ctrl, width=290)

        # Image
        f = ttk.LabelFrame(ctrl, text='Image', padding=4)
        f.pack(fill='x', pady=(0, 6))
        tk.Button(f, text='Paste from Clipboard  (Ctrl+V)',
                  command=self.paste_image).pack(fill='x')
        tk.Button(f, text='Open Image File…',
                  command=self.open_image).pack(fill='x', pady=(3, 0))

        # Axis limits
        f = ttk.LabelFrame(ctrl, text='Axis Limits', padding=4)
        f.pack(fill='x', pady=(0, 6))
        f.columnconfigure(1, weight=1)
        for i, (lbl, var) in enumerate([
            ('X min', self.x_min), ('X max', self.x_max),
            ('Y min', self.y_min), ('Y max', self.y_max),
        ]):
            tk.Label(f, text=lbl+':', width=7, anchor='w').grid(
                row=i, column=0, sticky='w')
            tk.Entry(f, textvariable=var, width=14).grid(
                row=i, column=1, sticky='ew', padx=(2, 0))
        sf = tk.Frame(f)
        sf.grid(row=4, column=0, columnspan=2, sticky='w', pady=(5, 0))
        tk.Checkbutton(sf, text='X log scale', variable=self.x_log).pack(side='left')
        tk.Checkbutton(sf, text='Y log scale', variable=self.y_log).pack(
            side='left', padx=(10, 0))
        # Axis title / units
        tk.Frame(f, height=1, bg='#ccc').grid(
            row=5, column=0, columnspan=2, sticky='ew', pady=(6, 4))
        for i, (lbl, var) in enumerate([
            ('X title', self.x_title), ('X units', self.x_units),
            ('Y title', self.y_title), ('Y units', self.y_units),
        ]):
            tk.Label(f, text=lbl+':', width=7, anchor='w').grid(
                row=6+i, column=0, sticky='w')
            tk.Entry(f, textvariable=var, width=14).grid(
                row=6+i, column=1, sticky='ew', padx=(2, 0))

        # Boundaries
        f = ttk.LabelFrame(ctrl, text='Axis Boundaries', padding=4)
        f.pack(fill='x', pady=(0, 6))
        tk.Label(f, text='Drag the dashed lines to align\nwith the chart axes.',
                 justify='left').pack(anchor='w')
        tk.Label(f, text='  Red  = left / right (X)\n  Blue = top / bottom (Y)',
                 justify='left', font=('Courier', 8), fg='#666').pack(
            anchor='w', pady=(2, 0))
        tk.Button(f, text='Reset Boundaries', command=self._reset_bounds).pack(
            fill='x', pady=(5, 0))
        tk.Checkbutton(f, text='Lock axes  (hide lines, click anywhere)',
                       variable=self.axes_locked,
                       command=self._redraw).pack(anchor='w', pady=(4, 0))

        # Traces
        f = ttk.LabelFrame(ctrl, text='Traces  (click to switch)', padding=4)
        f.pack(fill='x', pady=(0, 6))
        # Listbox — click any row to make that trace active
        lbf = tk.Frame(f)
        lbf.pack(fill='x')
        self.trace_listbox = tk.Listbox(lbf, height=5, selectmode=tk.SINGLE,
                                        exportselection=False, font=('Courier', 9))
        lbsb = tk.Scrollbar(lbf, command=self.trace_listbox.yview)
        self.trace_listbox.configure(yscrollcommand=lbsb.set)
        self.trace_listbox.pack(side='left', fill='x', expand=True)
        lbsb.pack(side='right', fill='y')
        self.trace_listbox.bind('<<ListboxSelect>>', self._on_trace_select)

        row2 = tk.Frame(f)
        row2.pack(fill='x', pady=(4, 0))
        tk.Button(row2, text='+ Add Trace',    command=self._add_trace).pack(side='left')
        tk.Button(row2, text='✕ Delete Trace', command=self._del_trace).pack(
            side='left', padx=(4, 0))

        # Name entry for renaming
        row3 = tk.Frame(f)
        row3.pack(fill='x', pady=(4, 0))
        tk.Label(row3, text='Rename:', anchor='w', width=7).pack(side='left')
        self.rename_var = tk.StringVar()
        tk.Entry(row3, textvariable=self.rename_var, width=14).pack(
            side='left', fill='x', expand=True)
        tk.Button(row3, text='✓', width=2, command=self._rename_trace).pack(side='left')

        # Points list
        f = ttk.LabelFrame(ctrl, text='Points  (active trace)', padding=4)
        f.pack(fill='both', expand=True, pady=(0, 6))
        self.pts_list = tk.Listbox(f, height=10, font=('Courier', 9))
        sb = tk.Scrollbar(f, command=self.pts_list.yview)
        self.pts_list.configure(yscrollcommand=sb.set)
        self.pts_list.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        tk.Button(f, text='Undo Last  (Ctrl+Z)', command=self.undo_point).pack(
            fill='x', pady=(4, 0))
        tk.Button(f, text='Clear Active Trace',  command=self._clear_trace).pack(
            fill='x', pady=(2, 0))

        # Status / coords
        self.status_var = tk.StringVar(value='Paste or open an image to begin.')
        tk.Label(ctrl, textvariable=self.status_var, wraplength=270,
                 justify='left', fg='#555').pack(anchor='w', pady=(4, 0))
        self.coord_var = tk.StringVar()
        tk.Label(ctrl, textvariable=self.coord_var, font=('Courier', 9),
                 fg='steelblue').pack(anchor='w')

        # Export
        f = ttk.LabelFrame(ctrl, text='Export', padding=4)
        f.pack(fill='x', pady=(6, 0))
        tk.Button(f, text='Save CSV…', command=self.save_csv,
                  bg='#2a6e2a', fg='white', activebackground='#3a9e3a').pack(fill='x')

    # ------------------------------------------------------------------ coord math

    def _canvas_to_data(self, cx, cy):
        ox, oy = self.img_offset
        bx, by = cx - ox, cy - oy
        L, R, T, B = (self.bounds['left'], self.bounds['right'],
                      self.bounds['top'],  self.bounds['bottom'])
        t = (bx - L) / (R - L) if R != L else 0.0
        # s=0 at bottom (y_min), s=1 at top (y_max) — pixel y is inverted
        s = (by - B) / (T - B) if T != B else 0.0

        xmin, xmax = self.x_min.get(), self.x_max.get()
        ymin, ymax = self.y_min.get(), self.y_max.get()

        if self.x_log.get() and xmin > 0 and xmax > 0:
            dx = math.exp(math.log(xmin) + t * (math.log(xmax) - math.log(xmin)))
        else:
            dx = xmin + t * (xmax - xmin)

        if self.y_log.get() and ymin > 0 and ymax > 0:
            dy = math.exp(math.log(ymin) + s * (math.log(ymax) - math.log(ymin)))
        else:
            dy = ymin + s * (ymax - ymin)

        return dx, dy

    def _data_to_canvas(self, dx, dy):
        ox, oy = self.img_offset
        L, R, T, B = (self.bounds['left'], self.bounds['right'],
                      self.bounds['top'],  self.bounds['bottom'])
        xmin, xmax = self.x_min.get(), self.x_max.get()
        ymin, ymax = self.y_min.get(), self.y_max.get()

        if self.x_log.get() and xmin > 0 and xmax > 0 and dx > 0:
            t = (math.log(dx) - math.log(xmin)) / (math.log(xmax) - math.log(xmin))
        else:
            t = (dx - xmin) / (xmax - xmin) if xmax != xmin else 0

        if self.y_log.get() and ymin > 0 and ymax > 0 and dy > 0:
            s = (math.log(dy) - math.log(ymin)) / (math.log(ymax) - math.log(ymin))
        else:
            s = (dy - ymin) / (ymax - ymin) if ymax != ymin else 0

        cx = L + t * (R - L) + ox
        cy = B - s * (B - T) + oy   # B > T in pixel space
        return cx, cy

    def _hit_bound(self, cx, cy, tol=8):
        if self.axes_locked.get():
            return None
        ox, oy = self.img_offset
        bx, by = cx - ox, cy - oy
        if abs(bx - self.bounds['left'])   < tol: return 'left'
        if abs(bx - self.bounds['right'])  < tol: return 'right'
        if abs(by - self.bounds['top'])    < tol: return 'top'
        if abs(by - self.bounds['bottom']) < tol: return 'bottom'
        return None

    # ------------------------------------------------------------------ canvas events

    def _on_motion(self, event):
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if not self.axes_locked.get():
            hit = self._hit_bound(cx, cy)
            if hit in ('left', 'right'):
                self.canvas.config(cursor='sb_h_double_arrow')
            elif hit in ('top', 'bottom'):
                self.canvas.config(cursor='sb_v_double_arrow')
            else:
                self.canvas.config(cursor='crosshair')
        else:
            self.canvas.config(cursor='crosshair')
        try:
            dx, dy = self._canvas_to_data(cx, cy)
            self.coord_var.set(f'x = {dx:.4g}   y = {dy:.4g}')
        except Exception:
            pass

    def _on_click(self, event):
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        hit = self._hit_bound(cx, cy)
        if hit:
            self.drag_line = hit
        else:
            self._add_point(cx, cy)

    def _on_drag(self, event):
        if not self.drag_line:
            return
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        ox, oy = self.img_offset
        bx, by = int(cx - ox), int(cy - oy)
        if self.drag_line == 'left':
            self.bounds['left']   = bx
        elif self.drag_line == 'right':
            self.bounds['right']  = bx
        elif self.drag_line == 'top':
            self.bounds['top']    = by
        elif self.drag_line == 'bottom':
            self.bounds['bottom'] = by
        self._redraw()

    def _on_release(self, event):
        self.drag_line = None

    # ------------------------------------------------------------------ point ops

    def _add_point(self, cx, cy):
        try:
            dx, dy = self._canvas_to_data(cx, cy)
        except Exception:
            return
        trace = self.active_trace.get()
        if trace not in self.traces:
            self.traces[trace] = []
        self.traces[trace].append((dx, dy))
        self._redraw_points()
        self._update_list()
        self.status_var.set(f"Added ({dx:.4g}, {dy:.4g})  →  '{trace}'")

    def undo_point(self, event=None):
        trace = self.active_trace.get()
        if trace in self.traces and self.traces[trace]:
            self.traces[trace].pop()
            self._redraw_points()
            self._update_list()
            self.status_var.set('Undone last point.')

    def _clear_trace(self):
        trace = self.active_trace.get()
        if trace in self.traces:
            self.traces[trace] = []
            self._redraw_points()
            self._update_list()

    def _add_trace(self):
        n = len(self.traces) + 1
        name = f'trace_{n}'
        while name in self.traces:
            n += 1
            name = f'trace_{n}'
        self.traces[name] = []
        self.active_trace.set(name)
        self._update_trace_combo()

    def _del_trace(self):
        if len(self.traces) <= 1:
            messagebox.showwarning('Delete Trace', 'Cannot delete the only trace.')
            return
        trace = self.active_trace.get()
        del self.traces[trace]
        self.active_trace.set(list(self.traces.keys())[0])
        self._update_trace_combo()
        self._redraw()

    def _rename_trace(self):
        old = self.active_trace.get()
        new = self.rename_var.get().strip()
        if not new or new == old:
            return
        if new in self.traces:
            messagebox.showwarning('Rename', f"'{new}' already exists.")
            return
        # Preserve order
        self.traces = {(new if k == old else k): v for k, v in self.traces.items()}
        self.active_trace.set(new)
        self.rename_var.set('')
        self._update_trace_combo()

    def _on_trace_select(self, event=None):
        sel = self.trace_listbox.curselection()
        if sel:
            name = list(self.traces.keys())[sel[0]]
            self.active_trace.set(name)
            self._update_list()
            self._redraw_points()

    def _update_trace_combo(self):
        keys = list(self.traces.keys())
        self.trace_listbox.delete(0, tk.END)
        active = self.active_trace.get()
        for i, name in enumerate(keys):
            n_pts = len(self.traces[name])
            color_idx = i % len(TRACE_COLORS)
            self.trace_listbox.insert(tk.END, f'[{i+1}] {name}  ({n_pts}pts)')
            # Highlight active trace
            if name == active:
                self.trace_listbox.selection_clear(0, tk.END)
                self.trace_listbox.selection_set(i)
                self.trace_listbox.see(i)
        self._update_list()

    def _update_list(self):
        # Refresh trace listbox
        keys = list(self.traces.keys())
        active = self.active_trace.get()
        self.trace_listbox.delete(0, tk.END)
        for i, name in enumerate(keys):
            n_pts = len(self.traces[name])
            self.trace_listbox.insert(tk.END, f'[{i+1}] {name}  ({n_pts}pts)')
            if name == active:
                self.trace_listbox.selection_clear(0, tk.END)
                self.trace_listbox.selection_set(i)
                self.trace_listbox.see(i)
        # Refresh points list for active trace
        self.pts_list.delete(0, tk.END)
        for i, (x, y) in enumerate(self.traces.get(active, [])):
            self.pts_list.insert(tk.END, f'{i+1:3d}  x={x:.4g}  y={y:.4g}')

    # ------------------------------------------------------------------ draw

    def _redraw(self):
        """Full redraw: boundaries + points."""
        self.canvas.delete('bounds', 'points')
        if not self.axes_locked.get():
            ox, oy = self.img_offset
            L, R, T, B = (self.bounds['left']  + ox, self.bounds['right'] + ox,
                          self.bounds['top']   + oy, self.bounds['bottom']+ oy)
            W = H = 4000
            self.canvas.create_line(L, 0, L, H, fill='#FF5555', width=1,
                                     dash=(8, 4), tags='bounds')
            self.canvas.create_line(R, 0, R, H, fill='#FF5555', width=1,
                                     dash=(8, 4), tags='bounds')
            self.canvas.create_line(0, T, W, T, fill='#5599FF', width=1,
                                     dash=(8, 4), tags='bounds')
            self.canvas.create_line(0, B, W, B, fill='#5599FF', width=1,
                                     dash=(8, 4), tags='bounds')
        self._redraw_points()

    def _redraw_points(self):
        self.canvas.delete('points')
        active = self.active_trace.get()
        for ti, (tname, pts) in enumerate(self.traces.items()):
            color = TRACE_COLORS[ti % len(TRACE_COLORS)]
            is_active = (tname == active)
            r = 5 if is_active else 4
            outline = 'white' if is_active else '#666'
            for (dx, dy) in pts:
                try:
                    px, py = self._data_to_canvas(dx, dy)
                    self.canvas.create_oval(px-r, py-r, px+r, py+r,
                                             fill=color, outline=outline,
                                             width=1, tags='points')
                except Exception:
                    pass

    # ------------------------------------------------------------------ image loading

    def paste_image(self, event=None):
        if not HAS_PIL:
            messagebox.showerror('Error', 'Pillow not installed.\nRun: pip install Pillow')
            return
        try:
            img = ImageGrab.grabclipboard()
            if img is None:
                self.status_var.set('No image found in clipboard.')
                return
            self._load_image(img)
        except Exception as e:
            self.status_var.set(f'Paste failed: {e}')

    def open_image(self):
        if not HAS_PIL:
            messagebox.showerror('Error', 'Pillow not installed.')
            return
        path = filedialog.askopenfilename(
            title='Open Image',
            filetypes=[('Images', '*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp'),
                       ('All files', '*.*')])
        if path:
            try:
                self._load_image(Image.open(path))
            except Exception as e:
                messagebox.showerror('Error', str(e))

    def _load_image(self, img):
        self.image = img.convert('RGB')
        self.photo = ImageTk.PhotoImage(self.image)
        self.canvas.delete('all')
        ox, oy = self.img_offset
        self.canvas.create_image(ox, oy, anchor='nw', image=self.photo, tags='image')
        self.canvas.config(scrollregion=(0, 0,
                                          self.image.width  + ox * 2,
                                          self.image.height + oy * 2))
        self._reset_bounds()
        self.status_var.set(
            f'Image: {self.image.width}×{self.image.height}px\n'
            f'1. Drag red lines → X axis bounds\n'
            f'2. Drag blue lines → Y axis bounds\n'
            f'3. Set axis limits & scale\n'
            f'4. Click to add data points'
        )

    def _reset_bounds(self):
        if self.image:
            w, h = self.image.size
            self.bounds = {
                'left':   int(w * 0.10),
                'right':  int(w * 0.96),
                'top':    int(h * 0.04),
                'bottom': int(h * 0.90),
            }
        else:
            self.bounds = {'left': 100, 'right': 500, 'top': 50, 'bottom': 450}
        self._redraw()

    # ------------------------------------------------------------------ export

    def save_csv(self):
        active_pts = {n: p for n, p in self.traces.items() if p}
        if not active_pts:
            messagebox.showwarning('Save CSV', 'No points to save.')
            return

        path = filedialog.asksaveasfilename(
            title='Save CSV',
            defaultextension='.csv',
            filetypes=[('CSV files', '*.csv'), ('All files', '*.*')],
            initialdir=os.path.join(os.path.dirname(__file__), '..'))
        if not path:
            return

        # Build axis column name: "title (units)" or just title or just units
        def _axis_label(title_var, units_var, fallback):
            t = title_var.get().strip()
            u = units_var.get().strip()
            if t and u:
                return f'{t} ({u})'
            return t or u or fallback

        x_col = _axis_label(self.x_title, self.x_units, 'x')
        y_col = _axis_label(self.y_title, self.y_units, 'y')

        try:
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                names = list(active_pts.keys())
                if len(names) == 1:
                    n = names[0]
                    writer.writerow([f'{x_col}_{n}', f'{y_col}_{n}'])
                    for x, y in sorted(active_pts[n], key=lambda p: p[0]):
                        writer.writerow([f'{x:.6g}', f'{y:.6g}'])
                else:
                    header = []
                    for n in names:
                        header += [f'{x_col}_{n}', f'{y_col}_{n}']
                    writer.writerow(header)
                    max_len = max(len(p) for p in active_pts.values())
                    sorted_pts = {n: sorted(p, key=lambda pt: pt[0])
                                  for n, p in active_pts.items()}
                    for i in range(max_len):
                        row = []
                        for n in names:
                            pts = sorted_pts[n]
                            if i < len(pts):
                                row += [f'{pts[i][0]:.6g}', f'{pts[i][1]:.6g}']
                            else:
                                row += ['', '']
                        writer.writerow(row)
            self.status_var.set(f'Saved: {os.path.basename(path)}')
        except Exception as e:
            messagebox.showerror('Save Error', str(e))


# --------------------------------------------------------------------------

if __name__ == '__main__':
    if not HAS_PIL:
        print("ERROR: Pillow is required.  Run:  pip install Pillow")
        raise SystemExit(1)
    root = tk.Tk()
    root.geometry('1150x720')
    root.minsize(800, 500)
    app = ChartDigitizer(root)
    root.mainloop()
