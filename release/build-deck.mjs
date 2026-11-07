// Offline document authoring only. Uses the supplied Artifact Tool runtime.
// No cloud API, candidate execution, publication, or secret access.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const [root, workspace, evidence] = process.argv.slice(2).map(p => path.resolve(p));
const modules = process.env.RUNTIME_NODE_MODULES;
const skill = process.env.PROOFFLOW_PRESENTATION_SKILL;
const python = process.env.PROOFFLOW_DOCUMENT_PYTHON;
if (!modules || !skill || !python) throw new Error('Bundled document runtime paths required');
const require = createRequire(import.meta.url);
const { Presentation, PresentationFile } = await import(pathToFileURL(
  require.resolve('@oai/artifact-tool', { paths: [modules] })).href);
const { finalizePresentation } = await import(pathToFileURL(
  path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const content = JSON.parse(await fs.readFile(path.join(root,'release/deck-content.json'),'utf8'));
const build = path.join(workspace,'.build-v4');
const out = path.join(workspace,'deliverables');
await fs.mkdir(build,{recursive:true});
await fs.mkdir(out,{recursive:true});
const P = Presentation.create({slideSize:{width:1280,height:720}});
P.theme.defaultFont='Arial';
const C = {ink:'#153239',teal:'#08776D',mint:'#81E6CF',paper:'#F2F6F4',muted:'#526B70'};

function text(slide,value,x,y,w,h,size=28,color=C.ink,bold=false) {
  const shape=slide.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},
    fill:'none',line:{fill:'none',width:0}});
  shape.text=value;
  shape.text.style={typeface:'Arial',fontSize:size,color,bold};
  return shape;
}
function slide(index,dark=false) {
  const s=P.slides.add();s.background.fill=dark?C.ink:C.paper;
  s.speakerNotes.text=content.slides[index].notes;
  if(index) text(s,content.slides[index].title,64,44,1152,85,48,dark?'#FFFFFF':C.ink,true);
  text(s,`${content.status}  ·  ${index+1} / 8`,64,676,1152,24,18,dark?C.mint:C.muted);
  return s;
}
function table(s,values,widths,{top=214,height=330,dark=false,size=24}={}) {
  const t=s.tables.add({rows:values.length,columns:values[0].length,left:64,top,
    width:1152,height,columnWidths:widths,values});
  t.borders.assign({fill:dark?'#375259':'#CDDBD5',width:1,style:'solid'});
  for(let r=0;r<values.length;r++) for(let c=0;c<values[0].length;c++) {
    const cell=t.getCell(r,c); cell.fill=r===0?C.teal:dark?C.ink:'#FFFFFF';
    cell.text.style={typeface:'Arial',fontSize:size,color:r===0||dark?'#FFFFFF':C.ink,
      bold:r===0};
  }
  return t;
}

// Text-only cover, matching the existing product palette; no synthetic event imagery.
let s=slide(0,true);
text(s,content.title,64,172,1152,120,96,C.mint,true);
text(s,content.subtitle,68,320,1050,80,44,'#FFFFFF');
text(s,'Vultr Agent Rush · Challenge 1: Blast Radius Zero',68,520,1100,50,26,'#FFFFFF');

s=slide(1);
text(s,'A merchant/customer join can preserve totals while changing who owns a transaction.',64,135,1152,70,28);
const screenshot=path.join(evidence,'phase6-9226e15095a441a48272c48e2ffe8f48-0.png');
const image=await fs.readFile(screenshot);
const imageHash=createHash('sha256').update(image).digest('hex');
const receipt=JSON.parse(await fs.readFile(path.join(evidence,
  'phase6-browser-9226e15095a441a48272c48e2ffe8f48.json')));
if(imageHash!==receipt.cases[0].screenshot_sha256) throw new Error('Source screenshot changed');
s.images.add({blob:image.buffer.slice(image.byteOffset,image.byteOffset+image.byteLength),
  contentType:'image/png',alt:'Actual synthetic wrong-owner witness; original result needs review',
  fit:'contain',position:{left:64,top:222,width:1035,height:438}});

s=slide(2);
const steps=[['01','Approve the contract','Define joins, units, duplicates and permitted exclusions.'],
 ['02','Inspect the original','Run in isolation; compare actual records with source-derived expectations.'],
 ['03','Request a bounded repair','Vultr proposes code; fresh execution and protected checks decide eligibility.'],
 ['04','Approve the exact version','Only the reviewed source, contract and evidence can activate.'],
 ['05','Process a fresh batch','Run again on different inputs and independently verify the result.']];
steps.forEach((a,i)=>{const y=157+i*94;text(s,a[0],64,y,70,58,34,C.teal,true);
 text(s,a[1],157,y,1050,38,29,C.ink,true);text(s,a[2],157,y+40,1050,45,23,C.muted);});

