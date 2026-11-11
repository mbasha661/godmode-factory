"""Real ten-app benchmark of the factory pipeline. One durable step per invocation.
No mocked model responses; no claimed deploys. Secrets are loaded from local server config.
"""
import asyncio,json,os,sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))
from app.config import Settings
from app.db import SupabaseDB, MemoryDB
from app.services.orchestrator import Orchestrator,utcnow
from app.services.agents import execute_agent
from app.services.providers.gemini import GeminiProvider
from app.services.providers.groq import GroqProvider
OUT=Path('/downloads/factory-benchmark'); OUT.mkdir(exist_ok=True)
CATALOG=[
('Expense Tracker','Record expenses with amount, category, date and description; list/filter expenses, monthly totals by category, delete an expense.'),
('Inventory Manager','Add products with SKU, name, quantity and reorder threshold; adjust stock; list low-stock products; reject negative stock and duplicate SKU.'),
('Contact Book','Create contacts with name, email, phone and tags; search names, edit contacts and delete; reject empty names.'),
('Task Board','Create tasks with title, description, priority and todo/doing/done status; filter by status; edit and delete tasks.'),
('Habit Journal','Create daily habits; mark a habit complete for a date; avoid duplicate completion; show completion history and counts.'),
('Appointment Planner','Create appointments with title, date, start/end time and notes; reject overlapping appointments; list by date; cancel an appointment.'),
('Support Tickets','Create tickets with title, description, priority and open/closed status; assign to a named agent; filter, update and close tickets.'),
('Notes Library','Create notes with title, content and tags; search title/content; edit and delete notes; preserve markdown text.'),
('Bookmark Organizer','Save http/https URLs with title and category; search and filter bookmarks; reject invalid URL schemes; delete bookmarks.'),
('Time Log','Record work sessions with project, date, minutes and description; reject nonpositive minutes; report total minutes by project and date; edit/delete entries.')]
COMMON=''' Build a compact runnable web app, not an outline. Use Python FastAPI, SQLite via the standard sqlite3 module, and a single HTML/CSS/vanilla-JS frontend served by the same app. Keep each generated file below 120 lines and the backend below 200 lines. Use concise design outputs. No user accounts, JWT, cloud services, paid APIs or external database; this is a local single-user evaluation app. Keep application code in main.py, frontend in static/index.html and dependencies in requirements.txt. Use FastAPI 0.115.6, Pydantic 2.10.4, httpx 0.27.2 and pytest 8.3.4, pinned in requirements.txt. With Pydantic 2 use Field(pattern=), never regex=. Use a database path configurable by APP_DB_PATH for isolated tests; enable safe per-request SQLite connections. Include at least 6 substantive pytest tests covering positive CRUD flows, validation failures and the named business rule; tests must invoke the real application, not mocks. Tests must use isolated temporary databases and must not weaken assertions just to pass. Include README.md with exact startup command. This benchmark is local only; do not claim any public deployment.'''

def settings():
 env={v['envVar']['key'].lower():v['envVar']['value'] for v in json.load(open('/tmp/render-env.json'))}
 return Settings(**env,seconds_between_agent_steps=0)

async def main():
 s=settings();db=MemoryDB()
 dbfile=OUT/'pipeline-store.json'
 if dbfile.exists(): db.tables=json.loads(dbfile.read_text())
 anchor={'owner_id':'local-benchmark-owner'}
 mf=OUT/'manifest.json';manifest=json.loads(mf.read_text()) if mf.exists() else []
 idx=next((i for i in range(10) if i>=len(manifest) or manifest[i]['status'] not in ('succeeded','failed','cancelled')),None)
 if idx is None: print('ALL_TEN_TERMINAL');return
 # Strong model for first app; later selection can change without changing artifact provenance.
 model=os.environ.get('BENCH_MODEL','openai/gpt-oss-120b')
 provider = (lambda:GeminiProvider(s.gemini_api_key,model)) if os.environ.get('BENCH_PROVIDER')=='gemini' else (lambda:GroqProvider(Path("/tmp/groq-key").read_text().strip(),model))
 orch=Orchestrator(db,s,provider,execute_agent)
 if idx>=len(manifest):
  name,features=CATALOG[idx];pid=str(uuid4());now=utcnow()
  await db.insert('projects',{'id':pid,'owner_id':anchor['owner_id'],'name':f'Benchmark {idx+1:02d}: {name}','description':features+COMMON,'project_type':'fullstack','status':'draft','created_at':now,'updated_at':now})
  r=await orch.create_run(pid,anchor['owner_id'],goal=features+COMMON)
  manifest.append({'index':idx+1,'name':name,'project_id':pid,'run_id':r['id'],'status':r['status'],'model':model})
  mf.write_text(json.dumps(manifest,indent=2)); dbfile.write_text(json.dumps(db.tables))
 item=manifest[idx];run_id=item['run_id']
 try:
  r=await asyncio.wait_for(orch.step(run_id),timeout=102)
 except asyncio.TimeoutError:
  tasks=await db.select('tasks',{'run_id':run_id})
  for t in tasks:
   if t['status']=='running':
    await db.update('tasks',{'id':t['id']},{'status':'ready','error_summary':'benchmark step timeout; retry with complete context','updated_at':utcnow()})
    for a in await db.select('agent_runs',{'task_id':t['id'],'status':'running'}):
     await db.update('agent_runs',{'id':a['id']},{'status':'failed','error_summary':'benchmark step timeout'})
  r=await db.select_one('workflow_runs',{'id':run_id})
 tasks=await db.select('tasks',{'run_id':run_id},order='sequence',desc=False)
 agents=await db.select('agent_runs',{'run_id':run_id},order='created_at',desc=False)
 item['status']=r['status'];item['model']=model
 mf.write_text(json.dumps(manifest,indent=2)); dbfile.write_text(json.dumps(db.tables))
 evidence={'run':r,'tasks':tasks,'agent_runs':agents}
 (OUT/f'{idx+1:02d}-evidence.json').write_text(json.dumps(evidence,indent=2))
 # Export the model's actual files, including cumulative test/repair patches.
 files={}
 for t in tasks:
  o=t.get('output') or {}
  for field in ('files','test_files','fixed_files'):
   for f in o.get(field,[]):
    if isinstance(f,dict): files[f['path']]=f['content']
 dest=OUT/f'{idx+1:02d}-app';dest.mkdir(exist_ok=True)
 for p,c in files.items():
  target=(dest/p).resolve()
  if not target.is_relative_to(dest.resolve()): raise ValueError('unsafe generated path')
  target.parent.mkdir(parents=True,exist_ok=True);target.write_text(c)
 print(json.dumps({'app':item,'tasks':[{'role':t['agent_role'],'status':t['status'],'attempts':t['attempts'],'error':t.get('error_summary'),'executor':(t.get('output') or {}).get('executor_result')} for t in tasks]},indent=2))

if __name__=='__main__': asyncio.run(main())
