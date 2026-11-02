"""Native Gemini/Ollama transports; domain tools remain read-only in Assistant."""
import json
import uuid
import time
import httpx


def gemini_error(response, stage='generate_content'):
    """Classify Google errors without returning raw bodies, keys or project identifiers."""
    try:
        detail = response.json().get('error', {})
        detail = detail if isinstance(detail, dict) else {}
    except (ValueError, AttributeError):
        detail = {}
    raw = str(detail.get('message', '')).lower()
    reasons = {d.get('reason') for d in detail.get('details', []) if isinstance(d, dict)}
    status = response.status_code
    if 'API_KEY_INVALID' in reasons or 'api key not valid' in raw or 'invalid api key' in raw:
        code, hint = 'API_KEY_INVALID', 'Google không chấp nhận API key. Lấy Gemini API key từ Google AI Studio; không dùng key OpenAI hoặc OAuth token.'
    elif 'leaked' in raw:
        code, hint = 'API_KEY_BLOCKED', 'Google đã chặn key bị lộ. Tạo key mới trong Google AI Studio và chỉ nhập trực tiếp trong dashboard.'
    elif reasons & {'API_KEY_HTTP_REFERRER_BLOCKED', 'API_KEY_IP_ADDRESS_BLOCKED', 'API_KEY_SERVICE_BLOCKED'}:
        code, hint = 'API_KEY_RESTRICTION', 'Key đang bị giới hạn referrer/IP/dịch vụ không phù hợp. Backend Python gọi Gemini từ máy này; kiểm tra API restrictions cho Generative Language API.'
    elif 'SERVICE_DISABLED' in reasons:
        code, hint = 'SERVICE_DISABLED', 'Project chưa bật Generative Language API. Kiểm tra project sở hữu key trong Google AI Studio/Google Cloud.'
    elif 'free tier is not available' in raw or 'billing' in raw and status in [400, 402, 403]:
        code, hint = 'BILLING_OR_REGION', 'Google yêu cầu kiểm tra billing/khu vực của project API. Gói Gemini Pro không tự bảo đảm quyền sử dụng API.'
    elif status == 429:
        code, hint = 'RESOURCE_EXHAUSTED', 'Đã chạm quota/rate limit API. Kiểm tra hạn mức model/project trong AI Studio; gói Gemini Pro không bảo đảm quota API.'
    elif status == 404:
        code, hint = 'MODEL_NOT_FOUND', 'Model không tồn tại hoặc không hỗ trợ generateContent với key này. Bấm Kiểm tra key & tải model rồi chọn model trong danh sách.'
    elif 'thought' in raw and 'signature' in raw:
        code, hint = 'TOOL_HISTORY_INVALID', 'Google từ chối thought signature trong lịch sử công cụ. Tải lại ứng dụng rồi thử lại; đây là lỗi định dạng tích hợp, không phải kết luận key sai.'
    elif any(word in raw for word in ['additionalproperties', 'additional_properties', 'parametersjsonschema', 'function_declarations', 'functiondeclarations', 'function response', 'function_response', 'unknown name', 'invalid json payload']):
        code, hint = 'REQUEST_SCHEMA_INVALID', 'Google từ chối định dạng yêu cầu/công cụ. Tải lại ứng dụng để dùng bản sửa tích hợp; chưa có cơ sở kết luận key sai.'
    elif status == 400:
        code, hint = 'INVALID_ARGUMENT', 'Google từ chối một tham số yêu cầu. Dùng Kiểm tra key & tải model để tách lỗi key khỏi lỗi model/công cụ; chưa thể kết luận key sai.'
    elif status in [401, 403]:
        code, hint = 'PERMISSION_DENIED', 'Kiểm tra quyền key/project và Generative Language API. Key có thể hợp lệ nhưng bị giới hạn quyền hoặc khu vực.'
    else:
        code, hint = 'SERVICE_ERROR', 'Dịch vụ Gemini chưa xử lý được yêu cầu; thử lại sau.'
    message = f'Gemini HTTP {status} ({code}, {stage}): {hint}'
    return {'status': status, 'code': code, 'stage': stage, 'message': message}


