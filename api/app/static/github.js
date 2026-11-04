// The preview POST is read-only preparation. Only a separate explicit click approves writes.
export function installGitHub({api, notice, currentSession, currentVersion}) {
  const $ = id => document.getElementById(id);
  const uuid = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
  let intent = null, selected = null, value = null, generation = 0, busy = false;
  let lastVersion = null;
  function allowed() {
    const s = currentSession(), v = currentVersion();
    return s?.kind === "operator" && v?.eligible && v.active_version === v.id;
  }
  function controls() {
    if(lastVersion!==currentVersion()?.id) { $("pr-confirm").checked=false; lastVersion=currentVersion()?.id; }
    $("pr-preview").disabled = busy || !allowed();
    $("pr-refresh").disabled = busy || !intent;
    $("pr-approve").disabled = busy || !value || value.state !== "PREVIEW" ||
      !value.currently_authorized || value.version_id !== currentVersion()?.id ||
      Date.parse(value.expires_at) <= Date.now() || !$("pr-confirm").checked;
  }
  function reset() {
    generation++; intent = selected = value = null; busy = false;
    $("pr-confirm").checked = false; $("pr-details").textContent = "No GitHub action prepared.";
    $("pr-link").hidden = true; controls();
  }
  function save() {
    const s = currentSession();
    sessionStorage.setItem("proofflow.pending-pr", JSON.stringify({workspace:s.workspace_id,
      expires:s.expires_at, intent, version:selected}));
  }
  async function refresh() {
    if (!intent) return;
    const g = generation, id = intent;
    const result = await api("/v1/pr-intents/" + id);
    if (generation !== g || intent !== id) return;
    if (value?.preview_sha256 !== result.preview_sha256 || result.state !== "PREVIEW") $("pr-confirm").checked = false;
    value = result;
    $("pr-details").textContent = JSON.stringify(result, null, 2);
    $("pr-link").hidden = true;
    if (result.state === "COMPLETE" && /^https:\/\/github\.com\/arslanabdulghaffar\/ProofFlow-Demo\/pull\/[1-9][0-9]*$/.test(result.result?.url)) {
      $("pr-link").href = result.result.url; $("pr-link").hidden = false;
    }
    controls();
  }
  $("pr-preview").addEventListener("click", async () => {
    if (busy || !allowed()) return;
    // Reuse a pending preview identity after an uncertain reply. Never auto-approve.
    const v = currentVersion().id;
    if (!intent || selected !== v || value) { intent = crypto.randomUUID(); selected = v; value = null; }
    const g = ++generation, id = intent;
    $("pr-confirm").checked = false; busy = true; controls();
    try {
      save();
      await api("/v1/versions/" + selected + "/pr-preview", "POST", {intent_id:id});
      if (g !== generation) return;
      const url = new URL(location.href); url.searchParams.set("pr", id); history.replaceState(null,"",url);
      await refresh(); notice("GitHub preview requested. Refresh to inspect the exact diff and destination before approval.");
    } catch(e) { if (g === generation) notice(e.message,true); }
    finally { if (g === generation) { busy = false; controls(); } }
  });
  $("pr-refresh").addEventListener("click", () => refresh().catch(e=>notice(e.message,true)));
  $("pr-confirm").addEventListener("change", controls);
  $("pr-approve").addEventListener("click", async () => {
    controls(); if ($("pr-approve").disabled) return;
    const g = generation, id = intent, digest = value.preview_sha256;
    busy = true; $("pr-confirm").checked = false; controls();
    try {
      await api("/v1/pr-intents/" + id + "/approve", "POST", {preview_sha256:digest,confirm:true});
      if (g !== generation) return;
      await refresh(); notice("Exact GitHub approval recorded. Refresh for committed write and readback status.");
    } catch(e) { if (g === generation) notice(e.message + ". Refresh the existing intent before retrying.",true); }
    finally { if (g === generation) { busy = false; controls(); } }
  });
  async function resume() {
    const s = currentSession(); if (!s) return;
    const urlId = new URL(location.href).searchParams.get("pr");
    if (urlId && uuid.test(urlId)) { intent=urlId; await refresh(); return; }
    const raw = sessionStorage.getItem("proofflow.pending-pr");
    if (!raw || raw.length > 1024) return;
    try {
      const p=JSON.parse(raw);
      if (Object.keys(p).sort().join() !== "expires,intent,version,workspace" || p.workspace!==s.workspace_id ||
          p.expires!==s.expires_at || Date.parse(p.expires)<=Date.now() || !uuid.test(p.intent) || !uuid.test(p.version)) return;
      intent=p.intent; selected=p.version; await refresh();
    } catch(e) { notice("Saved GitHub preview needs review. " + e.message,true); }
    controls();
  }
  return {reset, resume, controls};
}
