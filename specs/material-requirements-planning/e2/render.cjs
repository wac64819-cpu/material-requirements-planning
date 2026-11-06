const fs=require('fs');const path=require('path');
const deps="C:\\Users\\\u8bb8yq\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules";
const {instance}=require(path.join(deps,'@viz-js/viz/dist/viz.cjs'));
const sharp=require(path.join(deps,'sharp'));
(async()=>{const root=__dirname;const model=JSON.parse(fs.readFileSync(path.join(root,'model.json'),'utf8'));const viz=await instance();
for(const [id,fig] of Object.entries(model.figures)){const svg=viz.renderString(fig.dot,{format:'svg',engine:'dot'});fs.writeFileSync(path.join(root,'diagrams',id+'.svg'),svg);fs.writeFileSync(path.join(root,'diagrams',id+'.dot'),fig.dot);await sharp(Buffer.from(svg),{density:150}).png().toFile(path.join(root,'diagrams',id+'.png'));}
console.log('Rendered '+Object.keys(model.figures).length+' diagrams.');})().catch(e=>{console.error(e);process.exit(1)});
