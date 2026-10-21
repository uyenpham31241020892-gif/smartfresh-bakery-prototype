import pytest
from services.assistant import Assistant
import httpx


def test_assistant_requires_key_and_never_fakes_answer(monkeypatch):
    a=Assistant()
    a.key=''
    with pytest.raises(ValueError,match='API key'):
        a.request({'input':'test'})
    assert not a.status()['fine_tuned']


def test_responses_tool_loop_has_no_mutation_capability(flow,monkeypatch):
    a=Assistant()
    a.key='test-key-only-not-used-over-network'
    s=flow.create()
    payloads=[]
    def request(payload):
        payloads.append(payload)
        if len(payloads)==1:
            assert {x['name'] for x in payload['tools']} == {'get_session_context','get_model_evidence'}
            return {'id':'test1','output':[{'type':'function_call','name':'get_session_context','arguments':'{}','call_id':'call1'}]}
        assert payload['input'][-1]['type']=='function_call_output'
        return {'id':'test2','output':[{'type':'message','content':[{'type':'output_text','text':'Tool loop test response.'}]}]}
    monkeypatch.setattr(a,'request',request)
    r=a.chat('Test only',s,lambda sku:{})
    assert r['tools_used']==['get_session_context']
    assert r['response_id']=='test2'
    assert flow.store.get(s['id'])['revision']==0


@pytest.mark.parametrize('code,expected',[
    ('insufficient_quota','Billing'),
    ('credit_balance_exhausted','credit'),
    ('project_spend_limit_exceeded','Project'),
    ('organization_usage_limit_exceeded','hạn mức'),
    ('rate_limit_exceeded','Tạm dừng'),
    ('slow_down','Giảm tần suất')
])
def test_429_diagnosis_distinguishes_quota_and_rate(code,expected):
    r=httpx.Response(429,json={'error':{'code':code,'message':'Private text that must not be exposed.'}},
                     headers={'retry-after':'20'})
    result=Assistant.describe_error(r)
    assert result['code']==code and expected in result['message']
    assert 'Private text' not in result['message']
    assert result['retry_after_seconds']==(20 if code in ['slow_down','rate_limit_exceeded'] else None)


def test_quota_type_fallback_and_unknown_error_are_honest():
    r=httpx.Response(429,json={'error':{'code':None,'type':'insufficient_quota'}})
    assert Assistant.describe_error(r)['code']=='insufficient_quota'
    r=httpx.Response(429,text='invalid error body containing private data')
    assert Assistant.describe_error(r)['code']=='unknown_error'
