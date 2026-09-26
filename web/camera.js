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

// Starts the camera in `video` and calls onCode(digits) once a code has been
// read the same way twice in a row (one frame can misread). Returns stop().
export async function startScanner(video, onCode) {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } }, audio: false,
  });
  video.srcObject = stream;
  video.setAttribute("playsinline", "");
  await video.play();

  const detector = new window.BarcodeDetector({ formats: FORMATS });
  let stopped = false, last = null, timer = null;

  const stop = () => {
    stopped = true;
    clearTimeout(timer);
    stream.getTracks().forEach(t => t.stop());
    video.srcObject = null;
  };

  const tick = async () => {
    if (stopped) return;
    try {
      const codes = await detector.detect(video);
      const raw = codes[0]?.rawValue?.replace(/\D/g, "");
      if (raw && raw === last) {
        stop();
        onCode(codes[0].format === "upc_e" ? upcEtoA(raw) : raw);
        return;
      }
      last = raw || null;
    } catch { /* a frame that fails to decode is normal */ }
    timer = setTimeout(tick, 200);      // ~5 reads a second is plenty on a low-end phone
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
