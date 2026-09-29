/* The counter's alarm sound - the same one the Odoo counter makes.

   A line-for-line port of `Alarm` in sales_automation_store's
   static/src/store_screen.js, so the console and Odoo ring identically: a
   square wave (harsh on purpose - it has to be heard over a shop) alternating
   1000 Hz and 1400 Hz, 0.35 s on / 0.15 s off, for `seconds`. The pause
   between rings, and how long each ring lasts, are the counter's Delivery
   Settings, applied by the caller (useCounterAlarm in AdminCounter.jsx).

   Web Audio, no file: nothing to load or fail, no codec to be missing. A
   browser only lets it start inside a click, which is what arm() is for. */

export class Alarm {
  constructor() {
    this.ctx = null;
    this.armed = false;
    this.timer = null;
  }

  async arm() {
    if (this.armed) return true;
    const Ctx = typeof window !== "undefined" && (window.AudioContext || window.webkitAudioContext);
    if (!Ctx) return false;
    this.ctx = this.ctx || new Ctx();
    try { await this.ctx.resume(); } catch { /* the state below says whether it worked */ }
    this.armed = this.ctx.state === "running";
    return this.armed;
  }

  /* One loud tone. */
  tone(freq, at, length) {
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = "square";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(0.8, at + 0.01);
    gain.gain.setValueAtTime(0.8, at + length - 0.03);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + length);
    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start(at);
    osc.stop(at + length + 0.02);
  }

  /* Ring for `seconds`: two tones alternating, the cadence of a phone that
     wants answering. Scheduled a second at a time so stop() really stops. */
  ring(seconds) {
    this.stop();
    if (!this.armed || !this.ctx) return;
    const step = 0.5;
    const len = 0.35;
    const end = this.ctx.currentTime + seconds;
    let next = this.ctx.currentTime + 0.05;
    let hi = false;
    const schedule = () => {
      const horizon = this.ctx.currentTime + 1.0;
      while (next < horizon && next < end) {
        this.tone(hi ? 1400 : 1000, next, len);
        hi = !hi;
        next += step;
      }
      if (next >= end) this.stop();
    };
    schedule();
    this.timer = setInterval(schedule, 400);
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
}
