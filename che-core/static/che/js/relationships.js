/* CHE relationship graph: no dependency on CAP's alert editor.
 * Current schema permits a single parent UUID per event. All edges represent
 * recorded references, not proof of causation. SVG labels use textContent.
 *
 * Step 129: SVG camera supports zoom, fit and background drag-to-pan.
 * This changes presentation only: CHE records, filters and graph semantics
 * remain unchanged. All DOM labels use textContent / Option, not innerHTML.
 */
(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const byId = new Map();
  const children = new Map();
  const $ = id => document.getElementById(id);
  let focusId = null;
  let matchingIds = new Set();
  const filterNames = ['originator','year','event_type','status'];
  const filterControl = key => $('filter-'+key);
  function matches(e) {
    const q=$('search').value.trim().toLowerCase();
    return (!filterControl('originator').value || e.originator===filterControl('originator').value)
      && (!filterControl('year').value || String(e.start||'').slice(0,4)===filterControl('year').value)
      && (!filterControl('event_type').value || e.event_type_value===filterControl('event_type').value)
      && (!filterControl('status').value || e.status===filterControl('status').value)
      && (!q || [e.id,e.event_type,e.hazard_specification,e.originator,e.description,e.status].some(v=>String(v||'').toLowerCase().includes(q)));
  }
  function setupChoices(options) {
    for (const [key, list] of Object.entries({
      originator:(options.originators||[]).map(x=>({value:x,label:x})),
      year:(options.years||[]).map(x=>({value:String(x),label:String(x)})),
      event_type:options.event_types||[],status:options.statuses||[]
    })) {
      const sel=filterControl(key), value=sel.value;
      for (const opt of list) sel.add(new Option(opt.label,opt.value));
      sel.value=value;
    }
  }
  const svg = $('network');
  const createSvg = (tag, attrs = {}) => {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
    return el;
  };
  const short = (s, n=21) => String(s || '').length > n ? String(s).slice(0,n-1) + '…' : String(s || '');
  const title = e => e ? `${e.event_type} — ${e.hazard_specification || e.originator}` : 'Unresolved linked UUID';
  const highlight = e => e ? (e.is_synthetic ? '#267d94' : '#205a86') : '#7e8793';

  // Camera uses an SVG viewBox, not CSS transforms. The existing nodes remain
  // keyboard-focusable and clickable, while the background can be dragged.
  let sceneWidth = 1100, sceneHeight = 600;
  let camera = {x:0, y:0, w:1100, h:600};
  let drag = null;
  const applyCamera = () => {
    svg.setAttribute('viewBox', `${camera.x} ${camera.y} ${camera.w} ${camera.h}`);
  };
  const fitCamera = () => {
    const padding = 50;
    camera = {x:-padding, y:-padding, w:sceneWidth+2*padding, h:sceneHeight+2*padding};
    applyCamera();
  };
  const readableCamera = (hierarchical) => {
    if (!hierarchical || sceneWidth<=1100) {fitCamera();return;}
    // Initial hierarchy camera prioritizes readable node labels. The complete
    // tree can always be seen with Fit; drag or wheel to explore portions.
    const w=1100, h=600;
    camera={x:(sceneWidth-w)/2, y:Math.max(-30,(sceneHeight-h)/2), w, h};
    applyCamera();
  };
  const zoomAt = (factor, anchor) => {
    const nextW=Math.min(Math.max(camera.w*factor, 220), Math.max(6000, sceneWidth*2));
    const ratio=nextW/camera.w;
    const point=anchor||{x:camera.x+camera.w/2,y:camera.y+camera.h/2};
    camera={x:point.x-(point.x-camera.x)*ratio,
      y:point.y-(point.y-camera.y)*ratio, w:nextW, h:camera.h*ratio};
    applyCamera();
  };
  const svgPoint = event => {
    const transform=svg.getScreenCTM();
    if (!transform) return null;
    const point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;
    const result=point.matrixTransform(transform.inverse());
    return {x:result.x,y:result.y};
  };
  const visual = svg.closest('.visual');
  if (visual) {
    const toolbar=document.createElement('div');
    toolbar.className='che-zoom-toolbar';
    toolbar.setAttribute('role','group');
    toolbar.setAttribute('aria-label','Network zoom controls');
    const actions=[
      ['+','Zoom in',()=>zoomAt(0.8)],
      ['−','Zoom out',()=>zoomAt(1.25)],
      ['Fit to screen','Fit whole diagram',fitCamera]
    ];
    for(const [label,tooltip,action] of actions){
      const button=document.createElement('button');
      button.type='button';button.textContent=label;button.title=tooltip;
      button.setAttribute('aria-label',tooltip);
      button.addEventListener('click',action);toolbar.append(button);
    }
    const instruction=document.createElement('span');
    instruction.textContent='Scroll to zoom · Drag empty space to pan';
    toolbar.append(instruction);
    visual.insertBefore(toolbar,svg);
    const style=document.createElement('style');
    style.textContent=`
      .che-zoom-toolbar{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:9px}
      .che-zoom-toolbar button{background:#fff;color:#183044;border:1px solid #9bb3c4;border-radius:6px;padding:7px 12px;font:600 13px system-ui,sans-serif;cursor:pointer}
      .che-zoom-toolbar button:hover,.che-zoom-toolbar button:focus-visible{background:#e6f2f8;outline:2px solid #88b9d5;outline-offset:1px}
      .che-zoom-toolbar span{color:#536e7b;font-size:12px;margin-left:auto}
      #network{touch-action:none;cursor:grab;min-width:0!important}
      #network.che-panning{cursor:grabbing}
      #network .node{cursor:pointer}
    `;
    document.head.append(style);
  }
  svg.addEventListener('wheel',event=>{
    if (!focusId) return;
    event.preventDefault();
    const anchor=svgPoint(event);
    const factor=event.deltaY>0 ? 1.12 : 1/1.12;
    zoomAt(factor,anchor);
  },{passive:false});
  svg.addEventListener('pointerdown',event=>{
    if(event.button!==0 || event.target.closest('.node'))return;
    drag={id:event.pointerId,x:event.clientX,y:event.clientY};
    svg.setPointerCapture(event.pointerId);
    svg.classList.add('che-panning');
  });
  svg.addEventListener('pointermove',event=>{
    if(!drag || drag.id!==event.pointerId)return;
    // Preserve SVG aspect ratio when converting pixel drags to SVG units.
    const box=svg.getBoundingClientRect();
    const scale=Math.min(box.width/camera.w,box.height/camera.h);
    if(!scale)return;
    camera.x-=(event.clientX-drag.x)/scale;
    camera.y-=(event.clientY-drag.y)/scale;
    drag.x=event.clientX;drag.y=event.clientY;
    applyCamera();
  });
  const endPan=()=>{drag=null;svg.classList.remove('che-panning');};
  svg.addEventListener('pointerup',endPan);
  svg.addEventListener('pointercancel',endPan);
  svg.addEventListener('lostpointercapture',endPan);

  function describe(id) {
    const e = byId.get(id);
    $('detail').replaceChildren();
    const h = document.createElement('h2'); h.textContent = e ? title(e) : 'Unresolved reference'; $('detail').append(h);
    const dl = document.createElement('dl');
    const entries = e ? [['UUID',e.id], ['Status',e.status], ['Originator',e.originator], ['Start',e.start], ['Linked parent', e.parent || 'None'], ['Description',e.description], ['Synthetic',e.is_synthetic ? 'Yes — test only' : 'No indicator']] : [['UUID',id], ['Note','The referenced event is not present in this catalogue.']];
    for (const [key,val] of entries) { const dt=document.createElement('dt');dt.textContent=key;const dd=document.createElement('dd');dd.textContent=val || '—';dl.append(dt,dd); }
    $('detail').append(dl);
  }
  function center(id, updateUrl=true) {
    if (!id) return;
    focusId=id;
    if (byId.has(id)) $('event-select').value=id;
    if (updateUrl) history.replaceState(null,'', '?event='+encodeURIComponent(id));
    render();
  }
  function neighbors(id) {
    const e = byId.get(id);
    const pairs = [];
    if (e?.parent) pairs.push([e.parent,id]);
    for (const child of children.get(id) || []) pairs.push([id,child]);
    return pairs;
  }
  function render() {
    if (!focusId) return;
    const maxDepth=Number($('depth').value), levels=new Map([[focusId,0]]), edgeSet=new Set(), queue=[focusId];
    while(queue.length) {
      const id=queue.shift(), d=levels.get(id);
      if(d>=maxDepth) continue;
      for(const [from,to] of neighbors(id)) {
        edgeSet.add(from+'|'+to);
        const other=from===id ? to : from;
        if(!levels.has(other)) {levels.set(other,d+1); queue.push(other);}
      }
    }
    const ids=[...levels.keys()];
    const edgePairs=[...edgeSet].map(s=>s.split('|')).filter(([a,b])=>levels.has(a)&&levels.has(b));
    const hierarchical=$('layout').value==='levels';
    // Widen hierarchy rather than squeezing 20 children into 1100 pixels.
    sceneWidth=1100;sceneHeight=600;
    const positions=new Map();
    if(hierarchical) {
      const groups=new Map(); for(const id of ids){const level=levels.get(id);if(!groups.has(level))groups.set(level,[]);groups.get(level).push(id);}
      const count=groups.size, widest=Math.max(...[...groups.values()].map(g=>g.length));
      sceneWidth=Math.max(1100,widest*172+170);
      sceneHeight=Math.max(600,count*145+90);
      for(const [level, group] of groups){group.forEach((id,i)=>positions.set(id,{x:sceneWidth/2+(i-(group.length-1)/2)*172,y:90+level*145}));}
    } else {
      positions.set(focusId,{x:550,y:300});
      const others=ids.filter(id=>id!==focusId);
      others.forEach((id,i)=>{const angle=2*Math.PI*i/Math.max(1,others.length)-Math.PI/2;const radius= Math.min(245,155+(levels.get(id)-1)*80);positions.set(id,{x:550+radius*Math.cos(angle),y:300+radius*Math.sin(angle)});});
    }
    svg.style.minWidth='0';
    svg.replaceChildren();
    const defs=createSvg('defs');const marker=createSvg('marker',{id:'edgeArrow',markerWidth:10,markerHeight:10,refX:8,refY:3,orient:'auto',markerUnits:'strokeWidth'});marker.append(createSvg('path',{d:'M0,0 L0,6 L9,3 z',fill:'#73899c'}));defs.append(marker);svg.append(defs);
    for(const [a,b] of edgePairs){const p=positions.get(a),q=positions.get(b);if(!p||!q||a===b)continue;
      const dx=q.x-p.x,dy=q.y-p.y,len=Math.hypot(dx,dy)||1;
      const edge=createSvg('line',{x1:p.x+dx/len*66,y1:p.y+dy/len*25,x2:q.x-dx/len*66,y2:q.y-dy/len*25,class:'edge','marker-end':'url(#edgeArrow)'});svg.append(edge);
    }
    for(const id of ids){const e=byId.get(id),p=positions.get(id);if(!p)continue;
      const g=createSvg('g',{class:'node',tabindex:0,role:'button','aria-label':title(e)});g.append(createSvg('rect',{x:p.x-68,y:p.y-27,width:136,height:54,rx:9,fill:id===focusId?'#16436e':(e && !matchingIds.has(id) ? '#8b9aaa' : highlight(e)),stroke:id===focusId?'#e2b453':'none','stroke-width':3}));
      const label=createSvg('text',{x:p.x,y:p.y-2,'text-anchor':'middle',class:'node-label'});label.textContent=short(e?.event_type||'Unresolved UUID',18);g.append(label);
      const sub=createSvg('text',{x:p.x,y:p.y+14,'text-anchor':'middle',class:'node-sub'});sub.textContent=short(e?.originator||id.slice(0,14),21);g.append(sub);
      g.addEventListener('click',()=>center(id));g.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();center(id);}});svg.append(g);
    }
    readableCamera(hierarchical);
    $('summary').textContent=`${matchingIds.size} matching events · ${ids.length} visible events/references (including connections) · ${edgePairs.length} recorded links · ${byId.size} catalogue events`;
    describe(focusId);
  }
  function updateResults() {
    const sel=$('event-select'), previous=sel.value;
    const matchesList=[...byId.values()].filter(matches).sort((a,b)=>a.event_type.localeCompare(b.event_type));
    matchingIds=new Set(matchesList.map(e=>e.id));
    sel.replaceChildren();
    for (const e of matchesList) {
      const opt=new Option(short(title(e),72)+' · '+e.id.slice(0,8),e.id);
      sel.add(opt);
    }
    if (matchesList.length) {
      const selected=matchingIds.has(previous) ? previous : matchesList[0].id;
      sel.value=selected;
      if (!matchingIds.has(focusId)) center(selected,false);
      else render();
    } else {
      sel.add(new Option('No matching events',''));
      $('summary').textContent='0 matching events · Clear filters to explore the network';
      svg.replaceChildren();
      $('detail').replaceChildren();
    }
  }
  fetch(window.CHE_RELATIONSHIPS_URL,{credentials:'same-origin'}).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}).then(data=>{
    for(const e of data.events||[]){byId.set(e.id,e);if(e.parent){if(!children.has(e.parent))children.set(e.parent,[]);children.get(e.parent).push(e.id);}}
    setupChoices(data.filters||{});
    const desired=new URLSearchParams(location.search).get('event');
    const cyclone=[...byId.values()].find(e=>e.parent===null&&/tropical cyclone/i.test(e.event_type));
    focusId=byId.has(desired)?desired:(cyclone?.id || [...byId.keys()][0]);
    updateResults();
    $('search').addEventListener('input',updateResults);
    for(const key of filterNames) filterControl(key).addEventListener('change',updateResults);
    $('clear-filters').addEventListener('click',()=>{ $('search').value=''; for(const key of filterNames)filterControl(key).value='';updateResults(); });
    $('event-select').addEventListener('change',e=>center(e.target.value));
    $('depth').addEventListener('change',render);$('layout').addEventListener('change',render);
  }).catch(err=>{$('summary').textContent='Unable to load event relationships: '+err.message;});
})();