def list_gemini_models(owner):
    if not owner.key:
        raise ValueError('Nhập Gemini API key trong dashboard trước khi kiểm tra.')
    models, token = [], None
    try:
        with httpx.Client(timeout=30) as client:
            for _ in range(20):
                response = client.get('https://generativelanguage.googleapis.com/v1beta/models',
                                      headers={'x-goog-api-key': owner.key}, params={'pageSize': 100, **({'pageToken': token} if token else {})})
                if response.status_code >= 400:
                    owner.last_error = gemini_error(response, 'list_models')
                    raise ValueError(owner.last_error['message'])
                value = response.json()
                for model in value.get('models', []):
                    name = model.get('name', '').removeprefix('models/')
                    if name.startswith('gemini-') and 'generateContent' in model.get('supportedGenerationMethods', []):
                        models.append({'id': name, 'name': model.get('displayName', name)})
                token = value.get('nextPageToken')
                if not token:
                    break
    except httpx.RequestError:
        raise ValueError('Không kết nối được Google để kiểm tra key và danh sách model.') from None
    return {'provider': 'Gemini', 'key_accepted': True, 'models': sorted(models, key=lambda m: m['id']),
            'note': 'Google chấp nhận key để liệt kê model. Chưa xác minh quota gọi, function calling hoặc phí model.'}


