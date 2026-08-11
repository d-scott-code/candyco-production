// POST /api/move — LEADERSHIP ONLY (gate with Cloudflare Access).
// Body: { id, to: "public" | "leadership" }. Moves an event between the public
// board and the private leadership list. Moving an event back to its default
// list clears the override (keeps the store tidy).
import { json, loadCatalog, getState, putOverrides, accessEmail, defaultList } from "../_shared.js";

export async function onRequestPost({ request, env }) {
  const email = accessEmail(request);
  if (!email) return json({ error: "not authenticated" }, 401);

  let body;
  try { body = await request.json(); } catch { return json({ error: "invalid JSON" }, 400); }
  const { id, to } = body || {};
  if (!id || (to !== "public" && to !== "leadership"))
    return json({ error: "id and to (public|leadership) are required" }, 400);

  const catalog = await loadCatalog(request);
  const ev = (catalog.events || []).find((e) => e.id === id);
  if (!ev) return json({ error: "unknown event" }, 404);

  const { overrides } = await getState(env);
  if (to === defaultList(ev)) {
    delete overrides[id];
  } else {
    overrides[id] = { list: to, by: email, at: new Date().toISOString() };
  }
  await putOverrides(env, overrides);
  return json({ ok: true, id, to });
}
