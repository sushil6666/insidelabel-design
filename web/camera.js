// camera.js - live barcode reading (D-024: the barcode is the product key).
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

// Starts the camera in `video` and calls onCode(digits) once the same code has
// been read twice within AGREE_MS (one frame can misread). Returns stop(), with
// stop.torch(on) and stop.hasTorch when the phone has a light.
//
// D-124: testers found it slow. It used to need two reads in a row, so one
// blurred frame between two good ones started over; it never asked for
// continuous focus, so a phone held close to a small barcode stayed blurred.
const AGREE_MS = 1500;
const TICK_MS = 150;

export async function startScanner(video, onCode) {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } }, audio: false,
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
  if (caps.zoom && caps.zoom.max >= 1.5) want.zoom = Math.min(2, caps.zoom.max);
  if (Object.keys(want).length) {
    try { await track.applyConstraints({ advanced: [want] }); } catch { /* not all phones accept it */ }
  }

  const detector = new window.BarcodeDetector({ formats: FORMATS });
  let stopped = false, timer = null;
  const seen = new Map();                 // code -> time first read

  const stop = () => {
    stopped = true;
    clearTimeout(timer);
    stream.getTracks().forEach(t => t.stop());
    video.srcObject = null;
  };
  stop.hasTorch = !!caps.torch;
  stop.torch = async on => {
    try { await track.applyConstraints({ advanced: [{ torch: !!on }] }); return true; } catch { return false; }
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
        if (seen.has(raw)) {
          stop();
          navigator.vibrate?.(60);
          onCode(hit.format === "upc_e" ? upcEtoA(raw) : raw);
          return;
        }
        seen.set(raw, now);
      }
    } catch { /* a frame that fails to decode is normal */ }
    timer = setTimeout(tick, TICK_MS);
  };
  tick();
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
