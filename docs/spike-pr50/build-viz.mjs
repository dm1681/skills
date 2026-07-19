// Build a self-contained HTML visualization from the REAL spike output (graph.json).
import { readFileSync, writeFileSync } from "node:fs";

const g = JSON.parse(readFileSync(new URL("./graph.json", import.meta.url)));

// ---- compact the data: index nodes, rewrite edges to [srcIdx,tgtIdx,crossPkg] ----
const idx = new Map(g.nodes.map((n, i) => [n.id, i]));
const KIND = {
  FunctionDeclaration: "fn", MethodDeclaration: "method", ClassDeclaration: "class",
  InterfaceDeclaration: "interface", TypeAliasDeclaration: "type",
  EnumDeclaration: "enum", VariableDeclaration: "const",
};
const PKG = { "apps/web": 0, "apps/server": 1, "packages/contracts": 2 };
const nodes = g.nodes.map((n) => ({
  n: n.name, k: KIND[n.kind] ?? n.kind, p: PKG[n.pkg], f: n.file,
  l: n.layer, d: n.degree, c: n.cohort,
}));
const edges = g.edges.map((e) => [idx.get(e.source), idx.get(e.target), e.crossPkg ? 1 : 0]);
const data = { meta: g.meta, nodes, edges };

// ---- build the static "layered walkthrough" (the product preview) in Node ----
const PKG_NAME = ["apps/web", "apps/server", "packages/contracts"];
const PKG_CLASS = ["web", "server", "contracts"];
const LAYER_LABEL = ["Foundational", "Layer 1", "Layer 2", "Entry / leaf"];
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

// cohorts sorted by size desc; keep the two real ones + a grouped "singletons" bucket
const byCohort = new Map();
g.nodes.forEach((n) => { (byCohort.get(n.cohort) ?? byCohort.set(n.cohort, []).get(n.cohort)).push(n); });
const cohortEntries = [...byCohort.entries()].map(([id, syms]) => ({ id, syms }))
  .sort((a, b) => b.syms.length - a.syms.length);

const bigCohorts = cohortEntries.filter((c) => c.syms.length > 1);
const singletons = cohortEntries.filter((c) => c.syms.length === 1).flatMap((c) => c.syms);

const cohortTitle = (syms) => {
  // name a cohort by the highest-degree symbol
  const hub = [...syms].sort((a, b) => b.degree - a.degree)[0];
  return hub.name;
};

let walkHTML = "";
bigCohorts.forEach((c, i) => {
  const pkgs = [...new Set(c.syms.map((s) => s.pkg))];
  const crossPkg = pkgs.length > 1;
  const maxLayer = Math.max(...c.syms.map((s) => s.layer));
  let layersHTML = "";
  for (let L = 0; L <= maxLayer; L++) {
    const inLayer = c.syms.filter((s) => s.layer === L).sort((a, b) => b.degree - a.degree);
    if (!inLayer.length) continue;
    const chips = inLayer.map((s) =>
      `<span class="chip ${PKG_CLASS[PKG[s.pkg]]}" title="${esc(s.file)} · degree ${s.degree}">` +
      `${esc(s.name)}<em>${esc(KIND[s.kind] ?? s.kind)}</em></span>`).join("");
    layersHTML += `<div class="layer-row"><span class="layer-tag l${Math.min(L, 3)}">${LAYER_LABEL[Math.min(L, 3)]}${L > 3 ? " " + L : ""}</span><div class="chips">${chips}</div></div>`;
  }
  walkHTML += `<article class="cohort">
    <header>
      <span class="co-index">Cohort ${i + 1}</span>
      <h3>${esc(cohortTitle(c.syms))} &amp; related</h3>
      <div class="co-meta">
        <span class="co-count">${c.syms.length} symbols</span>
        ${pkgs.map((p) => `<span class="pill ${PKG_CLASS[PKG[p]]}">${esc(p)}</span>`).join("")}
        ${crossPkg ? `<span class="pill cross">cross-package</span>` : ""}
      </div>
    </header>
    ${layersHTML}
  </article>`;
});

