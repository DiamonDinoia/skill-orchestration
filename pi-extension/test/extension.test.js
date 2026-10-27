import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import managerExtension, { managerInstructions } from "../index.js";

const SKILL_MD = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "skills",
  "manager",
  "SKILL.md"
);

function makePi() {
  const commands = {};
  const handlers = {};
  return {
    registerCommand: (name, cfg) => { commands[name] = cfg; },
    on: (event, handler) => { (handlers[event] ||= []).push(handler); },
    sendUserMessage: () => {},
    commands,
    handlers,
  };
}

test("loads instructions from the skill body", () => {
  const src = readFileSync(SKILL_MD, "utf8");
  const fm = src.match(/^---\n[\s\S]*?\n---\n?/);
  const expected = (fm ? src.slice(fm[0].length) : src).trim();
  const actual = managerInstructions();
  assert.equal(actual, expected);
  assert.match(actual, /^# Manager$/m);
});

test("injects instructions only while active", async () => {
  const pi = makePi();
  managerExtension(pi);
  const before = pi.handlers.before_agent_start[0];
  assert.equal(await before({ systemPrompt: "base" }), undefined);
  await pi.commands.manager.handler("fix the flaky test", { ui: { notify: () => {} } });
  const out = await before({ systemPrompt: "base" });
  assert.match(out.systemPrompt, /^base\n\n/);
  assert.match(out.systemPrompt, /Dispatch tiers/);
});

test("stop manager deactivates", async () => {
  const pi = makePi();
  managerExtension(pi);
  const before = pi.handlers.before_agent_start[0];
  await pi.commands.manager.handler("", { ui: { notify: () => {} } });
  assert.ok(await before({ systemPrompt: "base" }));
  await pi.handlers.input[0]({ text: "stop manager" });
  assert.equal(await before({ systemPrompt: "base" }), undefined);
});
