// Standalone cover uses editable slide text, exported locally; no cloud generation.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(import.meta.url);
const {Presentation}=await import(pathToFileURL(require.resolve('@oai/artifact-tool',
  {paths:[process.env.RUNTIME_NODE_MODULES]})).href);
const [destination]=process.argv.slice(2);
const p=Presentation.create({slideSize:{width:1280,height:720}});
p.theme.defaultFont='Arial';
const s=p.slides.add();s.background.fill='#153239';
for(const [value,y,size,color,height] of [
  ['ProofFlow',172,96,'#81E6CF',120],
  ['Checked repairs before the next batch',320,44,'#FFFFFF',80],
  ['Vultr Agent Rush · Challenge 1: Blast Radius Zero',520,26,'#FFFFFF',50],
  ['Private preview · synthetic data',676,18,'#81E6CF',24]]) {
  const sh=s.shapes.add({geometry:'textbox',position:{left:64,top:y,width:1152,height},
    fill:'none',line:{fill:'none',width:0}});
  sh.text=value;sh.text.style={typeface:'Arial',fontSize:size,color,bold:size===96};
}
const image=await p.export({slide:s,format:'png',scale:1.5});
await fs.writeFile(path.resolve(destination),new Uint8Array(await image.arrayBuffer()),{flag:'wx'});
console.log('Standalone1920x1080 cover exported');
