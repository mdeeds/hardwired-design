const KEY_MAP = {
  // Octave 3 (z row)
  'z': 48, 's': 49, 'x': 50, 'd': 51, 'c': 52, 'v': 53,
  'g': 54, 'b': 55, 'h': 56, 'n': 57, 'j': 58, 'm': 59,
  // Octave 4 (q row)
  'q': 60, '2': 61, 'w': 62, '3': 63, 'e': 64, 'r': 65,
  '5': 66, 't': 67, '6': 68, 'y': 69, '7': 70, 'u': 71, 'i': 72
};

class OscilloscopeApp {
  constructor() {
    this.canvas = document.getElementById('scopeCanvas');
    this.ctx = this.canvas.getContext('2d');
    this.fftCanvas = document.getElementById('fftCanvas');
    this.fftCtx = this.fftCanvas.getContext('2d');
    this.selectX = document.getElementById('selectX');
    this.selectY = document.getElementById('selectY');
    this.deviceSelect = document.getElementById('deviceSelect');

    this.audioCtx = null;
    this.currentStream = null;
    this.micSource = null;
    this.oscSine = null;
    this.oscSaw = null;
    this.workletNode = null;

    this.currentFreq = 440;
    this.latestData = null;
    this.latestFFT = null;
    this.isInitialized = false;

    this.noteDisplay = document.getElementById('noteDisplay');
    this.freqDisplay = document.getElementById('freqDisplay');
    this.updateFreqDisplay(69, 440);

    this.resize();
    window.addEventListener('resize', () => this.resize());
    window.addEventListener('keydown', (e) => this.handleKeyDown(e));

    if (this.selectY) {
      this.selectY.addEventListener('change', () => {
        if (this.isInitialized && this.workletNode) {
          this.workletNode.port.postMessage({ type: 'setSelectY', value: this.selectY.value });
        }
      });
    }

    // Start context on first interaction
    document.body.addEventListener('click', () => this.initAudio(), { once: true });

    if (this.deviceSelect) {
      this.deviceSelect.addEventListener('change', () => {
        if (this.isInitialized) this.setupDevice(this.deviceSelect.value);
      });
    }

    // Handle hardware changes (unplugging/plugging devices)
    navigator.mediaDevices.ondevicechange = () => {
      if (this.isInitialized) this.updateDeviceList();
    };

    this.draw = this.draw.bind(this);
    requestAnimationFrame(this.draw);
  }

  resize() {
    this.canvas.width = 600;
    this.canvas.height = 600;
    if (this.fftCanvas) {
      this.fftCanvas.width = 600;
      this.fftCanvas.height = 600;
    }
  }

  async initAudio() {
    this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    await this.audioCtx.resume();

    // Create Reference Oscillators once
    this.oscSine = this.audioCtx.createOscillator();
    this.oscSine.type = 'sine';
    this.oscSine.frequency.setValueAtTime(this.currentFreq, this.audioCtx.currentTime);

    this.oscSaw = this.audioCtx.createOscillator();
    this.oscSaw.type = 'sawtooth';
    this.oscSaw.frequency.setValueAtTime(this.currentFreq, this.audioCtx.currentTime);

    // Load and create Worklet
    await this.audioCtx.audioWorklet.addModule('processor.js?t=' + Date.now());
    this.workletNode = new AudioWorkletNode(this.audioCtx, 'scope-processor', {
      numberOfInputs: 3, // 0: Mic, 1: Sine, 2: Saw
      numberOfOutputs: 1
    });

    this.workletNode.port.onmessage = (e) => {
      if (e.data) {
        this.latestData = e.data.xyData;
        this.latestFFT = e.data.fftMagnitudes;
      }
    };

    // Connect reference oscillators to worklet
    this.oscSine.connect(this.workletNode, 0, 1);
    this.oscSaw.connect(this.workletNode, 0, 2);

    // Send initial selectY to worklet
    this.workletNode.port.postMessage({ type: 'setSelectY', value: this.selectY.value });

    // Setup initial device
    await this.setupDevice();
    await this.updateDeviceList();

    // Worklet to destination (muted)
    const gain = this.audioCtx.createGain();
    gain.gain.value = 0;
    this.workletNode.connect(gain).connect(this.audioCtx.destination);

    this.oscSine.start();
    this.oscSaw.start();
    this.isInitialized = true;

    console.log("Audio Initialized");
  }

