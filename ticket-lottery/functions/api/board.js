// GET /api/board — PUBLIC. Only ever returns events on the public list, so it is
// safe to call without authentication. The employee board reads this.
import { json, loadCatalog, getState, mergeEvents } from "../_shared.js";

export async function onRequestGet({ request, env }) {
  try {
    const catalog = await loadCatalog(request);
    const { overrides } = await getState(env);
    const events = mergeEvents(catalog, overrides)
      .filter((e) => e.list === "public" && e.include !== false);
    return json({ season: catalog.season, events });
  } catch (e) {
    return json({ error: String(e) }, 500);
  }
}
