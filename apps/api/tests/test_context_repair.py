import pytest
from app.config import Settings
from app.db import MemoryDB
from app.services.orchestrator import Orchestrator
from app.services.execution import _failure_summary

@pytest.mark.asyncio
async def test_upstream_source_is_not_silently_truncated():
    db=MemoryDB(); seen=[]
    class P: name='test'; model='test'
    async def execute(role, task_input, provider):
        seen.append(task_input)
        return {'files': []}
    orch=Orchestrator(db,Settings(seconds_between_agent_steps=0),lambda:P(),execute)
    run=await orch.create_run('p','u',goal='demo')
    tasks=await db.select('tasks',{'run_id':run['id']},order='sequence',desc=False)
    source='x'*15000+'END_OF_COMPLETE_BACKEND'
    await db.update('tasks',{'id':tasks[0]['id']},{'status':'succeeded','output':{'source':source}})
    await orch.step(run['id'])
    assert seen[0]['upstream_outputs']['architect']['source']==source

def test_error_lines_survive_warning_flood():
    msg=_failure_summary('E   NameError: missing\n'+'warning\n'*500,'',limit=500)
    assert msg.startswith('E   NameError: missing')

@pytest.mark.asyncio
async def test_failed_repair_output_is_retained(monkeypatch):
    db=MemoryDB()
    class P: name='test'; model='test'
    async def execute(role, task_input, provider):
        return {'test_files':[{'path':'test_x.py','content':'assert False'}], 'fixed_files':[{'path':'main.py','content':'x=1'}]}
    orch=Orchestrator(db,Settings(seconds_between_agent_steps=0),lambda:P(),execute)
    run=await orch.create_run('p','u',goal='demo')
    task=next(t for t in await db.select('tasks',{'run_id':run['id']}) if t['agent_role']=='test_repair')
    async def failing(run,out):
        out['executor_result']={'ran':True,'tests_passed':False,'exit_code':1}
        raise RuntimeError('real failure')
    monkeypatch.setattr(orch,'_run_real_tests',failing)
    await orch._execute_task(run,task)
    saved=await db.select_one('tasks',{'id':task['id']})
    assert saved['output']['fixed_files'][0]['content']=='x=1'
    assert saved['output']['executor_result']['tests_passed'] is False
