import json
import pytest
import httpx
from app.services.providers.groq import GroqProvider

@pytest.mark.asyncio
@pytest.mark.parametrize('model', ['openai/gpt-oss-120b','llama-3.3-70b-versatile'])
async def test_schema_sent_to_groq(monkeypatch, model):
    sent=[]
    class Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*a): pass
        async def post(self,url,**kwargs):
            sent.append(kwargs['json'])
            return httpx.Response(200,json={'choices':[{'message':{'content':'{"name":"demo"}'}}]})
    monkeypatch.setattr(httpx,'AsyncClient',Client)
    schema={'type':'object','properties':{'name':{'type':'string'}},'required':[]}
    await GroqProvider('test',model).generate('demo',json_schema=schema)
    body=sent[0]
    if model.startswith('openai/'):
        assert body['response_format']['json_schema']['strict'] is True
        inner=body['response_format']['json_schema']['schema']
        assert inner['required']==['name']
        assert inner['additionalProperties'] is False
    else:
        assert body['response_format']['type']=='json_object'
        assert '"properties"' in body['messages'][0]['content']
        assert 'reasoning_effort' not in body
    assert schema['required']==[]
