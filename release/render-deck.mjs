// Read-only final-file rendering for visual QA; no external service calls.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const require=createRequire(import.meta.url);
const {FileBlob,PresentationFile}=await import(pathToFileURL(require.resolve(
  '@oai/artifact-tool',{paths:[process.env.RUNTIME_NODE_MODULES]})).href);
const [file,destination]=process.argv.slice(2).map(p=>path.resolve(p));
await fs.mkdir(destination,{recursive:true});
const deck=await PresentationFile.importPptx(await FileBlob.load(file));
for(let i=0;i<deck.slides.items.length;i++){
  const png=await deck.export({slide:deck.slides.items[i],format:'png',scale:1});
  await fs.writeFile(path.join(destination,`slide-${i+1}.png`),
    new Uint8Array(await png.arrayBuffer()));
}
console.log(JSON.stringify({finalFileRendered:true,slides:deck.slides.items.length}));
