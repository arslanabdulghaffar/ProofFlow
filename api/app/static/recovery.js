// Non-secret request identities only. This cache never grants server authority.
const uuid = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
const fields = ["idempotency_key", "pipeline_id", "transactions_id", "customers_id", "contract_id"];
export function key(workspace) { return "proofflow.pending.v1." + workspace; }
export function savePending(storage, session, body) {
  const value = {workspace:session.workspace_id, expires:session.expires_at, body};
  const raw = JSON.stringify(value);
  if (!parsePending(raw, session.workspace_id, Date.now())) throw new Error("Invalid pending request.");
  storage.setItem(key(session.workspace_id), raw); // Fail before POST if persistence is unavailable.
}
export function parsePending(raw, workspace, now) {
  try {
    if (typeof raw !== "string" || raw.length > 2048) return null;
    const value = JSON.parse(raw);
    if (Object.keys(value).sort().join() !== "body,expires,workspace" || !uuid.test(workspace)
        || value.workspace !== workspace || typeof value.expires !== "string"
        || !Number.isFinite(Date.parse(value.expires)) || Date.parse(value.expires) <= now
        || Date.parse(value.expires) > now + 43200000 || !value.body
        || Object.keys(value.body).sort().join() !== fields.slice().sort().join()
        || !fields.every(k => typeof value.body[k] === "string" && uuid.test(value.body[k]))) return null;
    return value.body;
  } catch { return null; }
}
export function loadPending(storage, session) {
  const name = key(session.workspace_id), raw = storage.getItem(name);
  const value = parsePending(raw, session.workspace_id, Date.now());
  if (raw && !value) storage.removeItem(name);
  return value;
}
export function clearPending(storage, session) { storage.removeItem(key(session.workspace_id)); }
