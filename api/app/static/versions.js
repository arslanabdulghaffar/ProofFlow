// Browser controls supply explicit intent; database transactions own authority.
export function installVersions({api, notice, currentSession}) {
  const $ = id => document.getElementById(id);
  const uuid = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
  let repair = null, version = null, preview = null, batch = null, pending = null;
  let uploads = {};
  function reset() {
    repair = version = preview = batch = pending = null; uploads = {};
    $("version-prepare").disabled = true;
    $("version-preview").disabled = true;
    $("version-approve").disabled = true;
    $("version-revoke").disabled = true;
    $("version-confirm").checked = false;
    $("version-revoke-confirm").checked = false;
    $("version-details").textContent = "Prepare a verified version to inspect its exact identity.";
    $("approval-details").textContent = "No approval preview.";
    $("batch-form").reset(); $("batch-start").disabled = true;
    $("batch-refresh").disabled = true; $("batch-cancel").disabled = true;
    $("batch-result").textContent = "No batch selected."; $("batch-evidence").hidden = true; $("batch-retry").hidden = true;
  }
  async function refreshVersion() {
    if (!version) return;
    version = await api("/v1/versions/" + version.id);
    $("version-details").textContent = JSON.stringify({version_id:version.id,
      pipeline_id:version.pipeline_id, candidate_sha256:version.code_sha256,
      contract_sha256:version.contract_sha256, runtime_sha256:version.runtime_sha256,
      verifier_sha256:version.verifier_sha256, evidence_sha256:version.evidence_sha256,
      active_version:version.active_version, eligible:version.eligible,
      revoked_at:version.revoked_at}, null, 2);
    $("version-preview").disabled = !version.eligible || version.active_version === version.id;
    $("version-revoke").disabled = !!version.revoked_at || !$("version-revoke-confirm").checked;
    $("batch-start").disabled = !!pending || !version.eligible || version.active_version !== version.id;
    if (!version.eligible || version.active_version === version.id) {
      preview = null; $("version-confirm").checked = false; $("version-approve").disabled = true;
    }
  }
  $("version-prepare").addEventListener("click", async () => {
    if (!repair) return;
    $("version-prepare").disabled = true;
    try {
      const value = await api("/v1/repairs/" + repair + "/version", "POST", {prepare_verified_source:true});
      preview = null; version = {id:value.version_id};
      const url = new URL(location.href); url.searchParams.set("version", version.id);
      history.replaceState(null, "", url); await refreshVersion();
      notice("Verified source prepared. Review the exact approval preview before activating.");
    } catch (e) { notice(e.message, true); $("version-prepare").disabled = false; }
  });
  $("version-preview").addEventListener("click", async () => {
    if (!version) return;
    $("version-confirm").checked = false; $("version-approve").disabled = true;
    try {
      preview = await api("/v1/versions/" + version.id + "/preview", "POST", {intent_id:crypto.randomUUID()});
      $("approval-details").textContent = JSON.stringify(preview, null, 2);
    } catch (e) { preview = null; notice(e.message, true); }
  });
  $("version-confirm").addEventListener("change", () => {
    $("version-approve").disabled = !preview || !$("version-confirm").checked;
  });
  $("version-approve").addEventListener("click", async () => {
    if (!preview || !version || !$("version-confirm").checked) return;
    $("version-approve").disabled = true;
    try {
      await api("/v1/versions/" + version.id + "/approve", "POST",
        {intent_id:preview.intent_id, bundle_sha256:preview.bundle_sha256, confirm:true});
      await refreshVersion(); notice("Exact approval recorded. Fresh batches use the active version.");
    } catch (e) { notice(e.message + ". Refresh version status before retrying.", true);
      $("version-approve").disabled = false; }
  });
  $("version-refresh").addEventListener("click", () => refreshVersion().catch(e => notice(e.message,true)));
  $("version-revoke-confirm").addEventListener("change", () => {
    $("version-revoke").disabled = !version || !!version.revoked_at || !$("version-revoke-confirm").checked;
  });
  $("version-revoke").addEventListener("click", async () => {
    if (!version || !$("version-revoke-confirm").checked) return;
    try {
      await api("/v1/versions/" + version.id + "/revoke", "POST",
        {expected_revision:version.pipeline_revision, confirm:true});
      await refreshVersion(); notice("Version revoked. Unfinished affected work must stop and clean up.");
    } catch (e) { notice(e.message,true); }
  });
  for (const kind of ["transactions", "customers"]) $("batch-" + kind).addEventListener("change", () => {
    if (!pending) delete uploads[kind];
  });
  async function refreshBatch() {
    if (!batch) return;
    const value = await api("/v1/batches/" + batch);
    $("batch-result").textContent = value.state.replaceAll("_", " ") + " · " + (value.outcome || "Waiting for committed evidence") + " · Version " + value.version_id + (value.version_currently_eligible ? "" : " · This version is now revoked or incompatible. Historical results remain recorded.");
    $("batch-evidence").hidden = false; $("batch-evidence").href = "/v1/batches/" + batch;
    $("batch-refresh").disabled = false;
    $("batch-cancel").disabled = !["QUEUED", "RUNNING"].includes(value.state);
  }
  function savePending() {
    const session = currentSession();
    sessionStorage.setItem("proofflow.pending-batch", JSON.stringify({workspace:session.workspace_id,
      expires:session.expires_at, ...pending}));
  }
  async function submitPending() {
    const value = await api("/v1/pipelines/" + pending.pipeline + "/batches", "POST", pending.request);
    batch = value.batch_id; pending = null;
    sessionStorage.removeItem("proofflow.pending-batch");
    const url = new URL(location.href); url.searchParams.set("batch",batch);
    history.replaceState(null,"",url); await refreshBatch();
  }
  $("batch-form").addEventListener("submit", async event => {
    event.preventDefault(); if (!version || pending) return;
    $("batch-start").disabled = true;
    try {
      for (const kind of ["transactions", "customers"]) {
        const file = $("batch-" + kind).files[0];
        if (!file || file.size < 1 || file.size > 5242880) throw new Error("Select bounded fresh CSV files.");
        const entry = uploads[kind] ||= {id:crypto.randomUUID(), file};
        if (entry.file !== file) throw new Error("File selection changed. Select the files again.");
        await api("/v1/assets/" + kind + "/" + entry.id, "POST", await file.arrayBuffer(), true);
      }
      pending = {pipeline:version.pipeline_id, request:{version_id:version.id,
        transactions_id:uploads.transactions.id, customers_id:uploads.customers.id,
        idempotency_key:crypto.randomUUID()}};
      savePending(); await submitPending(); uploads = {};
      notice("Fresh batch accepted with an immutable version. Refresh to inspect recorded results.");
    } catch (e) { notice(e.message + (pending ? ". Use Retry saved batch request; do not resubmit new identities." : ""),true); }
    $("batch-retry").hidden = !pending; await refreshVersion().catch(e => notice(e.message,true));
  });
  $("batch-retry").addEventListener("click", async () => {
    if (!pending) return;
    try { savePending(); await submitPending(); $("batch-retry").hidden = true; }
    catch(e) { notice(e.message,true); }
  });
  $("batch-refresh").addEventListener("click", () => refreshBatch().catch(e=>notice(e.message,true)));
  $("batch-cancel").addEventListener("click", async () => {
    try { await api("/v1/jobs/" + batch + "/cancel", "POST"); await refreshBatch(); }
    catch(e) { notice(e.message,true); }
  });
  async function resume() {
    if (!currentSession()) return;
    const url = new URL(location.href), v = url.searchParams.get("version"), b = url.searchParams.get("batch");
    if (v && uuid.test(v)) { version = {id:v}; await refreshVersion(); }
    if (b && uuid.test(b)) { batch = b; await refreshBatch(); }
    const raw = sessionStorage.getItem("proofflow.pending-batch");
    if (raw && raw.length <= 2048) {
      const p = JSON.parse(raw), session = currentSession();
      if (p && Object.keys(p).sort().join() === "expires,pipeline,request,workspace" &&
          p.workspace === session.workspace_id && p.expires === session.expires_at &&
          Date.parse(p.expires) > Date.now() && uuid.test(p.pipeline) && p.request &&
          Object.keys(p.request).sort().join() === "customers_id,idempotency_key,transactions_id,version_id" &&
          Object.values(p.request).every(value => typeof value === "string" && uuid.test(value))) {
        pending = {pipeline:p.pipeline,request:p.request}; $("batch-retry").hidden = false;
        $("batch-start").disabled = true;
        notice("A saved batch request needs explicit retry. No request was submitted on reload.");
      }
    }
  }
  return {reset, resume, repair(id,state) { repair=id; $("version-prepare").disabled=state!=="AWAITING_APPROVAL"; }};
}