// singletons bucket
if (singletons.length) {
  const chips = singletons.map((s) =>
    `<span class="chip ${PKG_CLASS[PKG[s.pkg]]}" title="${esc(s.file)}">${esc(s.name)}<em>${esc(KIND[s.kind] ?? s.kind)}</em></span>`).join("");
  walkHTML += `<article class="cohort muted">
    <header>
      <span class="co-index">Unlinked</span>
      <h3>Changed, but no edge to another changed symbol</h3>
      <div class="co-meta"><span class="co-count">${singletons.length} symbols</span>
      <span class="note">mostly new <code>@olympus/contracts</code> types whose consumers weren't in this diff</span></div>
    </header>
    <div class="layer-row"><span class="layer-tag l0">Foundational</span><div class="chips">${chips}</div></div>
  </article>`;
}

const m = g.meta;

const html = String.raw`<title>Proof: the semantic layer, running on a real Olympus PR</title>
<style>
:root{
  --ground:#f6f3ec;--panel:#fffdf8;--panel2:#efeae0;--ink:#23262e;--soft:#565a62;--faint:#888b91;
  --rule:#ddd6c8;--rule2:#e9e3d6;
  --web:#b9762a;--web-bg:#f1e4d1;--server:#2f7d72;--server-bg:#d9e8e4;--contracts:#5f52a8;--contracts-bg:#e4e0f0;
  --cross:#c2412f;--good:#3f8a5c;
  --shadow:0 1px 2px rgba(40,36,28,.05),0 10px 30px rgba(40,36,28,.07);
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --ground:#12151d;--panel:#1a1e28;--panel2:#222736;--ink:#e9e7e0;--soft:#a8aab3;--faint:#767884;
  --rule:#2c313f;--rule2:#242938;
  --web:#e0a34d;--web-bg:#2a2318;--server:#59b6a8;--server-bg:#15241f;--contracts:#9488d9;--contracts-bg:#1e1b2c;
  --cross:#e8776b;--good:#63bd85;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 12px 34px rgba(0,0,0,.4);
}}
:root[data-theme="light"]{--ground:#f6f3ec;--panel:#fffdf8;--panel2:#efeae0;--ink:#23262e;--soft:#565a62;--faint:#888b91;--rule:#ddd6c8;--rule2:#e9e3d6;--web:#b9762a;--web-bg:#f1e4d1;--server:#2f7d72;--server-bg:#d9e8e4;--contracts:#5f52a8;--contracts-bg:#e4e0f0;--cross:#c2412f;--good:#3f8a5c;--shadow:0 1px 2px rgba(40,36,28,.05),0 10px 30px rgba(40,36,28,.07);}
:root[data-theme="dark"]{--ground:#12151d;--panel:#1a1e28;--panel2:#222736;--ink:#e9e7e0;--soft:#a8aab3;--faint:#767884;--rule:#2c313f;--rule2:#242938;--web:#e0a34d;--web-bg:#2a2318;--server:#59b6a8;--server-bg:#15241f;--contracts:#9488d9;--contracts-bg:#1e1b2c;--cross:#e8776b;--good:#63bd85;--shadow:0 1px 2px rgba(0,0,0,.3),0 12px 34px rgba(0,0,0,.4);}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1000px;margin:0 auto;padding:0 24px}
h1,h2,h3{font-family:var(--serif);font-weight:600;text-wrap:balance;line-height:1.14}
.eyebrow{font-family:var(--mono);font-size:11.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint)}
header.hero{border-bottom:1px solid var(--rule);padding:64px 0 34px}
h1{font-size:clamp(30px,5vw,50px);margin:16px 0 0;letter-spacing:-.01em}
h1 .hl{font-style:italic;color:var(--server)}
.dek{max-width:60ch;color:var(--soft);font-size:18px;margin:18px 0 0}
.src{margin-top:16px;font-family:var(--mono);font-size:12px;color:var(--faint)}
.src b{color:var(--soft);font-weight:600}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:14px;overflow:hidden;margin:30px 0 6px}
.stat{background:var(--panel);padding:16px 18px}
.stat .v{font-family:var(--serif);font-size:30px;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.stat .l{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin-top:2px}
.stat.ok .v{color:var(--good)}

section{padding:46px 0;border-bottom:1px solid var(--rule2)}
.sec-h{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
.sec-n{font-family:var(--mono);font-size:12px;color:var(--server)}
h2{font-size:clamp(22px,3.2vw,30px);margin:0}
.lede{max-width:64ch;color:var(--soft);font-size:16px;margin:12px 0 26px}

/* graph */
.graph-wrap{position:relative;background:var(--panel);border:1px solid var(--rule);border-radius:16px;box-shadow:var(--shadow);overflow:hidden}
#g{display:block;width:100%;height:560px;touch-action:none}
.legend{position:absolute;top:14px;left:16px;display:flex;flex-direction:column;gap:7px;font-family:var(--mono);font-size:11.5px;background:color-mix(in srgb,var(--panel) 82%,transparent);padding:10px 12px;border:1px solid var(--rule);border-radius:10px;backdrop-filter:blur(3px)}
.legend .row{display:flex;align-items:center;gap:8px;color:var(--soft)}
.dot{width:11px;height:11px;border-radius:50%}
.dot.web{background:var(--web)}.dot.server{background:var(--server)}.dot.contracts{background:var(--contracts)}
.edge-key{width:16px;height:0;border-top:2.5px solid var(--cross)}
.axis{position:absolute;right:14px;top:0;bottom:0;display:flex;flex-direction:column;justify-content:space-between;padding:16px 0;font-family:var(--mono);font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);text-align:right;pointer-events:none}
#tip{position:absolute;pointer-events:none;opacity:0;transition:opacity .1s;background:var(--ink);color:var(--ground);font-family:var(--mono);font-size:11.5px;padding:7px 9px;border-radius:7px;max-width:250px;z-index:5;line-height:1.5}
#tip b{color:var(--ground)}#tip .t-pkg{opacity:.75}
.hint{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:10px;text-align:center}

/* walkthrough */
.cohort{background:var(--panel);border:1px solid var(--rule);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px;margin-bottom:14px}
.cohort.muted{opacity:.82}
.cohort header{margin-bottom:14px}
.co-index{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}
.cohort h3{font-size:19px;margin:3px 0 8px}
.co-meta{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.co-count{font-family:var(--mono);font-size:12px;color:var(--soft)}
.pill{font-family:var(--mono);font-size:10.5px;padding:3px 8px;border-radius:20px;border:1px solid var(--rule)}
.pill.web{color:var(--web);background:var(--web-bg);border-color:transparent}
.pill.server{color:var(--server);background:var(--server-bg);border-color:transparent}
.pill.contracts{color:var(--contracts);background:var(--contracts-bg);border-color:transparent}
.pill.cross{color:#fff;background:var(--cross);border-color:transparent;font-weight:600}
.note{font-size:12px;color:var(--faint)}.note code{font-family:var(--mono);font-size:11px}
.layer-row{display:grid;grid-template-columns:120px 1fr;gap:14px;padding:9px 0;border-top:1px dashed var(--rule)}
.layer-tag{font-family:var(--mono);font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;padding:3px 8px;border-radius:6px;height:fit-content;color:var(--soft);background:var(--panel2);text-align:center}
.layer-tag.l0{color:var(--good);background:color-mix(in srgb,var(--good) 15%,transparent);font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-family:var(--mono);font-size:12px;padding:4px 9px;border-radius:7px;border:1px solid var(--rule);display:inline-flex;align-items:baseline;gap:6px;background:var(--panel2)}
.chip em{font-style:normal;font-size:9.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--faint)}
.chip.web{border-left:3px solid var(--web)}.chip.server{border-left:3px solid var(--server)}.chip.contracts{border-left:3px solid var(--contracts)}

.readout{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:6px}
.card{background:var(--panel);border:1px solid var(--rule);border-radius:12px;padding:16px 18px}
.card h4{margin:0 0 8px;font-family:var(--sans);font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--faint)}
.card p{margin:0;color:var(--soft);font-size:14.5px}
.card b{color:var(--ink)}
.foot{padding:34px 0 60px;color:var(--faint);font-size:13px}
.foot .cav{border-left:3px solid var(--server);padding:3px 0 3px 15px;margin:0 0 14px;color:var(--soft);max-width:70ch}
code{font-family:var(--mono)}
@media (max-width:640px){.readout{grid-template-columns:1fr}.layer-row{grid-template-columns:1fr;gap:6px}#g{height:460px}.axis{display:none}}
@media (prefers-reduced-motion:no-preference){.cohort,.stat{animation:rise .5s both}@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}}
</style>

<header class="hero"><div class="wrap">
  <div class="eyebrow">Ticket #6 · prototype · live on real code</div>
  <h1>The semantic layer, <span class="hl">running on a real Olympus PR</span></h1>
  <p class="dek">Not a mock. This is the actual dependency graph the engine extracted from <b>PR #50</b> — tree-sitter-style symbol extraction + ts-morph reference resolution — grouped into cohorts and ordered foundational-first.</p>
  <div class="src"><b>Source:</b> dm1681/Olympus <b>·</b> PR ${esc(m.pr)} <b>·</b> engine: ts-morph 28 over the pnpm monorepo <b>·</b> read-only, nothing committed</div>
  <div class="stats">
    <div class="stat"><div class="v">${m.symbolCount}</div><div class="l">changed symbols</div></div>
    <div class="stat"><div class="v">${m.edgeCount}</div><div class="l">dependency edges</div></div>
    <div class="stat ok"><div class="v">${m.crossPkg}</div><div class="l">cross-package</div></div>
    <div class="stat"><div class="v">${m.cohortCount}</div><div class="l">cohorts</div></div>
    <div class="stat ok"><div class="v">${(m.endMs/1000).toFixed(1)}s</div><div class="l">end-to-end</div></div>
  </div>
</div></header>

<div class="wrap">
  <section>
    <div class="sec-h"><span class="sec-n">01</span><h2>The dependency graph it found</h2></div>
    <p class="lede">Every dot is a symbol that changed in PR&nbsp;#50, colored by package. Every line is a real dependency the engine resolved between two changed symbols. Height encodes <b>layer</b> — foundational symbols sit at the top, the code that builds on them flows down. The <b style="color:var(--cross)">red edges cross package boundaries</b> — the monorepo test.</p>
    <div class="graph-wrap">
      <canvas id="g" aria-label="Dependency graph of the changed symbols in Olympus PR 50"></canvas>
      <div class="legend">
        <div class="row"><span class="dot web"></span>apps/web</div>
        <div class="row"><span class="dot server"></span>apps/server</div>
        <div class="row"><span class="dot contracts"></span>packages/contracts</div>
        <div class="row"><span class="edge-key"></span>cross-package edge</div>
      </div>
      <div class="axis"><span>▲ foundational</span><span>depends-on ▼</span></div>
      <div id="tip"></div>
    </div>
    <div class="hint">hover a node to trace its dependencies · larger dot = more connected</div>
  </section>

  <section>
    <div class="sec-h"><span class="sec-n">02</span><h2>The same PR, as a layered walkthrough</h2></div>
    <p class="lede">This is the product: the flat 22-file diff reorganized into dependency cohorts, each cohort's symbols stacked into layers so the foundation reads first. No summaries yet (that's ticket #9) — this is pure structure, extracted automatically.</p>
    ${walkHTML}
  </section>

  <section style="border-bottom:none">
    <div class="sec-h"><span class="sec-n">03</span><h2>What this proves</h2></div>
    <div class="readout">
      <div class="card"><h4>Cross-package resolution works</h4><p>The engine correctly resolved <b>apps/server</b> symbols depending on the <b>packages/contracts</b> <code>IdeaStatus</code> type — across the pnpm workspace boundary, via one solution-style ts-morph Program. That was the core monorepo risk.</p></div>
      <div class="card"><h4>Layering is real, not cosmetic</h4><p>The <code>@olympus/contracts</code> types landed at <b>layer 0</b> automatically — the foundation everything else references — computed by longest-path over the dependency DAG. Foundational-first ordering falls out of the graph.</p></div>
      <div class="card"><h4>Latency is a non-issue</h4><p>The research feared "seconds to tens of seconds" for Program build on a monorepo. Real numbers: <b>${m.loadMs} ms</b> to load, <b>${m.refMs} ms</b> for all ${m.symbolCount} findReferences calls, <b>${(m.endMs/1000).toFixed(1)}s</b> end-to-end.</p></div>
      <div class="card"><h4>Cohorts match intent</h4><p>PR #50 split cleanly into a <b style="color:var(--web)">web/frontend</b> cohort (the Ideas UI) and a <b style="color:var(--server)">server + contracts</b> cohort (the lifecycle backend) — the two halves a human would describe.</p></div>
    </div>
  </section>

  <div class="foot">
    <p class="cav"><b>Honest scope.</b> This ran <b>without <code>node_modules</code></b>, so edges routing through external types are under-counted — the ${m.edgeCount} edges are a floor, and ${m.loadMs} ms is a floor too. Symbol extraction used ts-morph (production swaps in tree-sitter). The big ${bigCohorts[0].syms.length}-symbol web cohort is still one undifferentiated lump — splitting and ordering <em>within</em> a cohort is the next ticket (#7). No LLM summaries yet (#9).</p>
    <p>Generated from the live spike output <code>scratchpad/spike6/graph.json</code> · wayfinder ticket #6, dm1681/skills.</p>
  </div>
</div>

<script>
const DATA=${JSON.stringify(data)};
(function(){
  const cv=document.getElementById("g"),ctx=cv.getContext("2d"),tip=document.getElementById("tip");
  const cs=()=>getComputedStyle(document.documentElement);
  const col=(v)=>cs().getPropertyValue(v).trim();
  const PKGV=["--web","--server","--contracts"];
  let W=0,H=0,DPR=Math.min(devicePixelRatio||1,2),N=DATA.nodes,E=DATA.edges;
  const maxL=Math.max(...N.map(n=>n.l)),maxD=Math.max(...N.map(n=>n.d));
  // seeded PRNG for stable init
  let seed=20260718;const rnd=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
  // cohort x-centers: rank cohorts by size, spread across width
  const cohortSizes={};N.forEach(n=>cohortSizes[n.c]=(cohortSizes[n.c]||0)+1);
  const cohortOrder=[...new Set(N.map(n=>n.c))].sort((a,b)=>cohortSizes[b]-cohortSizes[a]);
  const cohortX={};
  function layout(){
    const r=cv.getBoundingClientRect();W=r.width;H=r.height;cv.width=W*DPR;cv.height=H*DPR;ctx.setTransform(DPR,0,0,DPR,0,0);
    const padX=70,padY=48;
    cohortOrder.forEach((c,i)=>{cohortX[c]=padX+(cohortOrder.length===1?0.5:i/(cohortOrder.length-1))*(W-2*padX);});
    const yOf=(l)=>padY+(maxL===0?0.5:l/maxL)*(H-2*padY);
    seed=20260718;
    N.forEach(n=>{n.x=cohortX[n.c]+(rnd()-0.5)*90;n.y=yOf(n.l)+(rnd()-0.5)*36;n.vx=0;n.vy=0;n._ty=yOf(n.l);});
    // settle synchronously
    for(let it=0;it<420;it++){
      for(let i=0;i<N.length;i++){let a=N[i],fx=0,fy=0;
        for(let j=0;j<N.length;j++){if(i===j)continue;let b=N[j],dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy+.01;if(d2<9000){let f=1400/d2;fx+=dx*f;fy+=dy*f;}}
        fx+=(cohortX[a.c]-a.x)*0.012; // cohort gravity (x)
        fy+=(a._ty-a.y)*0.14;         // layer anchor (y, strong)
        a.vx=(a.vx+fx)*0.82;a.vy=(a.vy+fy)*0.82;
      }
      for(const e of E){let a=N[e[0]],b=N[e[1]];if(!a||!b)continue;let dx=b.x-a.x,dy=b.y-a.y,dist=Math.hypot(dx,dy)||1,f=(dist-70)*0.02,ux=dx/dist,uy=dy/dist;a.vx+=ux*f;a.vy+=uy*f*0.3;b.vx-=ux*f;b.vy-=uy*f*0.3;}
      for(const a of N){a.x+=Math.max(-6,Math.min(6,a.vx));a.y+=Math.max(-6,Math.min(6,a.vy));a.x=Math.max(24,Math.min(W-24,a.x));a.y=Math.max(24,Math.min(H-24,a.y));a.y+=(a._ty-a.y)*0.05;}
    }
    draw(-1);
  }
  function rad(n){return 3.5+Math.sqrt(n.d/(maxD||1))*8;}
  function draw(hi){
    ctx.clearRect(0,0,W,H);
    const rule=col("--rule"),cross=col("--cross");
    const nbr=new Set();if(hi>=0){for(const e of E){if(e[0]===hi)nbr.add(e[1]);if(e[1]===hi)nbr.add(e[0]);}}
    // edges
    for(const e of E){const a=N[e[0]],b=N[e[1]];if(!a||!b)continue;const on=hi<0||e[0]===hi||e[1]===hi;
      ctx.beginPath();ctx.moveTo(a.x,a.y);
      const mx=(a.x+b.x)/2,my=(a.y+b.y)/2-18;ctx.quadraticCurveTo(mx,my,b.x,b.y);
      if(e[2]){ctx.strokeStyle=cross;ctx.globalAlpha=on?0.95:0.12;ctx.lineWidth=on?2.4:1.6;}
      else{ctx.strokeStyle=rule;ctx.globalAlpha=hi<0?0.55:(on?0.8:0.06);ctx.lineWidth=on?1.6:1;}
      ctx.stroke();
    }
    ctx.globalAlpha=1;
    // nodes
    for(let i=0;i<N.length;i++){const n=N[i],on=hi<0||i===hi||nbr.has(i);
      ctx.globalAlpha=on?1:0.18;ctx.beginPath();ctx.arc(n.x,n.y,rad(n)*(i===hi?1.35:1),0,6.2832);
      ctx.fillStyle=col(PKGV[n.p]);ctx.fill();
      if(i===hi){ctx.lineWidth=2;ctx.strokeStyle=col("--ink");ctx.stroke();}
    }
    ctx.globalAlpha=1;
    // labels for high-degree hubs (always) + hovered
    ctx.font="600 11px "+col("--mono").replace(/^,/,"")||"monospace";ctx.font='600 11px ui-monospace,Menlo,monospace';
    ctx.fillStyle=col("--ink");ctx.textAlign="center";
    for(let i=0;i<N.length;i++){const n=N[i];if(n.d>=8||i===hi){if(hi>=0&&!(i===hi||nbr.has(i)))continue;
      ctx.globalAlpha=i===hi?1:0.8;ctx.fillText(n.n,n.x,n.y-rad(n)-5);}}
    ctx.globalAlpha=1;
  }
  let hov=-1;
  cv.addEventListener("pointermove",(ev)=>{
    const r=cv.getBoundingClientRect(),mx=ev.clientX-r.left,my=ev.clientY-r.top;
    let best=-1,bd=1e9;for(let i=0;i<N.length;i++){const n=N[i],d=Math.hypot(n.x-mx,n.y-my);if(d<Math.max(rad(n)+5,11)&&d<bd){bd=d;best=i;}}
    if(best!==hov){hov=best;draw(hov);}
    if(best>=0){const n=N[best];tip.style.opacity=1;tip.style.left=Math.min(mx+14,r.width-190)+"px";tip.style.top=(my+14)+"px";
      tip.innerHTML="<b>"+n.n+"</b> <span class='t-pkg'>"+n.k+"</span><br><span class='t-pkg'>"+["apps/web","apps/server","packages/contracts"][n.p]+" · "+n.f+"</span><br><span class='t-pkg'>layer "+n.l+" · "+n.d+" edges</span>";}
    else tip.style.opacity=0;
  });
  cv.addEventListener("pointerleave",()=>{hov=-1;tip.style.opacity=0;draw(-1);});
  let to;addEventListener("resize",()=>{clearTimeout(to);to=setTimeout(layout,160);});
  const mq=matchMedia("(prefers-color-scheme:dark)");mq.addEventListener&&mq.addEventListener("change",()=>draw(hov));
  new MutationObserver(()=>draw(hov)).observe(document.documentElement,{attributes:true,attributeFilter:["data-theme"]});
  layout();
})();
</script>`;

writeFileSync("/home/user/skills/docs/olympus-pr50-semantic-layer.html", html);
console.log("wrote /home/user/skills/docs/olympus-pr50-semantic-layer.html", html.length, "bytes");
