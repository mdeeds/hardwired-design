/**
 * Signal Processor for XY Oscilloscope & Pitch-Synchronous FFT
 * Handles routing, sine/saw generation, delayed channel computation,
 * wavelength resampling, and Cooley-Tukey Radix-2 FFT.
 */
class ScopeProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 32768; // Holds down to 20Hz at 44.1kHz (17640 samples)
    this.bufferL = new Float32Array(this.bufferSize);
    this.bufferR = new Float32Array(this.bufferSize);
    this.bufferSine = new Float32Array(this.bufferSize);
    this.bufferSaw = new Float32Array(this.bufferSize);
    this.bufferLeftDelay = new Float32Array(this.bufferSize);
    this.bufferRightDelay = new Float32Array(this.bufferSize);
    this.writePtr = 0;
    this.frequency = 440;
    this.frameCounter = 0;
    this.selectY = 'left'; // Default source for FFT

    this.port.onmessage = (e) => {
      if (e.data && e.data.type === 'setSelectY') {
        this.selectY = e.data.value;
      }
    };

    // Precompute sine and cosine tables for 1024-point FFT twiddle factors
    this.fftCosTable = new Float32Array(512);
    this.fftSinTable = new Float32Array(512);
    for (let i = 0; i < 512; i++) {
      this.fftCosTable[i] = Math.cos(-2 * Math.PI * i / 1024);
      this.fftSinTable[i] = Math.sin(-2 * Math.PI * i / 1024);
    }
  }

  static get parameterDescriptors() {
    return [{ name: 'frequency', defaultValue: 440 }];
  }

  resampleRingBuffer(ringBuffer, writePtr, M, targetLength) {
    const output = new Float32Array(targetLength);
    const bufferSize = ringBuffer.length;
    for (let i = 0; i < targetLength; i++) {
      const rawIndex = i * (M - 1) / (targetLength - 1);
      const indexLow = Math.floor(rawIndex);
      const indexHigh = Math.min(M - 1, indexLow + 1);
      const weight = rawIndex - indexLow;

      let readIdxLow = (writePtr - M + indexLow) % bufferSize;
      if (readIdxLow < 0) readIdxLow += bufferSize;

      let readIdxHigh = (writePtr - M + indexHigh) % bufferSize;
      if (readIdxHigh < 0) readIdxHigh += bufferSize;

      output[i] = (1 - weight) * ringBuffer[readIdxLow] + weight * ringBuffer[readIdxHigh];
    }
    return output;
  }

  extractRecentHistory(ringBuffer, size) {
    const output = new Float32Array(size);
    const bufferSize = ringBuffer.length;
    for (let i = 0; i < size; i++) {
      let readIdx = (this.writePtr - size + i) % bufferSize;
      if (readIdx < 0) readIdx += bufferSize;
      output[i] = ringBuffer[readIdx];
    }
    return output;
  }

  fft1024(realInput) {
    const N = 1024;
    const real = new Float32Array(realInput);
    const imag = new Float32Array(N);

    // Bit-reversal permutation
    let i = 0;
    for (let j = 1; j < N - 1; j++) {
      let bit = N >> 1;
      while (i & bit) {
        i ^= bit;
        bit >>= 1;
      }
      i ^= bit;
      if (j < i) {
        let temp = real[j];
        real[j] = real[i];
        real[i] = temp;
      }
    }

    // Cooley-Tukey decimation-in-time
    for (let size = 2; size <= N; size *= 2) {
      const halfSize = size / 2;
      const tabStep = N / size;
      for (let step = 0; step < N; step += size) {
        for (let j = step, k = 0; j < step + halfSize; j++, k += tabStep) {
          const wr = this.fftCosTable[k];
          const wi = this.fftSinTable[k];
          
          const tr = real[j + halfSize] * wr - imag[j + halfSize] * wi;
          const ti = real[j + halfSize] * wi + imag[j + halfSize] * wr;
          
          real[j + halfSize] = real[j] - tr;
          imag[j + halfSize] = imag[j] - ti;
          real[j] += tr;
          imag[j] += ti;
        }
      }
    }

    // Compute magnitudes (symmetry means we only need N/2)
    const magnitudes = new Float32Array(N / 2);
    for (let i = 0; i < N / 2; i++) {
      magnitudes[i] = Math.sqrt(real[i] * real[i] + imag[i] * imag[i]) / N;
    }
    return magnitudes;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];     // Mic input (usually 1 or 2 channels)
    const refSine = inputs[1];   // Sine oscillator (input 1)
    const refSaw = inputs[2];    // Saw oscillator (input 2)

    if (parameters.frequency && parameters.frequency.length > 0) {
      const freqVal = parameters.frequency[0];
      if (freqVal && !isNaN(freqVal) && freqVal > 0) {
        this.frequency = freqVal;
      }
    }
    const currentFreq = (this.frequency && !isNaN(this.frequency) && this.frequency > 0) ? this.frequency : 440;

    const frameSize = (input && input[0]) ? input[0].length : 128;

    const chanL = (input && input[0]) ? input[0] : new Float32Array(frameSize);
    const chanR = (input && input.length > 1) ? input[1] : chanL;
    const sineVal = (refSine && refSine[0]) ? refSine[0] : new Float32Array(frameSize);
    const sawVal = (refSaw && refSaw[0]) ? refSaw[0] : new Float32Array(frameSize);

    const delaySamples = Math.round(sampleRate / (4 * currentFreq));

    // Write to ring buffers
    for (let i = 0; i < frameSize; i++) {
      this.bufferL[this.writePtr] = chanL[i];
      this.bufferR[this.writePtr] = chanR[i];
      this.bufferSine[this.writePtr] = sineVal[i];
      this.bufferSaw[this.writePtr] = sawVal[i];

      // Calculate delayed samples on the fly
      let delayReadIdx = (this.writePtr - delaySamples) % this.bufferSize;
      if (delayReadIdx < 0) delayReadIdx += this.bufferSize;

      this.bufferLeftDelay[this.writePtr] = this.bufferL[delayReadIdx];
      this.bufferRightDelay[this.writePtr] = this.bufferR[delayReadIdx];

      this.writePtr = (this.writePtr + 1) % this.bufferSize;
    }

    // Throttle messages to the main thread
    this.frameCounter++;
    if (this.frameCounter >= 4) {
      // 1. Get the source buffer for FFT
      let fftSourceBuffer = this.bufferL;
      if (this.selectY === 'right') fftSourceBuffer = this.bufferR;
      else if (this.selectY === 'sine') fftSourceBuffer = this.bufferSine;
      else if (this.selectY === 'saw') fftSourceBuffer = this.bufferSaw;
      else if (this.selectY === 'leftDelay') fftSourceBuffer = this.bufferLeftDelay;
      else if (this.selectY === 'rightDelay') fftSourceBuffer = this.bufferRightDelay;

      // 2. Determine sample length for exactly 8 wavelengths
      // Limit M to bufferSize - 1, and ensure a minimum of 10 samples
      const M = Math.min(this.bufferSize - 1, Math.max(10, Math.round(8 * sampleRate / currentFreq)));

      // 3. Resample to 1024 samples
      const fftInput = this.resampleRingBuffer(fftSourceBuffer, this.writePtr, M, 1024);

      // 4. Run Cooley-Tukey 1024-Point FFT
      const fftMagnitudes = this.fft1024(fftInput);

      const left       = this.extractRecentHistory(this.bufferL, 2048);
      const right      = this.extractRecentHistory(this.bufferR, 2048);
      const sine       = this.extractRecentHistory(this.bufferSine, 2048);
      const saw        = this.extractRecentHistory(this.bufferSaw, 2048);
      const leftDelay  = this.extractRecentHistory(this.bufferLeftDelay, 2048);
      const rightDelay = this.extractRecentHistory(this.bufferRightDelay, 2048);

      // Post data back to main thread using transferable ArrayBuffers
      // to avoid the structured-clone overhead / silent drop of Float32Arrays
      this.port.postMessage({
        xyData: {
          left: left, right: right, sine: sine, saw: saw,
          leftDelay: leftDelay, rightDelay: rightDelay
        },
        fftMagnitudes: fftMagnitudes
      }, [
        left.buffer, right.buffer, sine.buffer, saw.buffer,
        leftDelay.buffer, rightDelay.buffer, fftMagnitudes.buffer
      ]);
      this.frameCounter = 0;
    }

    // Pass through audio if needed (usually muted for scope)
    if (outputs[0]) {
      for (let i = 0; i < outputs[0].length; i++) {
        outputs[0][i].fill(0);
      }
    }

    return true;
  }
}

registerProcessor('scope-processor', ScopeProcessor);