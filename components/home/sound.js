/* ==========================================================================
   369 Mart — UI sound engine (Web Audio, no files)
   Browsers only let a page play sound after the user has tapped or typed.
   The receipt prints on its own a moment after payment, so a fresh
   AudioContext created then stays "suspended" = silence. Fix: one shared
   context, unlocked on the very first tap anywhere in the app (the Pay
   button, the cart, anything) by installAudioUnlock(); the receipt then
   reuses the already-running context.
   ========================================================================== */

let ctx = null;
let master = null;
let noiseBuf = null;
const listeners = new Set();

export function getAudio() {
  if (typeof window === "undefined") return null;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return null;
  if (!ctx) {
    ctx = new AC();
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14; comp.knee.value = 8; comp.ratio.value = 4; comp.attack.value = 0.003; comp.release.value = 0.12;
    master = ctx.createGain();
    master.gain.value = 1;
    master.connect(comp).connect(ctx.destination);
    ctx.onstatechange = () => listeners.forEach((f) => f(ctx.state));
  }
  return ctx;
}

export const audioRunning = () => !!ctx && ctx.state === "running";
export const onAudioState = (f) => { listeners.add(f); return () => listeners.delete(f); };

/* call inside a user gesture (click / tap / key) */
export function unlockAudio() {
  const ac = getAudio();
  if (!ac) return Promise.resolve(false);
  if (ac.state === "running") return Promise.resolve(true);
  /* a silent blip also unlocks iOS Safari */
  try {
    const b = ac.createBuffer(1, 1, 22050), s = ac.createBufferSource();
    s.buffer = b; s.connect(ac.destination); s.start(0);
  } catch (e) {}
  return ac.resume().then(() => ac.state === "running").catch(() => false);
}

let installed = false;
export function installAudioUnlock() {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const go = () => { unlockAudio().then((ok) => { if (ok) ["pointerdown", "keydown", "touchend"].forEach((e) => window.removeEventListener(e, go, true)); }); };
  ["pointerdown", "keydown", "touchend"].forEach((e) => window.addEventListener(e, go, true));
}

function noise(ac) {
  if (!noiseBuf) {
    noiseBuf = ac.createBuffer(1, ac.sampleRate * 1, ac.sampleRate);
    const d = noiseBuf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  }
  const s = ac.createBufferSource();
  s.buffer = noiseBuf;
  s.loop = true;
  return s;
}

/* ---------- sound recipes; each returns a stop() ---------- */
/* Thermal receipt printer: every paper step is a burst of print-head
   chatter (band-passed noise gated at ~38 Hz) with a click at the start,
   over a motor whine. Steps line up with the paper's motor steps. */
