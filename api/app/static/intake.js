// Private browser client. All execution, approval and evidence authority stays on the server.
const $ = id => document.getElementById(id);
const kinds = ["pipeline", "transactions", "customers", "contract"];
const limits = {pipeline:16384, transactions:5242880, customers:5242880, contract:32768};
const terminal = new Set(["NEEDS_REVIEW", "FAILED_INFRA", "CANCELLED"]);
const names = {QUEUED:"Queued", BASELINE_RUNNING:"Running original", BASELINE_VERIFYING:"Verifying output", RECONCILING:"Reconciling execution", NEEDS_REVIEW:"Needs review", FAILED_INFRA:"Execution failed", CANCELLED:"Cancelled"};
const explanations = {match:"The original matched these inputs. No version has been activated.", mismatch:"The original output violates your approved contract. Inspect the differences below.", held:"Source data has unresolved problems. The batch remains held.", input_rejected:"These inputs could not be prepared under the contract. No pipeline executed.", infrastructure_failed:"The run failed. No verified result was published.", cancelled:"Cancellation and cleanup are recorded."};
let session, assets = {}, uploadIds = {}, approved = false, requestBody = null, job = null, stream = null, lastEvent = 0n;
function lockFiles(locked) { for(const kind of kinds) $(kind).disabled=locked; }
function notice(text, error=false) { $("notice").textContent=text; $("notice").dataset.error=String(error); }
function csrf() { return document.cookie.split("; ").find(v=>v.startsWith("__Host-proofflow-csrf="))?.split("=")[1] || ""; }
async function api(path, method="GET", data, raw=false) {
  const headers = method === "GET" ? {} : {"X-Proofflow-CSRF":csrf()};
  if (data !== undefined && !raw) headers["Content-Type"]="application/json";
  const response=await fetch(path,{method,headers,body:data===undefined?undefined:raw?data:JSON.stringify(data),credentials:"same-origin",cache:"no-store",redirect:"error"});
  if (!response.ok) { const value=await response.json().catch(()=>({})); throw new Error((value.error?.code||"REQUEST_FAILED")+(value.error?.request_id?" · request "+value.error.request_id:"")); }
  return response.status===204 ? null : response.json();
}
async function refreshSession() {
  try { const current=await api("/v1/session");if(session&&session.workspace_id!==current.workspace_id)resetWorkspace();session=current; $("access").hidden=true; $("workspace").hidden=false;
    $("identity").textContent="Workspace "+session.workspace_id+" · access expires "+new Date(session.expires_at).toLocaleString();
    notice("Private workspace connected. Use synthetic data only.");
  } catch { resetWorkspace();session=null; $("access").hidden=false; $("workspace").hidden=true; notice("Open your provisioned workspace to begin."); }
}
function resetWorkspace(){stream?.close();stream=null;assets={};uploadIds={};approved=false;requestBody=null;job=null;lastEvent=0n;$("files").reset();for(const kind of kinds)invalidate(kind);$("job").hidden=true;$("confirm-delete").checked=false;$("delete").disabled=true;$("upload-status").textContent="";}
$("login").addEventListener("submit",async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;
  try { await api("/v1/session/import","POST",{session_token:$("session-token").value,csrf_token:$("csrf-token").value}); $("login").reset(); await refreshSession(); }
  catch(error){notice(error.message,true);}finally{button.disabled=false;}
});
function invalidate(kind) { delete assets[kind]; delete uploadIds[kind]; requestBody=null; $("retry").hidden=true; $("run").disabled=true;
  if(kind==="contract"){approved=false;$("confirm-contract").checked=false;$("confirm-contract").disabled=true;$("approve").disabled=true;$("contract-preview").textContent="Upload the new contract before approval.";$("contract-hash").textContent="";$("approval-status").textContent="No contract approved.";}
}
for(const kind of kinds) $(kind).addEventListener("change",()=>invalidate(kind));
$("files").addEventListener("submit",async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;lockFiles(true);
  try { for(const kind of kinds){const file=$(kind).files[0]; if(!file||file.size<1||file.size>limits[kind])throw new Error("Check the file and byte limit for "+kind+".");}
    for(const kind of kinds){if(assets[kind])continue;const file=$(kind).files[0]; uploadIds[kind] ||= crypto.randomUUID();const result=await api("/v1/assets/"+kind+"/"+uploadIds[kind],"POST",file,true);assets[kind]=result;
      $("upload-status").textContent="Stored "+kind+" · "+result.bytes+" bytes.";
      if(kind==="contract"){ $("contract-preview").textContent=await file.text(); $("contract-hash").textContent="Exact source SHA-256: "+result.sha256;$("confirm-contract").disabled=false; }
    } $("run").disabled=!approved;notice("Inputs stored. Review and explicitly approve the exact contract.");
  }catch(error){notice(error.message,true);}finally{button.disabled=false;lockFiles(false);}
});
$("confirm-contract").addEventListener("change",()=>{$("approve").disabled=!$("confirm-contract").checked||!assets.contract;});
$("approve").addEventListener("click",async()=>{$("approve").disabled=true;lockFiles(true);
  try{if(!$("confirm-contract").checked||!assets.contract)return; await api("/v1/contracts/"+assets.contract.asset_id+"/approve","POST",{expected_sha256:assets.contract.sha256,confirm:true}); approved=true;$("approval-status").textContent="This exact contract is approved.";$("run").disabled=!kinds.every(k=>assets[k]);notice("Contract approved. Ready for the original run.");}
  catch(error){notice(error.message,true);$("approve").disabled=false;}finally{lockFiles(false);}
});
async function submitJob(){ $("run").disabled=true;$("retry").hidden=true;
  try{if(!requestBody){if(!approved||!kinds.every(k=>assets[k]))throw new Error("Upload and approve first.");requestBody={idempotency_key:crypto.randomUUID()};for(const kind of kinds)requestBody[kind+"_id"]=assets[kind].asset_id;}
    const result=await api("/v1/jobs","POST",requestBody);job=result.job_id;lastEvent=0n;$("events").replaceChildren();history.replaceState(null,"","/?job="+job);await refreshJob();watch();
  }catch(error){notice(error.message+". The result may be uncertain; retry keeps the same request identity.",true);$("retry").hidden=false;}
}
$("run").addEventListener("click",submitJob);$("retry").addEventListener("click",submitJob);
async function refreshJob(){if(!job)return;const value=await api("/v1/jobs/"+job+"/summary");if(value.wire_version!=="proofflow-browser-v1"||!names[value.state])throw new Error("Unsupported response version.");
  $("job").hidden=false;$("job-id").textContent="Job "+job;$("state").textContent=names[value.state];$("run-status").textContent="Recorded state, updated from the server. Refreshing never resubmits a job.";$("blocked").textContent=value.blocking_occurrences??"—";$("finding-count").textContent=value.finding_count??"—";$("outcome").textContent=explanations[value.outcome]||"Waiting for execution and independent comparison.";$("cancel").disabled=terminal.has(value.state);$("evidence-link").href="/jobs/"+job;
  $("witnesses").replaceChildren();for(const witness of value.ownership_witnesses){const row=document.createElement("tr");for(const key of ["merchant_id","customer_id","expected_owner","actual_owner"]){const cell=document.createElement("td");cell.textContent=witness[key];row.append(cell);}$("witnesses").append(row);}
  $("findings").replaceChildren();for(const finding of value.findings){const li=document.createElement("li");li.textContent=finding.check+" · "+finding.code;$("findings").append(li);}
  if(terminal.has(value.state)){stream?.close();stream=null;}return value;
}
function watch(){stream?.close();if(!job||$("cancel").disabled)return;stream=new EventSource("/v1/jobs/"+job+"/events");
  stream.addEventListener("job_state",event=>{try{const value=JSON.parse(event.data);if(!/^(0|[1-9][0-9]{0,18})$/.test(value.sequence)||!names[value.state])throw new Error("Invalid event.");const seq=BigInt(value.sequence);if(seq<=lastEvent)return;lastEvent=seq;const li=document.createElement("li");li.textContent=value.occurred_at+" · "+names[value.state];$("events").append(li);refreshJob().catch(error=>notice(error.message,true));}catch(error){stream?.close();notice(error.message,true);}});
  stream.addEventListener("stream_closed",()=>{stream?.close();notice("Event access ended. Sign in again or refresh the recorded status.",true);});
  stream.onerror=()=>{refreshJob().catch(error=>notice(error.message,true));};
}
$("refresh").addEventListener("click",()=>refreshJob().catch(error=>notice(error.message,true)));
$("cancel").addEventListener("click",async()=>{try{await api("/v1/jobs/"+job+"/cancel","POST");notice("Cancellation requested. Waiting for confirmed cleanup.");await refreshJob();}catch(error){notice(error.message,true);}});
$("logout").addEventListener("click",async()=>{try{await api("/v1/logout","POST");stream?.close();await refreshSession();}catch(error){notice(error.message,true);}});
$("confirm-delete").addEventListener("change",()=>{$("delete").disabled=!$("confirm-delete").checked;});
$("delete").addEventListener("click",async()=>{if(!session||!$("confirm-delete").checked)return;try{await api("/v1/workspace/delete","POST",{workspace_id:session.workspace_id,confirm:true});stream?.close();await refreshSession();notice("Access revoked. Byte deletion is queued and waits for safe execution cleanup.");}catch(error){notice(error.message,true);}});
await refreshSession();const query=new URL(location.href).searchParams.get("job");if(session&&query&&/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(query)){job=query;await refreshJob().then(watch).catch(error=>notice(error.message,true));}
