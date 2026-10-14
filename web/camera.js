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
//
// 2026-10-14, later (Sushil, on an Amulspray tin it didn't read: "check how poor our scan is"): the
// barcode covered about a tenth of a 1280 px frame, about one pixel per bar, too few for any reader.
// The camera now asks for 1920 px, and every other look reads only the box inside the corners
// (GUIDE, a little wider than the corners), cut from the full frame, so the reader spends its
// pixels on the barcode, not the room. The other looks still read the whole frame.
const AGREE_MS = 1500;
const TICK_MS = 150;
const SCAN_WIDTH = 1920;
// The corners' box as a share of the camera box (app.css .frame: inset 30% 12%), widened so a
// barcode a little outside the corners is still read.
const GUIDE = { top: 0.22, left: 0.06, bottom: 0.22, right: 0.06 };
// 2026-10-14 (Sushil: the other app "auto zooms"): with no read, the zoom steps 2x, 3x, 4x and
// round again, as far as the camera offers. Camera zoom crops the full sensor, so a small barcode
// gets real detail while the phone stays far enough back to focus.
const ZOOM_STEPS = [2, 3, 4];
const ZOOM_EVERY_MS = 1200;
// 2026-10-14 (Sushil: on his phone Chrome offers no zoom and the live picture stays soft, while "both
// upload and photo works"): with no read after STILL_AFTER_MS, the camera takes a full-resolution still
// every STILL_EVERY_MS (a still is focused and uses the whole sensor), with no flash. The phone reads
// each still; every other one also goes to the server (`onStill`: zxing-cpp, as a barcode photo, no
// model call), at most STILL_SERVER_MAX times while the camera is open (the /check-photo limit).
const STILL_AFTER_MS = 3000;
const STILL_EVERY_MS = 2000;
const STILL_SERVER_MAX = 8;

// The largest still the camera offers, with the flash off where the camera says it can be.
async function still(capture) {
  let settings = {};
  try {
    const pc = await capture.getPhotoCapabilities();
    if (pc?.imageWidth?.max) settings.imageWidth = pc.imageWidth.max;
    if (pc?.fillLightMode?.includes("off")) settings.fillLightMode = "off";
  } catch { /* not all phones report it */ }
  try { return await capture.takePhoto(settings); } catch { return await capture.takePhoto(); }
}

// GS1 mod-10 (General Specifications 7.9.1), as barcode.check_digit_ok on the server: weights
// 3, 1, 3 ... from the right, the check digit left out. EAN-8, UPC-A and EAN-13 only.
export function checkDigitOk(code) {
  if (!/^(\d{8}|\d{12}|\d{13})$/.test(code)) return false;
  let total = 0;
  for (let i = code.length - 2, w = 3; i >= 0; i--, w = 4 - w) total += Number(code[i]) * w;
  return (10 - total % 10) % 10 === Number(code[code.length - 1]);
}

// The part of the camera frame inside the guide, at the camera's own resolution, on `canvas`; null
// before the first frame. The video fills its box with object-fit: cover, so the box shows the
// frame's middle; the guide is a share of that box.
function guideCrop(video, canvas) {
  const vw = video.videoWidth, vh = video.videoHeight, cw = video.clientWidth, ch = video.clientHeight;
  if (!vw || !vh || !cw || !ch) return null;
  const scale = Math.max(cw / vw, ch / vh);
  const shownW = cw / scale, shownH = ch / scale;
  const x = (vw - shownW) / 2 + shownW * GUIDE.left, y = (vh - shownH) / 2 + shownH * GUIDE.top;
  const w = shownW * (1 - GUIDE.left - GUIDE.right), h = shownH * (1 - GUIDE.top - GUIDE.bottom);
  canvas.width = Math.round(w);
  canvas.height = Math.round(h);
  canvas.getContext("2d").drawImage(video, x, y, w, h, 0, 0, canvas.width, canvas.height);
  return canvas;
}

// `note(fields)`: each still's outcome for the app's trail (D-092), so a "Report a problem" shows
// what the stills did on that phone (2026-10-14: report #14 from a Samsung had none, and no reason).
export async function startScanner(video, onCode, onStill = null, note = null) {
  const { track, caps, stop: stopStream } = await openCamera(video, SCAN_WIDTH, true);
  const detector = new window.BarcodeDetector({ formats: FORMATS });
  const perFrame = typeof video.requestVideoFrameCallback === "function";
  const canvas = document.createElement("canvas");
  let stopped = false, timer = null, frame = null, looks = 0;
  const seen = new Map();                 // code -> time first read
  const max = caps.zoom?.max || 1;
  const levels = [...new Set(ZOOM_STEPS.map(z => Math.min(z, max)))].filter(z => z >= 1.5);
  let level = 0, zoomer = null, stills = null, shots = 0, sent = 0;

  const stop = () => {
    stopped = true;
    clearTimeout(timer);
    clearInterval(zoomer);
    clearTimeout(stills);
    if (frame !== null) video.cancelVideoFrameCallback(frame);
    stopStream();
  };
  stop.hasTorch = !!caps.torch;
  stop.torch = on => torch(track, on);
  stop.zoom = levels.length > 1 ? levels[0] : null;     // the level now; stop.onZoom(z) as it steps
  if (levels.length > 1) {
    zoomer = setInterval(async () => {
      level = (level + 1) % levels.length;
      try {
        await track.applyConstraints({ advanced: [{ zoom: levels[level] }] });
        stop.zoom = levels[level];
        stop.onZoom?.(levels[level]);
      } catch { /* not all phones accept it */ }
    }, ZOOM_EVERY_MS);
  }

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
      // Every other look: only the guide's box, at full resolution.
      const crop = looks++ % 2 ? guideCrop(video, canvas) : null;
      const codes = await detector.detect(crop || video);
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

  const capture = "ImageCapture" in window ? new window.ImageCapture(track) : null;
  const shoot = async () => {
    if (stopped) return;
    const t0 = performance.now();
    let blob = null;
    try {
      blob = await still(capture);
      note?.({ still: "taken", ms: Math.round(performance.now() - t0), kb: Math.round(blob.size / 1024) });
    } catch (e) {
      note?.({ still: "failed", error: String(e?.name || "error") });
    }
    if (blob && !stopped) {
      // The phone's own read first. An error here (a detector that refuses a 12 MP image) no longer
      // keeps the still from the server (2026-10-14).
      try {
        const codes = await detector.detect(await createImageBitmap(blob));
        const hit = codes.find(c => c.rawValue);
        const raw = hit?.rawValue?.replace(/\D/g, "");
        const code = raw && (hit.format === "upc_e" ? upcEtoA(raw) : raw);
        if (code && checkDigitOk(code)) return found(code);
      } catch (e) {
        note?.({ still: "unread", error: String(e?.name || "error") });
      }
      if (onStill && shots++ % 2 === 0 && sent < STILL_SERVER_MAX && !stopped) {
        sent++;
        const got = await onStill(blob);            // the server checks the code itself (D-103)
        note?.({ still: "server", found: !!got });
        if (got && !stopped) return found(got);
      }
    }
    if (!stopped) stills = setTimeout(shoot, STILL_EVERY_MS);
  };
  if (capture && typeof capture.takePhoto === "function") stills = setTimeout(shoot, STILL_AFTER_MS);
  else note?.({ still: "unsupported" });
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