  async setupDevice(deviceId = null) {
    try {
      // Stop previous stream if switching
      if (this.currentStream) {
        this.currentStream.getTracks().forEach(track => track.stop());
      }
      if (this.micSource) {
        this.micSource.disconnect();
      }

      const constraints = {
        audio: {
          deviceId: deviceId ? { exact: deviceId } : undefined,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
          channelCount: 2
        }
      };

      this.currentStream = await navigator.mediaDevices.getUserMedia(constraints);

      const audioTrack = this.currentStream.getAudioTracks()[0];
      console.log("Active Device:", audioTrack.label);

      this.micSource = this.audioCtx.createMediaStreamSource(this.currentStream);
      this.micSource.connect(this.workletNode, 0, 0);
    } catch (err) {
      console.error("Device Setup Error:", err);
      alert("Could not connect to the selected audio device.");
    }
  }

  async updateDeviceList() {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const audioInputs = devices.filter(d => d.kind === 'audioinput');

    if (!this.deviceSelect) return;

    // Save current selection to restore it
    const currentId = this.deviceSelect.value;
    this.deviceSelect.innerHTML = '';

    audioInputs.forEach(device => {
      const option = document.createElement('option');
      option.value = device.deviceId;
      option.text = device.label || `Microphone ${this.deviceSelect.length + 1}`;
      this.deviceSelect.appendChild(option);
    });

    // Synchronize selection with the actual active track settings
    const activeTrack = this.currentStream?.getAudioTracks()[0];
    const activeId = activeTrack?.getSettings()?.deviceId || currentId;

    if (activeId) this.deviceSelect.value = activeId;
  }

  handleKeyDown(e) {
    if (e.key === '^' || (e.key === '6' && e.shiftKey)) {
      const freq = 60;
      this.currentFreq = freq;
      const midiNote = 69 + 12 * Math.log2(freq / 440);
      this.updateFreqDisplay(midiNote, freq);
      if (this.audioCtx) {
        const now = this.audioCtx.currentTime;
        this.oscSine.frequency.setTargetAtTime(freq, now, 0.01);
        this.oscSaw.frequency.setTargetAtTime(freq, now, 0.01);

        // Update worklet param for delay calc
        const freqParam = this.workletNode.parameters.get('frequency');
        freqParam.setTargetAtTime(freq, now, 0.01);
      }
      return;
    }

    const midiNote = KEY_MAP[e.key.toLowerCase()];
    if (midiNote) {
      const freq = 440 * Math.pow(2, (midiNote - 69) / 12);
      this.currentFreq = freq;
      this.updateFreqDisplay(midiNote, freq);
      if (this.audioCtx) {
        const now = this.audioCtx.currentTime;
        this.oscSine.frequency.setTargetAtTime(freq, now, 0.01);
        this.oscSaw.frequency.setTargetAtTime(freq, now, 0.01);

        // Update worklet param for delay calc
        const freqParam = this.workletNode.parameters.get('frequency');
        freqParam.setTargetAtTime(freq, now, 0.01);
      }
    }
  }

  updateFreqDisplay(midiNote, freq) {
    if (this.noteDisplay && this.freqDisplay) {
      const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
      const roundedMidi = Math.round(midiNote);
      const noteName = NOTE_NAMES[roundedMidi % 12];
      const octave = Math.floor(roundedMidi / 12) - 1;
      this.noteDisplay.textContent = `${noteName}${octave}`;
      this.freqDisplay.textContent = `${freq.toFixed(2)} Hz`;
    }
  }

  draw() {
    requestAnimationFrame(this.draw);

    // 1. Draw XY Oscilloscope
    this.ctx.fillStyle = 'rgba(0, 0, 0, 0.2)';
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    this.drawGrid();

    if (this.latestData) {
      const srcX = this.latestData[this.selectX.value];
      const srcY = this.latestData[this.selectY.value];

      if (srcX && srcY) {
        this.ctx.beginPath();
        this.ctx.strokeStyle = '#00ff41';
        this.ctx.lineWidth = 2;
        this.ctx.shadowBlur = 8;
        this.ctx.shadowColor = '#00ff41';

        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height / 2;
        const scale = 250; // Amplitude scaling

        const isSawX = this.selectX.value === 'saw';
        for (let i = 0; i < srcX.length; i++) {
          const x = centerX + srcX[i] * scale;
          const y = centerY - srcY[i] * scale;

          if (i === 0 || (isSawX && (srcX[i] - srcX[i - 1] < -1.0))) {
            this.ctx.moveTo(x, y);
          } else {
            this.ctx.lineTo(x, y);
          }
        }
        this.ctx.stroke();
        this.ctx.shadowBlur = 0;
      }
    }

    // 2. Draw FFT
    this.drawFFT();
  }

