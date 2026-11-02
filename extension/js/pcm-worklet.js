/**
 * AudioWorklet that downsamples the captured tab audio to 16 kHz mono PCM16.
 * Runs on the audio thread, so it must stay allocation-light.
 */
class BspCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    this.targetRate = opts.targetRate || 16000;
    this.chunkSamples = Math.max(160, Math.round(((opts.chunkMs || 100) * this.targetRate) / 1000));
    this.step = this.targetRate / sampleRate;
    this.phase = 0;
    this.prev = 0;
    this.lp = 0;
    this.alpha = 1 - Math.exp(-2 * Math.PI * Math.min(7000, this.targetRate * 0.45) / sampleRate);
    this.out = new Float32Array(this.chunkSamples);
    this.n = 0;
  }

  push(v) {
    this.out[this.n++] = v;
    if (this.n >= this.chunkSamples) this.flush();
  }

  flush() {
    const n = this.n;
    if (!n) return;
    const pcm = new Int16Array(n);
    for (let i = 0; i < n; i++) {
      let v = this.out[i];
      v = v < -1 ? -1 : v > 1 ? 1 : v;
      pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
    }
    this.n = 0;
    this.port.postMessage({ pcm: pcm, rate: this.targetRate, samples: n }, [pcm.buffer]);
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input.length || !input[0]) return true;
    const ch = input[0];
    for (let i = 0; i < ch.length; i++) {
      const raw = ch[i];
      this.lp += this.alpha * (raw - this.lp);
      this.phase += this.step;
      while (this.phase >= 1) {
        this.phase -= 1;
        const frac = this.phase / this.step;
        this.push(this.prev + (this.lp - this.prev) * (1 - frac));
      }
      this.prev = this.lp;
    }
    return true;
  }
}

registerProcessor('bsp-capture', BspCaptureProcessor);
