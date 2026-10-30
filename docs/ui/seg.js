/* @zyxworks/ui 1.1.0 (build f69b21cf273f), dist/seg.js. Built by scripts/build.mjs from react/seg.ts: do not edit. */
(() => {
// Seg: a segmented control on a static page that switches what is shown (1.1). No imports: the build
// also ships this as a plain `seg.js` for a static page.
//
//   <div class="zyx-seg" role="group" aria-label="Plan" data-zyx-seg>
//     <button type="button" aria-pressed="true" aria-controls="plan-week">Week</button>
//     <button type="button" aria-pressed="false" aria-controls="plan-month">Month</button>
//   </div>
//   <div id="plan-week">...</div>
//   <div id="plan-month" hidden>...</div>
//
// Only a group with `data-zyx-seg` is wired, so a React `Segmented` on the same page is left alone.
// The keys follow the library's choice for every segmented control: arrows, Home and End move the
// focus only; Enter or Space (the button's own click) chooses. Only the chosen view is a tab stop.
const GROUP = ".zyx-seg[data-zyx-seg]";
function buttonsOf(group) {
    return [...group.children].filter((el) => el instanceof HTMLButtonElement && !el.disabled);
}
/** Makes the chosen view (or the first one) the only tab stop of `group`. */
function rove(group) {
    const buttons = buttonsOf(group);
    const chosen = buttons.find((b) => b.getAttribute("aria-pressed") === "true") ?? buttons[0];
    for (const b of buttons)
        b.tabIndex = b === chosen ? 0 : -1;
}
/** Chooses `button` in its group: pressed, the only tab stop, its panel shown and the others hidden. */
function choose(button) {
    const group = button.parentElement;
    if (!group)
        return;
    for (const b of buttonsOf(group)) {
        const on = b === button;
        b.setAttribute("aria-pressed", String(on));
        b.tabIndex = on ? 0 : -1;
        const panel = b.getAttribute("aria-controls");
        const el = panel ? document.getElementById(panel) : null;
        if (el)
            el.hidden = !on;
    }
    button.dispatchEvent(new CustomEvent("zyx-seg", { bubbles: true, detail: { value: button.value || button.textContent?.trim() || "" } }));
}
/**
 * Wires every `.zyx-seg[data-zyx-seg]` in `root`, also groups added later (one listener per event on
 * `root`). A choice fires a bubbling `zyx-seg` event whose `detail.value` is the button's `value`
 * (or its words). Returns a function that unwires.
 */
function segments(root = document) {
    for (const group of root.querySelectorAll(GROUP))
        rove(group);
    const groupOf = (event) => {
        const button = event.target instanceof Element ? event.target.closest("button") : null;
        const group = button?.parentElement;
        return button instanceof HTMLButtonElement && group?.matches(GROUP) && root.contains(group) ? { button, group } : null;
    };
    const onClick = (event) => {
        const hit = groupOf(event);
        if (hit && !hit.button.disabled)
            choose(hit.button);
    };
    const onKey = (event) => {
        const hit = groupOf(event);
        if (!hit || !(event instanceof KeyboardEvent))
            return;
        const buttons = buttonsOf(hit.group);
        const at = buttons.indexOf(hit.button);
        const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
        let next = -1;
        if (event.key in step)
            next = (at + (step[event.key] ?? 0) + buttons.length) % buttons.length;
        else if (event.key === "Home")
            next = 0;
        else if (event.key === "End")
            next = buttons.length - 1;
        if (next < 0)
            return;
        event.preventDefault();
        buttons[next]?.focus();
    };
    root.addEventListener("click", onClick);
    root.addEventListener("keydown", onKey);
    return () => {
        root.removeEventListener("click", onClick);
        root.removeEventListener("keydown", onKey);
    };
}
const run = () => segments();
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run, { once: true });
else run();
})();
