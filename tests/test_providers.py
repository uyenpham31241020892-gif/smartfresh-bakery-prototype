import json
import httpx
import pytest
from services.assistant import Assistant


@pytest.mark.parametrize('provider', ['Gemini', 'Ollama'])
def test_native_tool_roundtrip_preserves_evidence_and_signatures(provider, flow, monkeypatch):
    import services.providers as native
    original = httpx.Client
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if provider == 'Gemini':
            assert request.headers['x-goog-api-key'] == 'test-key-not-real-123456789'
            assert 'temperature' not in body['generationConfig']
            declarations = body['tools'][0]['functionDeclarations']
            assert all('parametersJsonSchema' in f and 'parameters' not in f for f in declarations)
            assert declarations[0]['parametersJsonSchema']['additionalProperties'] is False
            if len(requests) == 1:
                return httpx.Response(200, json={'candidates': [{'content': {'role': 'model', 'parts': [
                    {'functionCall': {'name': 'get_model_evidence', 'args': {'sku': 'TP-DN-001'}, 'id': 'native1'}, 'thoughtSignature': 'signature-kept'}]}}]})
            assert body['contents'][1]['parts'][0]['thoughtSignature'] == 'signature-kept'
            result = body['contents'][2]['parts'][0]['functionResponse']
            assert result['id'] == 'native1' and result['response']['result']['forecast'] == 12.5
            return httpx.Response(200, json={'responseId': 'gemini-verified', 'candidates': [{'content': {'role': 'model', 'parts': [{'text': 'Dự báo 12.5 từ công cụ.'}]}}]})
        assert str(request.url) == 'http://127.0.0.1:11434/api/chat'
        if len(requests) == 1:
            return httpx.Response(200, json={'message': {'role': 'assistant', 'tool_calls': [
                {'function': {'name': 'get_model_evidence', 'arguments': {'sku': 'TP-DN-001'}}}]}})
        assert json.loads(body['messages'][-1]['content'])['forecast'] == 12.5
        return httpx.Response(200, json={'message': {'content': 'Dự báo 12.5 từ công cụ.'}})

    monkeypatch.setattr(native.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(respond)))
    a = Assistant()
    a.configure('test-key-not-real-123456789' if provider == 'Gemini' else '', 'test-model', provider)
    state = flow.create()
    result = a.chat('Dự báo TP-DN-001?', state, lambda sku: {'forecast': 12.5})
    assert result['tools_used'] == ['get_model_evidence']
    assert result['provider'] == provider and a.verified
    assert flow.store.get(state['id'])['revision'] == state['revision']


def test_model_without_evidence_is_rejected(flow, monkeypatch):
    a = Assistant()
    a.configure('', 'qwen3.5:4b', 'Ollama')
    monkeypatch.setattr(a, 'request', lambda _: {'id': 'fake', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Buy 999.'}]}]})
    with pytest.raises(ValueError, match='chưa đọc công cụ'):
        a.chat('Plan?', flow.create(), lambda sku: {})
    assert not a.verified


def test_gemini_parallel_results_share_one_turn_and_keep_signatures(flow, monkeypatch):
    import services.providers as native
    original = httpx.Client
    turns = []
    content = {'role': 'model', 'parts': [
        {'functionCall': {'name': 'get_session_context', 'args': {}, 'id': 'context1'}, 'thoughtSignature': 'opaque-signature'},
        {'functionCall': {'name': 'get_model_evidence', 'args': {'sku': 'TP-DN-001'}, 'id': 'evidence1'}}]}
    def respond(request):
        body = json.loads(request.content)
        turns.append(body)
        if len(turns) == 1:
            return httpx.Response(200, json={'candidates': [{'content': content}]})
        assert body['contents'][1] == content
        results = body['contents'][2]['parts']
        assert len(body['contents']) == 3 and len(results) == 2
        assert [r['functionResponse']['id'] for r in results] == ['context1', 'evidence1']
        return httpx.Response(200, json={'responseId': 'parallel-ok', 'candidates': [{'content': {'role': 'model', 'parts': [{'text': 'Grounded answer.'}]}}]})
    monkeypatch.setattr(native.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(respond)))
    a = Assistant()
    a.configure('test-gemini-key-not-real-000', 'gemini-3.8-flash', 'Gemini')
    result = a.chat('Read context and evidence', flow.create(), lambda sku: {'forecast': 12.5})
    assert result['tools_used'] == ['get_session_context', 'get_model_evidence']


@pytest.mark.parametrize('status,reason,message,code', [
    (400, 'API_KEY_INVALID', 'API key not valid. Secret content.', 'API_KEY_INVALID'),
    (400, None, 'Invalid JSON payload. Unknown name additionalProperties.', 'REQUEST_SCHEMA_INVALID'),
    (400, None, 'Missing thought_signature in function call.', 'TOOL_HISTORY_INVALID'),
    (400, None, 'Number of function response parts must match calls.', 'REQUEST_SCHEMA_INVALID'),
    (400, None, 'Private undocumented error.', 'INVALID_ARGUMENT'),
    (403, 'SERVICE_DISABLED', 'Private project number.', 'SERVICE_DISABLED'),
    (403, 'API_KEY_HTTP_REFERRER_BLOCKED', 'Private referrer.', 'API_KEY_RESTRICTION'),
    (403, None, 'Key reported as leaked.', 'API_KEY_BLOCKED'),
    (400, None, 'Free tier is not available in your country.', 'BILLING_OR_REGION'),
    (404, None, 'Unknown model.', 'MODEL_NOT_FOUND'),
    (429, None, 'Quota exceeded.', 'RESOURCE_EXHAUSTED'),
])
def test_gemini_diagnosis_is_specific_without_exposing_raw_data(status, reason, message, code):
    from services.providers import gemini_error
    secret = 'test-secret-not-to-be-shown'
    response = httpx.Response(status, json={'error': {'message': message+' '+secret, 'details': [{'reason': reason}]}})
    diagnosis = gemini_error(response)
    assert diagnosis['code'] == code
    assert secret not in json.dumps(diagnosis) and 'Private' not in diagnosis['message']


def test_list_models_paginates_filters_and_never_generates(monkeypatch):
    import services.providers as native
    original = httpx.Client
    calls = []
    def respond(request):
        assert request.method == 'GET' and request.url.path == '/v1beta/models'
        assert request.headers['x-goog-api-key'] == 'test-key-not-real-123456789'
        assert 'key' not in request.url.params
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={'models': [{'name': 'models/gemini-test-flash', 'supportedGenerationMethods': ['generateContent']}], 'nextPageToken': 'page2'})
        assert request.url.params['pageToken'] == 'page2'
        return httpx.Response(200, json={'models': [{'name': 'models/embedding-test', 'supportedGenerationMethods': ['embedContent']}]})
    monkeypatch.setattr(native.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(respond)))
    a = Assistant()
    a.configure('test-key-not-real-123456789', 'gemini-3.8-flash', 'Gemini')
    result = native.list_gemini_models(a)
    assert result['key_accepted'] and len(result['models']) == 1
    assert not a.verified and len(calls) == 2
