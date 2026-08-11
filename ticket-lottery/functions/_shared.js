// Shared helpers for the Cloudflare Pages Functions that power the ticket board.
// State lives in a KV namespace bound as `LOTTERY` (see CLOUDFLARE.md).

export const OWNER_EMAIL = "scott.maxfield@candyco.com"; // unlimited, not in the round-robin

// Basketball + hockey default to the public lottery; everything else (concerts,
// UFC, family shows, etc.) defaults to the private leadership list.
export function defaultList(ev) {
  return ev.league === "NBA" || ev.league === "NHL" ? "public" : "leadership";
}

export function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

// Cloudflare Access injects the verified identity on gated routes. Missing header
// means the route wasn't actually protected — fail closed.
export function accessEmail(request) {
  return request.headers.get("Cf-Access-Authenticated-User-Email") || null;
}

export async function loadCatalog(request) {
  const url = new URL("/ticket-lottery/data/events.json", new URL(request.url).origin);
  const res = await fetch(url, { cf: { cacheTtl: 30 } });
  if (!res.ok) throw new Error("events.json unavailable");
  return res.json();
}

export async function getState(env) {
  const kv = env.LOTTERY;
  if (!kv) return { overrides: {}, picks: [] };
  const [overrides, picks] = await Promise.all([kv.get("overrides"), kv.get("picks")]);
  return { overrides: JSON.parse(overrides || "{}"), picks: JSON.parse(picks || "[]") };
}

export async function putOverrides(env, overrides) {
  if (env.LOTTERY) await env.LOTTERY.put("overrides", JSON.stringify(overrides));
}
export async function putPicks(env, picks) {
  if (env.LOTTERY) await env.LOTTERY.put("picks", JSON.stringify(picks));
}

// Merge catalog + KV overrides into a list-assigned event array.
export function mergeEvents(catalog, overrides) {
  return (catalog.events || []).map((e) => ({
    ...e,
    list: (overrides[e.id] && overrides[e.id].list) || defaultList(e),
  }));
}
