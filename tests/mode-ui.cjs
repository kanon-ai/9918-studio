const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('web/app.js','utf8');const fn=src.slice(src.indexOf('function colorGroups('),src.indexOf('function modeWorkspace('));const context={};vm.createContext(context);vm.runInContext(fn,context);
function groups(enc,w,h,ti=0,sprite=false){const pixels=Array.from({length:w*h},(_,i)=>i%4);return context.colorGroups({width:w,height:h,frames:[{pixels}]},{encoding:enc,kind:sprite?'sprite':'character'},ti,0)}
assert.equal(groups('text',12,16)[0].indices.length,192);
const g1=groups('g1',24,32,7)[0];assert.equal(g1.indices.length,512);assert.equal(new Set(g1.indices).size,512);assert(g1.indices.includes(16*24+15));assert(!g1.indices.includes(16*24+16));
const g2=groups('g2',16,16,3);assert.equal(g2.length,8);assert.equal(g2[0].indices.join(','),'136,137,138,139,140,141,142,143');assert.equal(g2[7].indices[7],255);
const sp=groups('sp2',16,16,0,true);assert.equal(sp.length,16);assert(sp.every(g=>!g.colors.includes(0)));assert.equal(groups('sp1',16,16,0,true)[0].indices.length,256);
assert.equal(groups('tile4',16,16).length,0);console.log('PASS: TEXT scope, G1 shared group crossing atlas rows, G2 isolated row, sprite transparency, tile4 independent pixels');
const swapSource=src.slice(src.indexOf('function tileSwapPoints('),src.indexOf('function clearTileDrag('));vm.runInContext(swapSource,context);
for(const tw of [6,8]){
 const a={width:tw*3,height:16,frames:[{pixels:Array.from({length:tw*3*16},(_,i)=>i)},{pixels:Array(tw*3*16).fill(7)}]};
 const before=a.frames[0].pixels.slice(),other=a.frames[1].pixels.slice();const points=context.tileSwapPoints(a,tw,1,5,0);assert.equal(points.length,tw*8*2);
 for(const p of points)a.frames[0].pixels[p.y*a.width+p.x]=p.color;
 for(let i=0;i<before.length;i++){const x=i%a.width,y=Math.floor(i/a.width),tile=Math.floor(y/8)*3+Math.floor(x/tw);if(tile!==1&&tile!==5)assert.equal(a.frames[0].pixels[i],before[i]);}
 assert.deepEqual(a.frames[1].pixels,other);
 for(const p of context.tileSwapPoints(a,tw,1,5,0))a.frames[0].pixels[p.y*a.width+p.x]=p.color;
 assert.deepEqual(a.frames[0].pixels,before);assert.equal(context.tileSwapPoints(a,tw,1,1,0).length,0);assert.throws(()=>context.tileSwapPoints(a,tw,-1,5,0));
}
console.log('PASS: 6x8/8x8 tile swaps across rows, round trip, untouched neighbors/frames, same-tile no-op, invalid bounds');
// Exercise Ctrl at drop time, including changing the modifier during a drag.
(async()=>{
 const dragContext={};vm.createContext(dragContext);
 vm.runInContext(src.slice(src.indexOf('function tileSwapPoints('),src.indexOf('function modeWorkspace(')),dragContext);
 const controls={};let working,submitted;
 Object.assign(dragContext,{pending:false,drawing:null,selected:'test',frame:0,state:{revision:1},tileDrag:null,
  $$:()=>[],$:id=>controls[id]??(controls[id]={}),stopPlay:()=>{},mode:()=>({encoding:'g2'}),asset:()=>working,modeWorkspace:()=>{},fitCanvas:()=>{},notify:()=>{},
  mutate:async body=>{submitted=body;for(const p of body.points)working.frames[0].pixels[p.y*16+p.x]=p.color;return true}});
 const button=()=>({dataset:{},classList:{add(){},remove(){}}});
 const event=ctrlKey=>({ctrlKey,preventDefault(){},stopPropagation(){},dataTransfer:{setData(){}}});
 for(const copy of [true,false]){
  working={width:16,height:8,frames:[{pixels:Array.from({length:128},(_,i)=>i%16<8?2:7)}]};
  const from=button(),to=button();dragContext.bindTileDrag(from,0);dragContext.bindTileDrag(to,1);
  const start=event(!copy);from.ondragstart(start);assert.equal(start.dataTransfer.effectAllowed,'copyMove');
  const over=event(copy);to.ondragover(over);assert.equal(over.dataTransfer.dropEffect,copy?'copy':'move');
  await to.ondrop(event(copy));assert.equal(submitted.action,'pixels');assert.equal(submitted.points.length,copy?64:128);
  for(let i=0;i<128;i++)assert.equal(working.frames[0].pixels[i],i%16<8?(copy?2:7):2);
 }
 console.log('PASS: Ctrl-at-drop copy preserves source, normal drop swaps, cursor effect tracks Ctrl');
})().catch(e=>{console.error(e);process.exitCode=1});
