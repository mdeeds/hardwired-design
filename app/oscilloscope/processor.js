/**
 * Signal Processor for XY Oscilloscope
 * Handles routing, sine/saw generation, and wavelength delays.
 */
class ScopeProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 8192;
    this.bufferL = new Float32Array(this.bufferSize);
    this.bufferR = new Float32Array(this.bufferSize);
    this.writePtr = 0;
    this.frequency = 440;
    this.frameCounter = 0;
  }

  static get parameterDescriptors() {
    return [{ name: 'frequency', defaultValue: 440 }];
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];     // Mic input (usually 1 or 2 channels)
    const refSine = inputs[1];   // Sine oscillator (input 1)
    const refSaw = inputs[2];    // Saw oscillator (input 2)

    this.frequency = parameters.frequency[0];
    const frameSize = (input && input[0]) ? input[0].length : 128;

    // Prepare data object with default silent buffers
    const data = {
      left: new Float32Array(frameSize),
      right: new Float32Array(frameSize),
      sine: (refSine && refSine[0]) ? new Float32Array(refSine[0]) : new Float32Array(frameSize),
      saw: (refSaw && refSaw[0]) ? new Float32Array(refSaw[0]) : new Float32Array(frameSize),
      leftDelay: new Float32Array(frameSize),
      rightDelay: new Float32Array(frameSize)
    };

    if (input && input[0]) {
      const chanL = input[0];
      const chanR = input.length > 1 ? input[1] : chanL;
      data.left.set(chanL);
      data.right.set(chanR);

      // Write to ring buffers
      for (let i = 0; i < chanL.length; i++) {
        this.bufferL[this.writePtr] = chanL[i];
        this.bufferR[this.writePtr] = chanR[i];
        this.writePtr = (this.writePtr + 1) % this.bufferSize;
      }
    }

    // Calculate 1/4 wavelength delay and extract samples
    const delaySamples = Math.round(sampleRate / (4 * this.frequency));
    for (let i = 0; i < frameSize; i++) {
      let readIdx = (this.writePtr - frameSize + i - delaySamples) % this.bufferSize;
      if (readIdx < 0) readIdx += this.bufferSize;
      data.leftDelay[i] = this.bufferL[readIdx];
      data.rightDelay[i] = this.bufferR[readIdx];
    }

    // Throttle messages to the main thread
    this.frameCounter++;
    if (this.frameCounter >= 4) {
      this.port.postMessage(data);
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