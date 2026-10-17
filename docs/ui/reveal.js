/* @zyxworks/ui 0.2.0 (build fe7b4c85b875), dist/reveal.js. Built by scripts/build.mjs from react/reveal.ts: do not edit. */
(() => {
// Reveal: a `[data-zyx-reveal]` section waits until it is seen, then plays its draw-in once
// (css/site.css). No imports: the build also ships this as a plain `reveal.js` for a static page.
/**
 * Starts the reveal for every `[data-zyx-reveal]` in `root`. What is on screen already plays at once;
 * the rest waits and plays once when it scrolls in. It sets `zyx-js` on <html>, the class the
 * waiting state needs, so a page with no script is never blank. With less motion, or no
 * IntersectionObserver, nothing waits. Returns a function that stops watching.
 */
function reveal(root = document) {
    if (typeof window === "undefined" || !("IntersectionObserver" in window))
        return () => { };
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches)
        return () => { };
    const play = (el) => el.setAttribute("data-zyx-reveal", "on");
    // The bottom 8% of the window does not count, so a section plays when it is really in view.
    const io = new IntersectionObserver((entries) => {
        for (const e of entries) {
            if (!e.isIntersecting)
                continue;
            play(e.target);
            io.unobserve(e.target);
        }
    }, { rootMargin: "0px 0px -8% 0px" });
    const waiting = [...root.querySelectorAll('[data-zyx-reveal]:not([data-zyx-reveal="on"])')];
    if (root instanceof Element && root.matches('[data-zyx-reveal]:not([data-zyx-reveal="on"])'))
        waiting.unshift(root);
    // In the same task as the class, so what is already in view never shows its waiting state.
    document.documentElement.classList.add("zyx-js");
    const fold = window.innerHeight * 0.92;
    for (const el of waiting) {
        if (el.getBoundingClientRect().top < fold)
            play(el);
        else
            io.observe(el);
    }
    return () => io.disconnect();
}
const run = () => reveal();
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run, { once: true });
else run();
})();
