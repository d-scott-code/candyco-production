// GET /api/admin — LEADERSHIP ONLY (gate this route with Cloudflare Access).
// Returns both lists + the pick log + who you are. Fails closed if the Access
// identity header is missing (i.e. the route wasn't actually protected).
import { json, loadCatalog, getState, mergeEvents, accessEmail, OWNER_EMAIL } from "../_shared.js";

export async function onRequestGet({ request, env }) {
  const email = accessEmail(request);
  if (!email) return json({ error: "not authenticated" }, 401);
  try {
    const catalog = await loadCatalog(request);
    const { overrides, picks } = await getState(env);
    const events = mergeEvents(catalog, overrides);
    const mine = picks.filter((p) => p.who.toLowerCase() === email.toLowerCase()).length;
    return json({
      season: catalog.season,
      you: email,
      isOwner: email.toLowerCase() === OWNER_EMAIL.toLowerCase(),
      myPicks: mine,
      events,
      picks,
    });
  } catch (e) {
    return json({ error: String(e) }, 500);
  }
}
