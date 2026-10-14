// camera.js - live barcode reading (D-024: the barcode is the product key), and the label camera (D-171).
//
// Uses the browser's own BarcodeDetector, which Chrome on Android provides and
// which is what the Play Store build (a Trusted Web Activity, D-010) runs in.
// No third-party scanner library. Where the detector or the camera is missing,
// the caller shows the "type the number" field and the photo path instead.

const FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e"];

export async function barcodeSupported() {
  if (!("BarcodeDetector" in window) || !navigator.mediaDevices?.getUserMedia) return false;
  try {
    const have = await window.BarcodeDetector.getSupportedFormats();
    return FORMATS.some(f => have.includes(f));
  } catch { return false; }
}

// The back camera in `video`, with continuous focus where the phone offers it. `zoom`:
// a little zoom for the barcode (D-124); the label camera wants the whole pack in view.
async function openCamera(video, width, zoom) {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: "environment" }, width: { ideal: width } }, audio: false,
  });
  video.srcObject = stream;
  video.setAttribute("playsinline", "");
  await video.play();

  const track = stream.getVideoTracks()[0];
  const caps = track?.getCapabilities ? track.getCapabilities() : {};
  const want = {};
  if (caps.focusMode?.includes("continuous")) want.focusMode = "continuous";
  // A little zoom lets the phone sit further back, where its lens can focus on a
  // small barcode. Never more than the camera offers.
  if (zoom && caps.zoom && caps.zoom.max >= 1.5) want.zoom = Math.min(2, caps.zoom.max);
  if (Object.keys(want).length) {
    try { await track.applyConstraints({ advanced: [want] }); } catch { /* not all phones accept it */ }
  }
  const stop = () => {
    stream.getTracks().forEach(t => t.stop());
    video.srcObject = null;
  };
  return { track, caps, stop };
}

async function torch(track, on) {
  try { await track.applyConstraints({ advanced: [{ torch: !!on }] }); return true; } catch { return false; }
}

// Starts the camera in `video` and calls onCode(digits) once the same code has
// been read twice within AGREE_MS (one frame can misread). Returns stop(), with
// stop.torch(on) and stop.hasTorch when the phone has a light.
//
// D-124: testers found it slow. It used to need two reads in a row, so one
// blurred frame between two good ones started over; it never asked for
// continuous focus, so a phone held close to a small barcode stayed blurred.
//
// 2026-10-14 (Sushil, comparing another app's scanner: "its really fast"): a read whose GS1
// check digit is right is taken at once; only a read that fails it still needs a second,
// matching read within AGREE_MS (the server checks every barcode again, D-103). And the
// detector looks at each new camera frame (requestVideoFrameCallback, Chrome 83 and later)
// instead of every TICK_MS, which stays the fallback.
const AGREE_MS = 1500;
const TICK_MS = 150;

// GS1 mod-10 (General Specifications 7.9.1), as barcode.check_digit_ok on the server: weights
// 3, 1, 3 ... from the right, the check digit left out. EAN-8, UPC-A and EAN-13 only.
export function checkDigitOk(code) {
  if (!/^(\d{8}|\d{12}|\d{13})$/.test(code)) return false;
  let total = 0;
  for (let i = code.length - 2, w = 3; i >= 0; i--, w = 4 - w) total += Number(code[i]) * w;
  return (10 - total % 10) % 10 === Number(code[code.length - 1]);
}

export async function startScanner(video, onCode) {
  const { track, caps, stop: stopStream } = await openCamera(video, 1280, true);
  const detector = new window.BarcodeDetector({ formats: FORMATS });
  const perFrame = typeof video.requestVideoFrameCallback === "function";
  let stopped = false, timer = null, frame = null;
  const seen = new Map();                 // code -> time first read

  const stop = () => {
    stopped = true;
    clearTimeout(timer);
    if (frame !== null) video.cancelVideoFrameCallback(frame);
    stopStream();
  };
  stop.hasTorch = !!caps.torch;
  stop.torch = on => torch(track, on);

  const found = code => {
    stop();
    // app-polish: a 15 ms tap that the code was caught; none under reduced motion.
    // Chrome allows it after the person's first tap in the app (Chrome 60 and later).
    if (!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) navigator.vibrate?.(15);
    onCode(code);
  };

  const tick = async () => {
    if (stopped) return;
    try {
      const codes = await detector.detect(video);
      const now = Date.now();
      for (const [code, t] of seen) if (now - t > AGREE_MS) seen.delete(code);
      const hit = codes.find(c => c.rawValue);
      const raw = hit?.rawValue?.replace(/\D/g, "");
      if (raw) {
        const code = hit.format === "upc_e" ? upcEtoA(raw) : raw;
        if (checkDigitOk(code) || seen.has(raw)) return found(code);
        seen.set(raw, now);
      }
    } catch { /* a frame that fails to decode is normal */ }
    if (stopped) return;
    if (perFrame) frame = video.requestVideoFrameCallback(tick);
    else timer = setTimeout(tick, TICK_MS);
  };
  tick();
  return stop;
}

