/* @zyxworks/ui 1.0.0 (build d693bb5665f3), dist/accent.js. Built by scripts/build.mjs from react/accent.ts: do not edit. */
(() => {
// White-label: a client sets one accent (a hex value). It is used only on the accent places (main
// button, focus ring, needs-you dot, running arm, the on-state of a switch or check box). White text on
// it must reach 4.5:1, else the check warns and the accent stays ink. Dark mode gets a lighter version
// made from it, with ink words on it. No imports: safe on a server and in a plain page.
const INK = "#111111";
const WHITE = "#ffffff";
const DARK_INK = "#ededed";
/** `#abc` or `#aabbcc` as [r, g, b] 0-255, or undefined. */
function parseHex(hex) {
    const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim());
    if (!m?.[1])
        return undefined;
    const h = m[1].length === 3 ? [...m[1]].map((c) => c + c).join("") : m[1];
    return [0, 2, 4].map((i) => Number.parseInt(h.slice(i, i + 2), 16));
}
const toHex = (rgb) => `#${rgb.map((c) => Math.round(c).toString(16).padStart(2, "0")).join("")}`;
/** The WCAG relative luminance of a hex colour. */
function luminance(hex) {
    const rgb = parseHex(hex);
    if (!rgb)
        throw new Error(`not a hex colour: ${hex}`);
    const [r, g, b] = rgb.map((c) => {
        const s = c / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
/** The WCAG contrast ratio of two hex colours (1 to 21). */
function contrast(a, b) {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
}
/** `hex` mixed toward white by `t` (0 to 1). */
function lighten(hex, t) {
    const rgb = parseHex(hex) ?? [0, 0, 0];
    return toHex(rgb.map((c) => c + (255 - c) * t));
}
/**
 * Checks a client's accent. `darkBg` is the dark page (the brand's dark `bg`): the dark accent is the
 * value lightened until ink words on it reach 4.5:1 and it stands out 3:1 from that page.
 */
function checkAccent(hex, { darkBg = INK } = {}) {
    const rgb = parseHex(hex);
    const fallback = { light: { accent: INK, onAccent: WHITE }, dark: { accent: DARK_INK, onAccent: INK } };
    if (!rgb)
        return { ok: false, ...fallback, ratio: 0, warning: `"${hex}" is not a colour. Use a hex value such as #1f4fd1. The accent stays ink.` };
    const value = toHex(rgb);
    const ratio = Math.round(contrast(WHITE, value) * 100) / 100;
    if (ratio < 4.5) {
        return { ok: false, ...fallback, ratio, warning: `White text on ${value} reaches only ${ratio.toFixed(2)}:1, and 4.5:1 is needed. The accent stays ink. Pick a darker colour.` };
    }
    let dark = value;
    for (let t = 0; t <= 1; t += 0.05) {
        dark = lighten(value, t);
        if (contrast(dark, INK) >= 4.5 && contrast(dark, darkBg) >= 3)
            break;
    }
    return { ok: true, light: { accent: value, onAccent: WHITE }, dark: { accent: dark, onAccent: INK }, ratio };
}
/**
 * The CSS that puts a checked accent in place, with the same selectors as the brand's tokens.css. Put
 * it in a `<style>` after zyx-ui.css (or tokens.css).
 */
function accentCss(check) {
    const vars = (v) => `--z-accent: ${v.accent}; --z-on-accent: ${v.onAccent};`;
    return [
        `:root, [data-theme="light"] { ${vars(check.light)} }`,
        `[data-theme="dark"] { ${vars(check.dark)} }`,
        `@media (prefers-color-scheme: dark) { [data-theme="system"] { ${vars(check.dark)} } }`,
    ].join("\n");
}
(window.zyxAccent = { checkAccent, accentCss, contrast });
})();
