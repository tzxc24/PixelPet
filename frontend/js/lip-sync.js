/* Read a short PCM window aligned to the browser's playback clock. */
(() => {
  const closed = Object.freeze({rms: 0, mouth: 'closed'});

  class PixelPetLipSync {
    static fromWav(buffer) {
      const view = new DataView(buffer);
      const tag = offset => view.getUint32(offset, false);
      if (view.byteLength < 12 || tag(0) !== 0x52494646 || tag(8) !== 0x57415645) return null;
      let format;
      let samples;
      for (let chunk = 12; chunk + 8 <= view.byteLength;) {
        const length = view.getUint32(chunk + 4, true);
        const start = chunk + 8;
        if (start + length > view.byteLength) return null;
        if (tag(chunk) === 0x666d7420 && length >= 16) {
          const channels = view.getUint16(start + 2, true);
          const rate = view.getUint32(start + 4, true);
          if (view.getUint16(start, true) !== 1 || channels < 1 || channels > 2 ||
              rate < 8000 || rate > 96000 || view.getUint16(start + 14, true) !== 16 ||
              view.getUint16(start + 12, true) !== channels * 2) return null;
          format = {channels, rate};
        }
        if (tag(chunk) === 0x64617461) samples = {start, length};
        if (format && samples) return new PixelPetLipSync(view, format, samples);
        chunk = start + length + (length % 2);
      }
      return null;
    }

    constructor(view, {channels, rate}, {start, length}) {
      this.view = view;
      this.rate = rate;
      this.channels = channels;
      this.start = start;
      this.frames = Math.floor(length / (channels * 2));
    }

    sample(seconds) {
      if (!Number.isFinite(seconds) || seconds < 0) return closed;
      const from = Math.floor(seconds * this.rate);
      const to = Math.min(this.frames, from + Math.round(this.rate * .025));
      if (from >= to) return closed;
      let energy = 0;
      for (let frame = from; frame < to; frame++) {
        for (let channel = 0; channel < this.channels; channel++) {
          const sample = this.view.getInt16(this.start + 2 * (frame * this.channels + channel), true) / 32768;
          energy += sample * sample;
        }
      }
      const rms = Math.sqrt(energy / ((to - from) * this.channels));
      return {rms, mouth: rms < .012 ? 'closed' : rms < .09 ? 'small' : 'large'};
    }
  }

  window.PixelPetLipSync = PixelPetLipSync;
})();
