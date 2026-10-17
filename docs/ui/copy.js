/* @zyxworks/ui 0.2.0 (build fe7b4c85b875), dist/copy.js. Built by scripts/build.mjs from react/copy.ts: do not edit. */
(() => {
// Copy: the copy button of a command (`zyx-cmd`). No imports: the build also ships this as a plain
// `copy.js` for a static page.
/**
 * Puts `text` on the clipboard. Where the clipboard is not open to the page (no https, an old
 * browser), it selects `select` and asks the browser to copy that; if even that fails, the text
 * stays selected for the person to copy. True when the text was copied.
 */
async function copyText(text, select) {
    try {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
            return true;
        }
    }
    catch {
        // Refused (no permission, not focused): fall back to the selection below.
    }
    if (!select)
        return false;
    const range = document.createRange();
    range.selectNodeContents(select);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    try {
        return document.execCommand("copy");
    }
    catch {
        return false;
    }
}
/**
 * Wires every `[data-zyx-copy]` button in `root`, also ones added later (one listener on `root`).
 * `data-zyx-copy="<id>"` copies the text of that element; empty, it copies the `code` of its
 * `zyx-cmd`. While done the button says `data-done-label` (default "Copied") and wears `data-done`,
 * and the `role="status"` element of its `zyx-cmd` says it once. Returns a function that unwires.
 */
function copyButtons(root = document) {
    const timers = new WeakMap();
    const onClick = (event) => {
        const button = event.target instanceof Element ? event.target.closest("[data-zyx-copy]") : null;
        if (!(button instanceof HTMLElement) || !root.contains(button))
            return;
        const box = button.closest(".zyx-cmd");
        const id = button.getAttribute("data-zyx-copy");
        const source = (id ? document.getElementById(id) : null) ?? box?.querySelector("code") ?? null;
        if (!source)
            return;
        // The word it said before the first copy, so a second copy in the done state restores it too.
        const idle = button.getAttribute("data-zyx-idle") ?? button.textContent ?? "";
        button.setAttribute("data-zyx-idle", idle);
        const status = box?.querySelector('[role="status"]') ?? null;
        void copyText(source.textContent ?? "", source).then((ok) => {
            if (!ok)
                return;
            const done = button.getAttribute("data-done-label") || "Copied";
            button.setAttribute("data-done", "");
            button.textContent = done;
            if (status)
                status.textContent = done;
            window.clearTimeout(timers.get(button));
            timers.set(button, window.setTimeout(() => {
                button.removeAttribute("data-done");
                button.textContent = idle;
                if (status)
                    status.textContent = "";
            }, 1600));
        });
    };
    root.addEventListener("click", onClick);
    return () => root.removeEventListener("click", onClick);
}
const run = () => copyButtons();
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run, { once: true });
else run();
})();