def request(owner, payload,timeout_override=None):
    gemini = owner.provider == 'Gemini'
    if gemini and not owner.key:
        raise ValueError('Chưa có Gemini API key. Tạo key trong Google AI Studio và nhập ở Cài đặt AI.')
    schema = payload.get('text', {}).get('format', {}).get('schema')
    source = payload.get('input', [])
    if isinstance(source, str):
        source = [{'role': 'user', 'content': source}]
    messages = []
    for item in source:
        if gemini and item.get('_gemini_content'):
            messages.append(item['_gemini_content'])
        elif item.get('type') == 'function_call':
            if not gemini:
                messages.append({'role': 'assistant', 'content': '', 'tool_calls': [
                    {'function': {'name': item['name'], 'arguments': json.loads(item['arguments'])}}]})
        elif item.get('type') == 'function_call_output':
            # The matching call is trusted backend metadata, never inferred from user text.
            call = next(x for x in source if x.get('call_id') == item['call_id'] and x.get('type') == 'function_call')
            if gemini:
                response = {'name': call['name'], 'response': {'result': json.loads(item['output'])}}
                if call.get('_native_id'):
                    response['id'] = call['_native_id']
                part = {'functionResponse': response}
                if messages and messages[-1]['role'] == 'user' and all('functionResponse' in p for p in messages[-1]['parts']):
                    messages[-1]['parts'].append(part)
                else:
                    messages.append({'role': 'user', 'parts': [part]})
            else:
                messages.append({'role': 'tool', 'tool_name': call['name'], 'content': item['output']})
        elif item.get('role'):
            messages.append({'role': item['role'], 'parts': [{'text': item['content']}]} if gemini else item)
    functions = [{k: t[k] for k in ['name', 'description', 'parameters']} for t in payload.get('tools', [])]
    if gemini:
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{owner.model}:generateContent'
        body = {'systemInstruction': {'parts': [{'text': payload.get('instructions', '')}]},
                'contents': messages, 'generationConfig': {'maxOutputTokens': 4096}}
        if functions:
            # parameters is Google's OpenAPI Schema (no additionalProperties).
            # Our strict schemas are JSON Schema, so use its dedicated field.
            body['tools'] = [{'functionDeclarations': [
                {'name': f['name'], 'description': f['description'], 'parametersJsonSchema': f['parameters']}
                for f in functions]}]
            body['toolConfig'] = {'functionCallingConfig': {'mode': 'ANY' if payload.get('tool_choice') == 'required' else 'AUTO'}}
        if schema:
            body['generationConfig'].update(responseMimeType='application/json', responseJsonSchema=schema)
        headers = {'x-goog-api-key': owner.key}
    else:
        url = 'http://127.0.0.1:11434/api/chat'
        body = {'model': owner.model, 'stream': False, 'think': False,
                'messages': [{'role': 'system', 'content': payload.get('instructions', '')}] + messages,
                'options': {'temperature': 0.1, 'num_ctx': 16384 if any(f['name']=='get_business_report' for f in functions) or payload.get('text',{}).get('format',{}).get('name') in ('report_insights','proposal_insights') else 8192, 'num_predict': payload.get('max_output_tokens',2400)}}
        if functions:
            body['tools'] = [{'type': 'function', 'function': f} for f in functions]
        if schema:
            body['format'] = schema
        headers = {}
    # Gemini 502/503/504 are temporary service failures. Domain tools are read-only;
    # retrying this transport cannot repeat a managerial approval or mutation.
    # Do not retry quota (429), permission (403), malformed requests (400), or Ollama.
    response = None
    attempts = 2 if gemini else 1
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=timeout_override or (90 if gemini else 180), trust_env=gemini) as client:
                response = client.post(url, headers=headers, json=body)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            if gemini and attempt + 1 < attempts:
                time.sleep(1.5)
                continue
            owner.last_error = {'code': 'NETWORK_TIMEOUT' if isinstance(exc, httpx.TimeoutException) else 'NETWORK_ERROR',
                                'message': 'Gemini phản hồi quá chậm hoặc mất kết nối. Hãy đợi một chút rồi thử lại.'} if gemini else None
            raise ValueError(owner.last_error['message'] if gemini else 'Không kết nối được Ollama. Kiểm tra tiến trình Ollama và tài nguyên máy.') from None
        except httpx.RequestError:
            raise ValueError('Không kết nối được ' + owner.provider + '. Kiểm tra mạng hoặc dịch vụ rồi thử lại.') from None
        if gemini and response.status_code in (502, 503, 504) and attempt + 1 < attempts:
            # Short bounded backoff, no retry storm.
            time.sleep(1.5)
            continue
        break
    if response.status_code >= 400:
        if gemini:
            owner.last_error = gemini_error(response)
            if response.status_code in (502, 503, 504):
                owner.last_error['message'] += ' Đã thử lại tự động một lần. Bạn có thể dùng M1/M2 trong lúc chờ dịch vụ.'
            raise ValueError(owner.last_error['message'])
        hints = {429: 'Đã chạm quota/rate limit.', 400: 'Kiểm tra model và tham số.',
                 403: 'Không có quyền gọi API.', 404: 'Không tìm thấy model.'}
        message = f'{owner.provider} HTTP {response.status_code}: ' + hints.get(response.status_code, 'Dịch vụ chưa xử lý được yêu cầu.')
        owner.last_error = {'status': response.status_code, 'message': message}
        raise ValueError(message)
    owner.last_error = None
    data = response.json()
    output = []
    if gemini:
        candidates = data.get('candidates', [])
        content = candidates[0].get('content', {}) if candidates else {}
        # Preserve thought signatures and the complete model turn across tool rounds.
        output.append({'type': '_native', '_gemini_content': content})
        parts = content.get('parts', [])
        calls = [p['functionCall'] for p in parts if 'functionCall' in p]
        answer = '\n'.join(p['text'] for p in parts if 'text' in p and not p.get('thought'))
    else:
        message = data.get('message', {})
        calls = [c['function'] for c in message.get('tool_calls', [])]
        answer = message.get('content', '')
    for call in calls:
        identifier = uuid.uuid4().hex
        output.append({'type': 'function_call', 'call_id': identifier, 'name': call['name'],
                       'arguments': json.dumps(call.get('args', call.get('arguments', {}))), '_native_id': call.get('id')})
    if answer:
        output.append({'type': 'message', 'content': [{'type': 'output_text', 'text': answer}]})
    return {'id': data.get('responseId') or 'local-' + uuid.uuid4().hex, 'output': output}
