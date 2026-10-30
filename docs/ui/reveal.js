/* @zyxworks/ui 1.0.0 (build d693bb5665f3), dist/reveal.js. Built by scripts/build.mjs from react/reveal.ts: do not edit. */
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
    // A section plays when it passes a line 8% above the bottom of the window, so it is really in
    // view. All above the window counts too, so a section that a fast jump carries past still plays.
    // A short last part (a footer) may never pass that line, so all of it in view also plays it.
    const seen = (entries, by) => {
        for (const e of entries) {
            if (!e.isIntersecting || (by === whole && e.intersectionRatio < 0.99))
                continue;
            play(e.target);
            line.unobserve(e.target);
            whole.unobserve(e.target);
        }
    };
    const line = new IntersectionObserver(seen, { rootMargin: "100000px 0px -8% 0px" });
    const whole = new IntersectionObserver(seen, { threshold: 1 });
    const waiting = [...root.querySelectorAll('[data-zyx-reveal]:not([data-zyx-reveal="on"])')];
    if (root instanceof Element && root.matches('[data-zyx-reveal]:not([data-zyx-reveal="on"])'))
        waiting.unshift(root);
    // In the same task as the class, so what is already in view never shows its waiting state.
    document.documentElement.classList.add("zyx-js");
    const fold = window.innerHeight * 0.92;
    for (const el of waiting) {
        if (el.getBoundingClientRect().top < fold)
            play(el);
        else {
            line.observe(el);
            whole.observe(el);
        }
    }
    return () => { line.disconnect(); whole.disconnect(); };
}
const run = () => reveal();
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run, { once: true });
else run();
})();
