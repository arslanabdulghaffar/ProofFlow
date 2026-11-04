import test from "node:test";
import assert from "node:assert/strict";
import {savePending, loadPending, parsePending, clearPending} from "../../api/app/static/recovery.js";
const workspace = "11111111-1111-1111-1111-111111111111";
const body = Object.fromEntries(["idempotency_key", "pipeline_id", "transactions_id", "customers_id", "contract_id"].map(k=>[k,workspace]));
const session = {workspace_id:workspace,expires_at:new Date(Date.now()+600000).toISOString()};
function storage(){const map=new Map();return {setItem:(k,v)=>map.set(k,v),getItem:k=>map.get(k)||null,removeItem:k=>map.delete(k)};}
test("reload preserves exact identity; logout removes it",()=>{const store=storage();savePending(store,session,body);assert.deepEqual(loadPending(store,session),body);clearPending(store,session);assert.equal(loadPending(store,session),null);});
test("foreign workspace, expired and mutated authority fail closed",()=>{const raw=JSON.stringify({workspace,expires:session.expires_at,body});assert.equal(parsePending(raw,"22222222-2222-2222-2222-222222222222",Date.now()),null);assert.equal(parsePending(raw,workspace,Date.now()+900000),null);assert.equal(parsePending(JSON.stringify({workspace,expires:session.expires_at,body:{...body,runtime:"attacker"}}),workspace,Date.now()),null);});
test("oversize, malformed, noncanonical IDs and unavailable storage fail before POST",()=>{for(const raw of ["x".repeat(2049),"null","[]","{",JSON.stringify({workspace,expires:session.expires_at,body:{...body,pipeline_id:"../path"}})])assert.equal(parsePending(raw,workspace,Date.now()),null);assert.throws(()=>savePending({setItem:()=>{throw new Error("storage denied")}},session,body));});