s=slide(3,true);
text(s,'Two Vultr Compute VMs. One fixed inference provider. Separate authority for each step.',64,140,1152,65,27,'#FFFFFF');
table(s,[['Component','Responsibility','Boundary'],
 ['Control VM','Web API, dispatcher, PostgreSQL','Durable jobs, budgets and exact approvals'],
 ['Vultr Serverless Inference','Propose a supported code repair','Model text never grants permissions'],
 ['Isolated worker VM','gVisor execution and byte capture','No candidate network or secrets'],
 ['Restricted verifier on control','Check records from collected bytes','Never runs candidate source']],
 [285,430,437],{dark:true,top:230,height:340,size:24});
text(s,'Only the trusted dispatcher can request inference or an approved external write.',64,602,1152,55,25,C.mint);

s=slide(4);
[['1','real Vultr call'],['3','fresh matching checks'],['1','new completed batch']].forEach((a,i)=>{
 const x=64+i*390;text(s,a[0],x,160,320,120,96,C.teal,true);
 text(s,a[1],x,291,340,70,29,C.ink,true);});
text(s,'Changed source → candidate + two protected canaries → exact test approval → different inputs',64,414,1152,90,30);
text(s,'Recorded 8 November KST. Automated synthetic approval; no new GitHub action.',64,540,1152,55,24,C.muted);
text(s,'$0.027853 reserved for this repair. Reservation is not a provider invoice.',64,601,1152,50,23,C.muted);

s=slide(5,true);
text(s,'Separate real loop test · no model call · no accepted result',64,141,1152,55,28,C.mint);
table(s,[['Observed worker receipt','Result'],['Runtime exit','Signal 9'],
 ['Output accepted','None'],['Cleanup','Confirmed'],['Kernel writers after termination','Absent']],
 [650,502],{top:225,height:310,dark:true,size:28});
text(s,'1 CPU · 768 MiB memory · zero swap. Candidate networking is denied.',64,568,1152,48,25,'#FFFFFF');
text(s,'Failed demo-script checks are preserved and reconciled against worker evidence.',64,625,1152,40,23,C.mint);

s=slide(6);
text(s,'24 cases × 4 approaches. All 96 predeclared jobs remain in the accounting.',64,141,1152,55,28);
table(s,content.comparison,[480,224,224,224],{top:222,height:310,size:25});
text(s,'The fixed rebuild performed best in this narrow supported contract.',64,561,1152,45,27,C.teal,true);
text(s,'One repeat; shared templates; no independent human oracle review. No AI superiority claim.',64,614,1152,50,23,C.muted);

s=slide(7);
text(s,'Small merchant revenue imports',64,155,700,60,38,C.teal,true);
text(s,'One Python file, pinned pandas, transaction/customer CSVs and an approved synthetic contract.',64,236,1080,100,32);
text(s,'Useful outcome',64,380,370,45,28,C.ink,true);
text(s,'Inspectable evidence before repaired code processes the next batch.',440,380,770,90,31);
text(s,'Current limits',64,510,370,45,28,C.ink,true);
text(s,'Private prototype. Customer value is a hypothesis. Public release, ownership clearance and full disaster recovery remain open.',440,510,770,120,25,C.muted);

for(let i=0;i<P.slides.items.length;i++) {
  const blob=await P.export({slide:P.slides.items[i],format:'png',scale:1.5});
  await fs.writeFile(path.join(build,`slide-${i+1}.png`),new Uint8Array(await blob.arrayBuffer()));
}
const cover=await P.export({slide:P.slides.items[0],format:'png',scale:1.5});
await fs.writeFile(path.join(out,'ProofFlow-cover-v4.png'),new Uint8Array(await cover.arrayBuffer()));
const draft=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(P)).save(draft);
const result=await finalizePresentation({workspaceDir:workspace,candidatePath:draft,
  finalPath:path.join(out,'ProofFlow-deck-v4.pptx'),pythonExecutable:python,
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  explicitTotalSlideCount:8,requiredNativeTableOwnerSlides:[4,6,7],
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry',
    '--validate-heading-fit','--require-native-table-slide','4','--require-native-table-slide','6',
    '--require-native-table-slide','7'],
  fontPolicy:{basis:'design',families:['Arial']},verifyArtifactToolImport:true,
  receiptPath:path.join(build,'validation.json')});
await fs.writeFile(path.join(build,'asset-provenance.json'),JSON.stringify({imageHash,
  sourceCheckpoint:content.source_checkpoint,authoring:'@oai/artifact-tool bundled runtime',
  actualScreenshot:true,generatedIllustrations:false},null,2));
console.log(JSON.stringify({completed:true,slides:8,outputs:out,validation:result}));