  drawGrid() {
    this.ctx.strokeStyle = '#113311';
    this.ctx.lineWidth = 1;
    const step = 60;

    // Vertical lines
    for (let x = 0; x <= this.canvas.width; x += step) {
      this.ctx.beginPath();
      this.ctx.moveTo(x, 0);
      this.ctx.lineTo(x, this.canvas.height);
      this.ctx.stroke();
    }
    // Horizontal lines
    for (let y = 0; y <= this.canvas.height; y += step) {
      this.ctx.beginPath();
      this.ctx.moveTo(0, y);
      this.ctx.lineTo(this.canvas.width, y);
      this.ctx.stroke();
    }

    // Axis lines
    this.ctx.strokeStyle = '#225522';
    this.ctx.lineWidth = 2;
    this.ctx.beginPath();
    this.ctx.moveTo(this.canvas.width / 2, 0);
    this.ctx.lineTo(this.canvas.width / 2, this.canvas.height);
    this.ctx.moveTo(0, this.canvas.height / 2);
    this.ctx.lineTo(this.canvas.width, this.canvas.height / 2);
    this.ctx.stroke();
  }

  drawFFT() {
    if (!this.fftCtx) return;

    // Clear canvas fully each frame
    this.fftCtx.fillStyle = '#000';
    this.fftCtx.fillRect(0, 0, this.fftCanvas.width, this.fftCanvas.height);
    this.drawFFTGrid();

    if (!this.latestFFT) return;

    const numBins = 128; // Display first 16 harmonics (128 / 8 = 16)
    const baseline = this.fftCanvas.height - 30;
    const plotHeight = baseline - 10; // available height for spectrum

    // Build point list once
    const points = [];
    for (let k = 0; k < numBins; k++) {
      const magnitude = this.latestFFT[k] || 0;
      const yVal = Math.min(1.0, magnitude * 4.0); // scale: 0.25 full-scale = top of chart
      const x = (k / (numBins - 1)) * this.fftCanvas.width;
      const y = baseline - yVal * plotHeight;
      points.push({ x, y });
    }

    // Draw filled area first (so stroke appears on top)
    const grad = this.fftCtx.createLinearGradient(0, 0, 0, baseline);
    grad.addColorStop(0, 'rgba(0, 255, 65, 0.25)');
    grad.addColorStop(1, 'rgba(0, 255, 65, 0.0)');
    this.fftCtx.beginPath();
    this.fftCtx.moveTo(points[0].x, baseline);
    for (const p of points) this.fftCtx.lineTo(p.x, p.y);
    this.fftCtx.lineTo(points[points.length - 1].x, baseline);
    this.fftCtx.closePath();
    this.fftCtx.fillStyle = grad;
    this.fftCtx.fill();

    // Draw glowing stroke on top
    this.fftCtx.beginPath();
    this.fftCtx.strokeStyle = '#00ff41';
    this.fftCtx.lineWidth = 2;
    this.fftCtx.shadowBlur = 8;
    this.fftCtx.shadowColor = '#00ff41';
    this.fftCtx.moveTo(points[0].x, points[0].y);
    for (let k = 1; k < points.length; k++) this.fftCtx.lineTo(points[k].x, points[k].y);
    this.fftCtx.stroke();
    this.fftCtx.shadowBlur = 0;
  }

  drawFFTGrid() {
    this.fftCtx.strokeStyle = '#113311';
    this.fftCtx.lineWidth = 1;

    // Harmonic markers (vertical lines every 8 bins, fundamental at bin 8)
    const numHarmonics = 16;
    const spacingX = this.fftCanvas.width / numHarmonics;
    
    for (let i = 1; i < numHarmonics; i++) {
      const x = i * spacingX;
      this.fftCtx.beginPath();
      this.fftCtx.moveTo(x, 0);
      this.fftCtx.lineTo(x, this.fftCanvas.height - 30);
      this.fftCtx.stroke();

      this.fftCtx.fillStyle = '#225522';
      this.fftCtx.font = '10px Courier New';
      this.fftCtx.textAlign = 'center';
      this.fftCtx.fillText(`H${i}`, x, this.fftCanvas.height - 15);
    }

    // Amplitude grid (horizontal lines)
    const numLevels = 10;
    const spacingY = (this.fftCanvas.height - 30) / numLevels;
    for (let i = 1; i <= numLevels; i++) {
      const y = (this.fftCanvas.height - 30) - i * spacingY;
      this.fftCtx.beginPath();
      this.fftCtx.moveTo(0, y);
      this.fftCtx.lineTo(this.fftCanvas.width, y);
      this.fftCtx.stroke();
    }

    // Baseline axis
    this.fftCtx.strokeStyle = '#225522';
    this.fftCtx.lineWidth = 2;
    this.fftCtx.beginPath();
    this.fftCtx.moveTo(0, this.fftCanvas.height - 30);
    this.fftCtx.lineTo(this.fftCanvas.width, this.fftCanvas.height - 30);
    this.fftCtx.stroke();
  }
}

window.onload = () => new OscilloscopeApp();
