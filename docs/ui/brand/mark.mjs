// The Zyx mark's line weight, from brand/mark.json: the one place its numbers live. Shipped as
// `@zyxworks/ui/brand/mark.mjs` (with mark.json beside it), so a product's own bake scripts draw with
// the same formulas as the library's files. Plain Node, no dependencies.
//
//   strokeWithWord(fontPx)          the line of a mark that stands with words: the Geist Medium stem
//   strokeAlone(pt)                 the line of a mark on its own, for a rendered 48 box of `pt`
//   rasterAxis(px, { dpr, scale })  the hinted drawing of the mark on a square raster of `px` pixels
//   markSvg(colour, pt?)            the bare mark as SVG; tileSvg(px, dpr?) and avatarSvg(px) the squares
import { readFileSync } from "node:fs";

export const MARK = JSON.parse(readFileSync(new URL("./mark.json", import.meta.url), "utf8"));
const { stem, lockup, stroke, grid } = MARK;
const n = (v) => String(Math.round(v * 1000) / 1000);

/** The stroke of a mark beside words of `fontPx`: the stem of Geist Medium at that size. */
export const strokeWithWord = (fontPx) => stem.em * fontPx;

/** The share of the box the line takes on its own, before the floor (see mark.json `stroke.alone`). */
export function ratioAlone(pt) {
  const { stemUpToPt, largeFromPt, largeRatio } = stroke.alone;
  const lockupRatio = stem.em / lockup.markEm;
  if (pt <= stemUpToPt) return lockupRatio;
  if (pt >= largeFromPt) return largeRatio;
  const t = Math.log2(pt / stemUpToPt) / Math.log2(largeFromPt / stemUpToPt);
  return lockupRatio + (largeRatio - lockupRatio) * t;
}

/** The stroke in pt of a mark on its own whose 48 box renders at `pt`. */
export const strokeAlone = (pt) => Math.max(stroke.alone.floorPt, pt * ratioAlone(pt));

/** The same, in units of the 48 grid: what a scalable file sets as its stroke-width. */
export const gridStrokeAlone = (pt) => (strokeAlone(pt) * grid) / pt;

/**
 * The mark on a square raster: `px` pixels shown at pixel ratio `dpr`, the 48 box `scale` of the
 * square (the tile's markScale, or 1 for a bare mark). Returns the line `w`, the grid unit `unit` and
 * the centre `cx`, `cy` in pixels, and the three arm ends. Up to 64 px the line is whole pixels and
 * the upright arm's edges sit on pixel edges (mark.json `stroke.snap`).
 */
export function rasterAxis(px, { dpr = 1, scale = 1 } = {}) {
  const box = px * scale;
  const unit = box / grid;
  let w = strokeAlone(box / dpr) * dpr;
  const cxRaw = px / 2 + (MARK.centre[0] - grid / 2) * unit;
  let cx = cxRaw;
  if (px <= 64) {
    w = Math.max(1, Math.round(w));
    const left = Math.round(cxRaw - w / 2);
    cx = left + w / 2;
  }
  const cy = px / 2 + (MARK.centre[1] - grid / 2) * unit;
  const arm = MARK.arm * unit;
  const c30 = Math.cos(Math.PI / 6);
  return { w, unit, cx, cy, arm, ends: [[cx, cy - arm], [cx - arm * c30, cy + arm / 2], [cx + arm * c30, cy + arm / 2]] };
}

const svgHead = (px, extra = "") => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${px} ${px}" width="${px}" height="${px}"${extra}><title>Zyx</title>`;
const axisPath = (a) => `M${n(a.cx)} ${n(a.cy)}L${a.ends.map(([x, y]) => `${n(x)} ${n(y)}`).join(`M${n(a.cx)} ${n(a.cy)}L`)}`;

/**
 * The bare mark on its 48 grid for a picture shown at about `pt` (default: text sizes, 24 to 48 pt,
 * where the line is the lockup's). `colour` "auto" switches ink to white in a dark tab (the favicon).
 */
export function markSvg(colour, pt = MARK.stroke.alone.stemUpToPt) {
  const w = n(gridStrokeAlone(pt));
  if (colour === "auto") {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="${pt}" height="${pt}" fill="none" stroke-width="${w}" stroke-linecap="round"><style>path{stroke:${MARK.colour.light}}@media (prefers-color-scheme:dark){path{stroke:${MARK.colour.dark}}}</style><title>Zyx</title><path d="${MARK.path}"/></svg>\n`;
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48" fill="none" stroke="${colour}" stroke-width="${w}" stroke-linecap="round"><title>Zyx</title><path d="${MARK.path}"/></svg>\n`;
}

/** The app icon tile of `px` pixels shown at `dpr`: the white mark on the #111111 rounded square. */
export function tileSvg(px, dpr = 1) {
  const { ground, mark, markScale, radius } = MARK.tile;
  const a = rasterAxis(px, { dpr, scale: markScale });
  return `${svgHead(px)}<rect width="${px}" height="${px}" rx="${n(px * radius)}" fill="${ground}"/><path d="${axisPath(a)}" fill="none" stroke="${mark}" stroke-width="${n(a.w)}" stroke-linecap="round"/></svg>\n`;
}

/** An account avatar of `px` pixels: the ink mark on an opaque white square, drawn for `avatar.seenAtPt`. */
export function avatarSvg(px) {
  const { ground, mark, markScale, seenAtPt } = MARK.avatar;
  const a = rasterAxis(px, { dpr: px / seenAtPt, scale: markScale });
  return `${svgHead(px)}<rect width="${px}" height="${px}" fill="${ground}"/><path d="${axisPath(a)}" fill="none" stroke="${mark}" stroke-width="${n(a.w)}" stroke-linecap="round"/></svg>\n`;
}
