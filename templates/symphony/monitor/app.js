'use strict';
const $ = id => document.getElementById(id);
let snapshot;
let pending = false;
async function action(item, kind) {
 const impact = kind === "start" ? "I acknowledge the engineering preview. Start may dispatch eligible Linear issues." : `Stop this repository and all its owned workers? ${item.counts?.running ?? "Unknown"} active workers may be interrupted; in-flight edits may be incomplete.`;
 if (!window.confirm(`${item.name}\n${item.project_path}\n\n${impact}`)) return;
 pending = true; render();
 const output = $("action-result"); output.textContent = `${kind === "start" ? "Starting" : "Stopping"} ${item.name}…`;
 try {
  const response = await fetch("/api/action", {method:"POST", headers:{"Content-Type":"application/json", "X-Symphony-CSRF":snapshot.csrf_token}, body:JSON.stringify({id:item.id, repository_id:item.lifecycle.repository_id, action:kind, acknowledge:true, invocation:item.lifecycle.invocation ?? null})});
  const result = await response.json();
  output.textContent = response.ok ? `${item.name}: ${kind} accepted. Process state will update; ownership remains until shutdown completes.` : result.error;
 } catch (_) {output.textContent = "Action could not be confirmed. Refresh and reconcile process state before retrying.";}
 finally {pending = false; render();}
}

function el(tag, text, cls) {const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
function duration(seconds) {if(seconds==null)return 'Unavailable';const n=Math.max(0,Math.floor(seconds));return n<60?`${n}s`:`${Math.floor(n/60)}m ${n%60}s`;}
function time(value) {return value==null?'Never':new Date(value*1000).toLocaleTimeString();}
function metric(label,value,scope) {const n=el('div',undefined,'metric');n.append(el('span',label),el('strong',value==null?'Unavailable':value.toLocaleString()),el('small',scope));return n;}
function link(label,url) {const n=el('a',label);n.href=url;n.target='_blank';n.rel='noopener noreferrer';return n;}
function render() {
 if(!snapshot)return;
 const project=$('project').value,status=$('status').value;
 const instances=snapshot.instances.filter(i=>!project||i.project_path===project);
 const current=instances.filter(i=>i.current);
 const tokens=current.filter(i=>i.usage.total_tokens!=null);
 const runtime=current.filter(i=>i.usage.seconds_running!=null);
 $('summary').replaceChildren(metric('Active workers',current.reduce((s,i)=>s+i.counts.running,0),'Fresh · selected projects'),metric('Retry queue',current.reduce((s,i)=>s+i.counts.retrying,0),'Fresh · selected projects'),metric('Reported tokens',tokens.length?tokens.reduce((s,i)=>s+i.usage.total_tokens,0):null,`${tokens.length}/${instances.length} instances report usage`),metric('Reported runtime',runtime.length?duration(runtime.reduce((s,i)=>s+i.usage.seconds_running,0)):null,`${runtime.length}/${instances.length} instances · current runtimes`));
 $('notice').textContent=snapshot.registry_error?'Registry unavailable. Coverage may be incomplete; repair the registry file.':`${current.length}/${instances.length} selected instances have fresh observations. ${instances.length-current.length?'Partial coverage — unavailable instances are excluded from counts.':'Observation coverage is current.'} Last monitor read ${time(snapshot.observed_at)}. Counts ignore the status filter.`;
 const root=$('instances');root.replaceChildren();
 for(const item of instances) {
  const sessions=item.sessions.filter(s=>!status||s.status===status||item.health===status&&status!=='active');
  if(status&&item.health!==status&&!sessions.length)continue;
  const box=el('article',undefined,'instance');const heading=el('h3',item.name);heading.append(el('span',item.health,'badge '+item.health));if(item.endpoint)heading.append(link('Open instance ↗',item.endpoint));box.append(heading);
  box.append(el('div',`${item.project_path} · Instance ${item.id.slice(0,8)}`,'details'),el('div',`Last success: ${time(item.last_success)} · Source snapshot: ${time(item.source_time)} · Last check: ${time(item.checked_at)}`,'details'));
  if(item.lifecycle) {
   const state = item.lifecycle;
   const controls = el('div', undefined, 'controls');
   controls.append(el('strong', `Process: ${state.state}`), el('span', state.readiness || 'Readiness unknown'));
   if(state.error) controls.append(el('p', state.error));
   for(const kind of ['start', 'stop']) {const button=el('button', kind==='start'?'Start':'Stop');button.type='button';button.disabled=pending || !state[`can_${kind}`];button.addEventListener('click',()=>action(item,kind));controls.append(button);}
   box.append(controls);
  }
  if(sessions.length) {
   const table=el('table');const head=el('tr');for(const title of ['Issue / session','State','Elapsed','Latest activity','Tokens'])head.append(el('th',title));const thead=el('thead');thead.append(head);table.append(thead);const body=el('tbody');
   for(const session of sessions) {const row=el('tr');const issue=el('td');issue.append(session.issue_url?link(session.issue||'Issue',session.issue_url):el('span',session.issue||'Identifier unavailable'),el('small','Title unavailable · '+(session.session_id||'Session unavailable')));row.append(issue);row.append(el('td',session.status));row.append(el('td',session.started_at==null?'Unavailable':duration(snapshot.observed_at-session.started_at)));const activity=el('td',session.activity||'Activity unavailable');activity.append(el('small',session.status==='retrying'?`Attempt ${session.attempt??'unavailable'} · due ${time(session.due_at)}`:`Last event: ${time(session.last_event_at)}`));row.append(activity,el('td',session.tokens.total_tokens==null?'Unavailable':session.tokens.total_tokens.toLocaleString()));body.append(row);}
   table.append(body);box.append(table);
  } else {const messages={disabled:'HTTP dashboard disabled / unavailable. Sessions cannot be observed.',configured:'Configured endpoint; waiting for the first observation.',unreachable:'Endpoint offline or timed out. Previous sessions are excluded.',incompatible:'Malformed, unavailable or unsupported state API. Sessions cannot be observed.',stale:'Source snapshot is stale. Previous sessions are excluded.',idle:'Reachable and idle — no active or retrying workers.'};box.append(el('p',messages[item.health]||'No workers match this status.'));}
  root.append(box);
 }
 if(!root.children.length)root.append(el('div',snapshot.instances.length?'No instances match these filters.':'No registered instances. Use skills symphony register --project-dir /path/to/project to import an existing instance.','empty'));
}
async function refresh() {try {const response=await fetch('/api/state',{signal:AbortSignal.timeout(4000)});if(!response.ok)throw Error();snapshot=await response.json();const selected=$('project').value;const options=[el('option','All projects')];options[0].value='';const seen=new Set();for(const i of snapshot.instances){if(seen.has(i.project_path))continue;seen.add(i.project_path);const option=el('option',i.name+' · '+i.project_path);option.value=i.project_path;options.push(option);}$('project').replaceChildren(...options);$('project').value=selected;render();}catch(_){snapshot=null;$('notice').textContent='Monitor disconnected. Current sessions and totals are unavailable; reconnecting…';$('summary').replaceChildren();$('instances').replaceChildren(el('div','Waiting for the local monitor to recover.','empty'));}finally{setTimeout(refresh,2000);}}
$('project').addEventListener('change',render);$('status').addEventListener('change',render);refresh();
