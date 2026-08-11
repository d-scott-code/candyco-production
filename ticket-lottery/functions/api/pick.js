// POST /api/pick — LEADERSHIP ONLY (gate with Cloudflare Access).
// Body: { id, action: "claim" | "release" }. Claims/releases a leadership-list
// event for the signed-in leader. The owner (Scott) is unlimited; everyone else
// is capped at 4 claims. (Turn-order round-robin is advisory here — the formal
// draw still lives in the Python engine; this gives leadership a live claim.)
import { json, loadCatalog, getState, putPicks, accessEmail, OWNER_EMAIL, mergeEvents } from "../_shared.js";

const CAP = 4;

export async function onRequestPost({ request, env }) {
  const email = accessEmail(request);
  if (!email) return json({ error: "not authenticated" }, 401);

  let body;
  try { body = await request.json(); } catch { return json({ error: "invalid JSON" }, 400); }
  const { id, action } = body || {};
  if (!id || (action !== "claim" && action !== "release"))
    return json({ error: "id and action (claim|release) are required" }, 400);

  const catalog = await loadCatalog(request);
  const { overrides, picks } = await getState(env);
  const ev = mergeEvents(catalog, overrides).find((e) => e.id === id);
  if (!ev) return json({ error: "unknown event" }, 404);
  if (ev.list !== "leadership")
    return json({ error: "only leadership-list events can be claimed" }, 400);

  const isOwner = email.toLowerCase() === OWNER_EMAIL.toLowerCase();
  const mine = email.toLowerCase();
  let next = picks.filter((p) => p.id !== id); // at most one claim per event

  if (action === "claim") {
    const held = picks.find((p) => p.id === id);
    if (held && held.who.toLowerCase() !== mine)
      return json({ error: `already claimed by ${held.who}` }, 409);
    const count = picks.filter((p) => p.who.toLowerCase() === mine).length;
    if (!isOwner && count >= CAP)
      return json({ error: `you have reached ${CAP} picks` }, 409);
    next = [...next, { id, who: email, at: new Date().toISOString() }];
  }
  await putPicks(env, next);
  return json({ ok: true, id, action });
}