// ------------------------------------------------------------------ the label camera (D-171)
// A tester liked the live barcode step and was lost on the label page, which handed over to
// the phone's camera app. The label photos now have a live view too. The shot itself is
// ImageCapture.takePhoto(), the camera's full-resolution still (Chrome on Android), because a
// video frame is too coarse for the small print of an ingredient list. Without it the caller
// keeps the file input with capture="environment" (the camera app), as before.
export function labelCameraSupported() {
  return !!navigator.mediaDevices?.getUserMedia && "ImageCapture" in window
    && typeof window.ImageCapture.prototype.takePhoto === "function";
}

// Hints worked out on the phone from a 64 x 48 copy of the view; nothing is sent anywhere.
// Mean brightness under DARK (0-255) is "dark"; a mean change between two looks over STILL
// is "moving". A hint is a hint: the shutter always works.
const HINT_MS = 300;
const DARK = 50;
const STILL = 14;

// Starts the camera in `video`; onHint(null | "dark" | "moving") as the view changes.
// Returns stop(), with stop.takePhoto() -> Blob, stop.hasTorch and stop.torch(on).
export async function startLabelCamera(video, onHint) {
  const { track, caps, stop: stopStream } = await openCamera(video, 1920, false);      // the preview; the shot is full size
  const capture = new window.ImageCapture(track);
  const canvas = document.createElement("canvas");
  canvas.width = 64; canvas.height = 48;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  let last = null, shown, timer = null, stopped = false;

  const look = () => {
    if (stopped) return;
    try {
      ctx.drawImage(video, 0, 0, 64, 48);
      const px = ctx.getImageData(0, 0, 64, 48).data;
      const luma = new Uint8Array(64 * 48);
      let sum = 0, diff = 0;
      for (let i = 0; i < luma.length; i++) {
        const y = (px[i * 4] * 299 + px[i * 4 + 1] * 587 + px[i * 4 + 2] * 114) / 1000;
        luma[i] = y; sum += y;
        if (last) diff += Math.abs(y - last[i]);
      }
      const hint = sum / luma.length < DARK ? "dark" : last && diff / luma.length > STILL ? "moving" : null;
      last = luma;
      if (hint !== shown) { shown = hint; onHint?.(hint); }
    } catch { /* a frame not ready yet */ }
    timer = setTimeout(look, HINT_MS);
  };
  look();

  const stop = () => {
    stopped = true;
    clearTimeout(timer);
    stopStream();
  };
  stop.hasTorch = !!caps.torch;
  stop.torch = on => torch(track, on);
  stop.takePhoto = async () => {
    // The largest still the camera offers; a phone that refuses the setting gets its default.
    let settings = {};
    try {
      const pc = await capture.getPhotoCapabilities();
      if (pc?.imageWidth?.max) settings = { imageWidth: pc.imageWidth.max };
    } catch { /* not all phones report it */ }
    try { return await capture.takePhoto(settings); } catch { return await capture.takePhoto(); }
  };
  return stop;
}

// UPC-E is printed on small packs; the catalogue stores the full 12-digit UPC-A.
// Only called for codes the detector reported as upc_e: an EAN-8 is also 8 digits.
function upcEtoA(code) {
  if (code.length !== 8) return code;
  const [ns, d1, d2, d3, d4, d5, d6, check] = code;
  let body;
  if ("012".includes(d6)) body = `${d1}${d2}${d6}0000${d3}${d4}${d5}`;
  else if (d6 === "3") body = `${d1}${d2}${d3}00000${d4}${d5}`;
  else if (d6 === "4") body = `${d1}${d2}${d3}${d4}00000${d5}`;
  else body = `${d1}${d2}${d3}${d4}${d5}0000${d6}`;
  return `${ns}${body}${check}`;
}
