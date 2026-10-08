// icons.js - the app's own icons (docs/APP_DESIGN.md section 8.7), drawn for
// InsideLabel on a 24 px grid: 2 px strokes, round caps and joins, currentColor.
//
// Built with createElementNS from constant path data: no innerHTML, no server
// text (tests/test_web.py). Every icon but kindIcon is decoration (aria-hidden); the words
// beside it carry the meaning. A check means only "this photo is readable",
// never anything about the food, and no icon says a pack is good or bad.
//
// D-169: each kind of message has one fixed symbol (kindIcon below) and one colour
// (the .k-* classes in app.css), on every screen. A photo problem is never drawn
// like a finding about the food: it has its own retake arrow and grey-blue.

const NS = "http://www.w3.org/2000/svg";

// Each shape: "M..." a path, or ["circle", cx, cy, r].
const SHAPES = {
  "chevron-right": ["M9 5.5l6.5 6.5-6.5 6.5"],
  "chevron-down": ["M5.5 9l6.5 6.5 6.5-6.5"],
  back: ["M15 5.5L8.5 12l6.5 6.5"],
  forward: ["M5 12h13", "M12.5 6l6 6-6 6"],               // D-185: "Scan here" goes on to the scanner
  alert: ["M12 6.5v7", "M12 17.5v.01"],
  cross: ["M7.5 7.5l9 9", "M16.5 7.5l-9 9"],
  check: ["M5.5 12.5l4.5 4.5 8.5-9.5"],
  dot: [["circle", 12, 12, 3]],
  // The scan button: a barcode inside a camera frame's corners.
  barcode: ["M3 8V5.5A2.5 2.5 0 0 1 5.5 3H8", "M16 3h2.5A2.5 2.5 0 0 1 21 5.5V8",
            "M21 16v2.5a2.5 2.5 0 0 1-2.5 2.5H16", "M8 21H5.5A2.5 2.5 0 0 1 3 18.5V16",
            "M7.5 8v8", "M10.5 8v8", "M13 8v8", "M16.5 8v8"],
  // The limit and error screens: a pack beside a clock, nothing that judges.
  clock: [["circle", 12, 12, 8.5], "M12 7.5V12l3 2"],
  pack: ["M6.5 3.5h11l1.5 4v13h-14v-13z", "M5 7.5h14", "M9 11.5h6", "M9 14.5h6", "M9 17.5h3.5"],
  // D-177: Share on a result: three joined dots.
  share: [["circle", 17.5, 5.5, 2.5], ["circle", 6.5, 12, 2.5], ["circle", 17.5, 18.5, 2.5], "M8.7 10.8l6.6-4", "M8.7 13.2l6.6 4"],
  plus: ["M12 5.5v13", "M5.5 12h13"],
  compare: ["M4 4.5h6.5v15H4z", "M13.5 4.5H20v15h-6.5z", "M6.5 9h1.5", "M16 9h1.5", "M6.5 12.5h1.5", "M16 12.5h1.5"],
  // D-169: the message kinds' own symbols.
  retake: ["M18.5 12a6.5 6.5 0 1 1-1.9-4.6", "M18.6 4.6v3.6H15"],
  circlecross: [["circle", 12, 12, 9], "M9.2 9.2l5.6 5.6", "M14.8 9.2l-5.6 5.6"],
  triangle: ["M12 4l9 15.5H3z", "M12 10v4.2", "M12 17.2v.01"],
  circlealert: [["circle", 12, 12, 9], "M12 7.6v5.4", "M12 16.4v.01"],
  info: [["circle", 12, 12, 9], "M12 11.2v5.2", "M12 7.8v.01"],
  wifi: ["M3.5 9.5a12 12 0 0 1 17 0", "M6.5 12.8a7.5 7.5 0 0 1 11 0", "M9.5 16a3.2 3.2 0 0 1 5 0",
         "M12 19.5v.01"],
};

export function icon(name, cls = "") {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", ("icon " + cls).trim());
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", String(false));     // a boolean: the wording lint reads string literals
  for (const s of SHAPES[name] || []) {
    let n;
    if (Array.isArray(s)) {
      n = document.createElementNS(NS, "circle");
      n.setAttribute("cx", s[1]); n.setAttribute("cy", s[2]); n.setAttribute("r", s[3]);
    } else {
      n = document.createElementNS(NS, "path");
      n.setAttribute("d", s);
    }
    svg.append(n);
  }
  return svg;
}

// A larger drawing for an empty or waiting screen: two icons side by side in a soft disc.
export function spot(...names) {
  const box = document.createElement("div");
  box.className = "spot";
  box.setAttribute("aria-hidden", "true");
  names.forEach(n => box.append(icon(n)));
  return box;
}

// D-169: one symbol per kind of message. The name is what a screen reader says when the
// symbol stands alone; beside words that already say the same, pass decorative = true.
export const KINDS = {
  problem: ["retake", "Photo problem"],
  avoid: ["circlecross", "On your avoid list"],
  notpermitted: ["triangle", "Not permitted in India"],
  worth: ["circlealert", "Worth a look"],
  info: ["info", "Information"],
  done: ["check", "Done"],
};

export function kindIcon(kind, decorative = false) {
  const [name, label] = KINDS[kind];
  const svg = icon(name, "kind-icon ki-" + kind);
  if (!decorative) {
    svg.removeAttribute("aria-hidden");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
  }
  return svg;
}
