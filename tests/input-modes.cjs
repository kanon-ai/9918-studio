const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('web/app.js','utf8');
const a={width:2,frames:[{pixels:[3,4]}]};
const c={asset:()=>a,selected:'a',frame:0,tool:'pencil',togglePixels:new Map(),draw(){},line(x,y,xx,yy,put){put(x,y)},drawing:null};
vm.createContext(c);
vm.runInContext(src.slice(src.indexOf('function drawGesture('),src.indexOf("canvas.addEventListener('contextmenu'")),c);
vm.runInContext(src.slice(src.indexOf('function clearRepeatClick('),src.indexOf("document.addEventListener('pointerdown'")),c);
function click(button,color){c.drawing={toggle:true,visited:new Set(),button,color,last:{x:0,y:0}};c.drawGesture({x:0,y:0});}
click(0,7);assert.equal(a.frames[0].pixels[0],7);
c.drawGesture({x:0,y:0});assert.equal(a.frames[0].pixels[0],7);
click(0,7);assert.equal(a.frames[0].pixels[0],3);
click(2,12);assert.equal(a.frames[0].pixels[0],12);
click(2,12);assert.equal(a.frames[0].pixels[0],3);
click(0,7);c.drawing=null;c.clearRepeatClick();click(0,7);assert.equal(a.frames[0].pixels[0],7);
assert.equal(a.frames[0].pixels[1],4);
console.log('PASS left/right restoration, drag revisit, invalidation and unchanged neighbors');