export function playPrint({ ms, steps = 22, from = 0, volume = 1, ac = getAudio(), out = master }) {
  if (!ac || !out) return () => {};
  const nodes = [];
  const t0 = ac.currentTime + 0.02;
  const stepLen = ms / 1000 / steps;
  const bus = ac.createGain(); bus.gain.value = volume; bus.connect(out); nodes.push(bus);

  /* motor: two detuned saws through a low-pass, on for the whole run */
  const runFrom = t0, runTo = t0 + stepLen * (steps - from);
  const mg = ac.createGain();
  mg.gain.setValueAtTime(0, runFrom); mg.gain.linearRampToValueAtTime(0.16, runFrom + 0.05);
  mg.gain.setValueAtTime(0.16, runTo - 0.06); mg.gain.linearRampToValueAtTime(0, runTo);
  const lp = ac.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 900; lp.Q.value = 2;
  mg.connect(bus); lp.connect(mg);
  [118, 121.5].forEach((f) => { const o = ac.createOscillator(); o.type = "sawtooth"; o.frequency.value = f; o.connect(lp); o.start(runFrom); o.stop(runTo + 0.05); nodes.push(o); });

  for (let i = from; i < steps; i++) {
    const s = t0 + (i - from) * stepLen, burst = stepLen * 0.55;
    /* head chatter */
    const src = noise(ac);
    const bp = ac.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = 3200; bp.Q.value = 0.8;
    const gate = ac.createGain(); gate.gain.value = 0;
    const lfo = ac.createOscillator(); lfo.type = "square"; lfo.frequency.value = 38;
    const lfoAmt = ac.createGain(); lfoAmt.gain.value = 0.32;
    const env = ac.createGain();
    env.gain.setValueAtTime(0, s); env.gain.linearRampToValueAtTime(1, s + 0.008);
    env.gain.setValueAtTime(1, s + burst - 0.02); env.gain.linearRampToValueAtTime(0, s + burst);
    lfo.connect(lfoAmt).connect(gate.gain);
    gate.gain.setValueAtTime(0.32, s);
    src.connect(bp).connect(gate).connect(env).connect(bus);
    src.start(s, Math.random() * 0.5); src.stop(s + burst + 0.02); lfo.start(s); lfo.stop(s + burst + 0.02);
    /* step click */
    const c = noise(ac);
    const hp = ac.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 1800;
    const cg = ac.createGain();
    cg.gain.setValueAtTime(0.9, s); cg.gain.exponentialRampToValueAtTime(0.001, s + 0.03);
    c.connect(hp).connect(cg).connect(bus);
    c.start(s, Math.random() * 0.5); c.stop(s + 0.04);
    nodes.push(src, lfo, c);
  }
  return () => nodes.forEach((n) => { try { n.stop ? n.stop() : n.disconnect(); } catch (e) {} });
}

export function playRewind({ ms = 520, volume = 1, ac = getAudio(), out = master }) {
  if (!ac || !out) return () => {};
  const t = ac.currentTime + 0.01, secs = ms / 1000;
  const o = ac.createOscillator(); o.type = "sawtooth";
  o.frequency.setValueAtTime(150, t); o.frequency.exponentialRampToValueAtTime(320, t + secs);
  const lp = ac.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 1400;
  const g = ac.createGain();
  g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.28 * volume, t + 0.04); g.gain.linearRampToValueAtTime(0, t + secs);
  o.connect(lp).connect(g).connect(out); o.start(t); o.stop(t + secs + 0.02);
  return () => { try { o.stop(); } catch (e) {} };
}

export function playTug({ volume = 1, ac = getAudio(), out = master }) {
  if (!ac || !out) return () => {};
  const t = ac.currentTime + 0.005;
  const s = noise(ac);
  const bp = ac.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = 1600; bp.Q.value = 1.2;
  const g = ac.createGain(); g.gain.setValueAtTime(2.2 * volume, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.12);
  s.connect(bp).connect(g).connect(out); s.start(t, Math.random() * 0.5); s.stop(t + 0.14);
  return () => { try { s.stop(); } catch (e) {} };
}

export function playRip({ volume = 1, ac = getAudio(), out = master }) {
  if (!ac || !out) return () => {};
  const t = ac.currentTime + 0.005;
  const s = noise(ac);
  const hp = ac.createBiquadFilter(); hp.type = "highpass";
  hp.frequency.setValueAtTime(700, t); hp.frequency.exponentialRampToValueAtTime(5200, t + 0.32);
  const crackle = ac.createGain(); crackle.gain.value = 0;
  const lfo = ac.createOscillator(); lfo.type = "square"; lfo.frequency.setValueAtTime(60, t); lfo.frequency.linearRampToValueAtTime(140, t + 0.35);
  const amt = ac.createGain(); amt.gain.value = 0.5;
  lfo.connect(amt).connect(crackle.gain); crackle.gain.setValueAtTime(0.5, t);
  const g = ac.createGain();
  g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(1.0 * volume, t + 0.03); g.gain.exponentialRampToValueAtTime(0.001, t + 0.42);
  s.connect(hp).connect(crackle).connect(g).connect(out);
  s.start(t, Math.random() * 0.5); s.stop(t + 0.45); lfo.start(t); lfo.stop(t + 0.45);
  return () => { try { s.stop(); lfo.stop(); } catch (e) {} };
}
