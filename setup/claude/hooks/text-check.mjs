#!/usr/bin/env node
// text-check.mjs - a PreToolUse hook: a free check on text as it leaves.
//
// A skill folder may hold `check.json`: rules a plain function runs over outgoing text, with no
// model and no context tokens. Here the outgoing text is a Bash call that publishes words: a commit
// message, a PR, an issue, a comment, a release. A hit blocks the call ONCE with the hints; the same
// command again passes, so an intended word (a quote, a name) is never a dead end. Clean text passes
// unseen.
//
// Checks: text-check.json next to this file (Agent Office's own rules, setup/claude/hooks/), then
// every ~/.claude/skills/*/check.json. Format: {"format":"skill-check/1","rules":[...]}, each rule
// {id, hint} plus one of match (regex), words (stems, any ending) or if + unless. "zyx-skill-check/1"
// is the same format under its first name, and is read too.
//
// Shipped by Agent Office. node --selfcheck tests it.
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const OUTBOUND = /\b(?:gh(?:-axi)?\s+(?:pr\s+(?:create|edit|comment|review|merge)|issue\s+(?:create|edit|comment)|release\s+(?:create|edit)|gist\s+create)|git\s+(?:commit|tag\s+-a|notes))\b/;
const FILE_ARG = /(?:--body-file|--notes-file|--file|-F)\s+(?:"([^"]+)"|'([^']+)'|(\S+))/g;
const FORMATS = new Set(["skill-check/1", "zyx-skill-check/1"]);
const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function readCheck(file, skill) {
  try {
    const raw = JSON.parse(readFileSync(file, "utf8"));
    if (FORMATS.has(raw.format) && Array.isArray(raw.rules)) return { skill, rules: raw.rules };
  } catch { /* a broken or missing check is skipped, never a blocked call */ }
  return null;
}

export function checksIn(dir) {
  const out = [];
  let names = [];
  try { names = readdirSync(dir); } catch { return out; }
  for (const name of names.sort()) {
    const f = join(dir, name, "check.json");
    if (!existsSync(f)) continue;
    const c = readCheck(f, name);
    if (c) out.push(c);
  }
  return out;
}

export function runChecks(text, checks) {
  const out = [];
  for (const c of checks) for (const r of c.rules) {
    let found = [];
    if (r.if !== undefined) {
      found = new RegExp(r.if, "iu").test(text) && !(r.unless && new RegExp(r.unless, "iu").test(text)) ? [""] : [];
    } else {
      const source = r.match ?? `(?<!\\p{L})(?:${r.words.map((w) => escape(w.trim())).join("|")})\\p{L}*`;
      found = [...new Set([...text.matchAll(new RegExp(source, "giu"))].map((m) => m[0]))];
    }
    if (found.length) out.push({ skill: c.skill, id: r.id, found: found.filter(Boolean).slice(0, 5), hint: r.hint });
  }
  return out;
}

/** The words a command publishes: the command itself plus any body file it names. */
export function outgoingText(command, cwd) {
  if (!OUTBOUND.test(command)) return null;
  let text = command;
  for (const m of command.matchAll(FILE_ARG)) {
    const p = m[1] ?? m[2] ?? m[3];
    if (!p || p === "-") continue;
    try { text += `\n${readFileSync(p.startsWith("/") ? p : join(cwd || ".", p), "utf8")}`; } catch { /* not a file */ }
  }
  return text;
}

function sentBefore(session, text) {
  const dir = join(homedir(), ".cache", "text-check");
  const file = join(dir, `${String(session || "none").replace(/[^\w-]/g, "_")}.txt`);
  const key = createHash("sha256").update(text).digest("hex");
  let seen = "";
  try { seen = readFileSync(file, "utf8"); } catch { /* first */ }
  if (seen.includes(key)) return true;
  mkdirSync(dir, { recursive: true });
  writeFileSync(file, `${seen}${key}\n`);
  return false;
}

function main() {
  let payload;
  try { payload = JSON.parse(readFileSync(0, "utf8")); } catch { return 0; }
  const command = String(payload?.tool_input?.command ?? "");
  const text = outgoingText(command, payload?.cwd);
  if (text === null) return 0;
  const own = readCheck(join(dirname(fileURLToPath(import.meta.url)), "text-check.json"), "text-check");
  const checks = [...(own ? [own] : []), ...checksIn(join(homedir(), ".claude", "skills"))];
  const findings = runChecks(text, checks);
  if (!findings.length || sentBefore(payload?.session_id, text)) return 0;
  const lines = findings.map((f) => `- ${f.skill}/${f.id}${f.found.length ? ` (found: ${f.found.map((s) => `"${s}"`).join(", ")})` : ""}: ${f.hint}`);
  process.stderr.write("The text check sent this back before anything was published: fix the text and run it again. " +
    "If a finding is intended (a quote, a name), run the same command again unchanged and it goes through.\n" + lines.join("\n") + "\n");
  return 2;
}

function selfcheck() {
  const assert = (ok, what) => { if (!ok) { console.error(`selfcheck failed: ${what}`); process.exit(1); } };
  const checks = [{ skill: "no-ai-slop", rules: [
    { id: "em-dash", match: "\u2014", hint: "h" }, { id: "w", words: ["leverage", "nahtlos"], hint: "h" }] }];
  assert(outgoingText("git commit -m 'Fix \u2014 the thing'", "") !== null, "commit is outbound");
  assert(outgoingText("gh pr create --title x --body y", "") !== null, "pr create is outbound");
  assert(outgoingText("gh-axi pr comment 3 --body y", "") !== null, "gh-axi comment is outbound");
  assert(outgoingText("git status", "") === null, "status is not");
  assert(outgoingText("gh pr view 3", "") === null, "pr view is not");
  const ids = (t) => runChecks(t, checks).map((f) => f.id).join(",");
  assert(ids("Fix \u2014 we leverage nahtlose") === "em-dash,w", "hits");
  assert(ids("Fix the parser - plain words") === "", "clean");
  console.log("selfcheck ok");
}

if (process.argv.includes("--selfcheck")) selfcheck();
else process.exit(main());
