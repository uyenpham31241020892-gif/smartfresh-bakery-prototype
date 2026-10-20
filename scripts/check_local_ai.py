"""Real Ollama smoke test after setup; never substitutes a canned answer."""
import json
from pathlib import Path
import httpx


def main():
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=240) as client:
        state = client.get('/api/state').json()
        result = client.post('/api/ai/connect', json={'provider': 'Ollama', 'model': 'qwen3.5:4b',
                                                    'session_id': state['id']})
        result.raise_for_status()
        data = result.json()
        assert data['ai']['verified'] and data['ai']['provider'] == 'Ollama'
        assert 'get_model_evidence' in data['verification']['tools_used']
        after = client.get('/api/state').json()
        assert after['revision'] == state['revision'] and after['phase'] == state['phase']
        evidence = client.get('/api/evidence/' + state['id'] + '/BK-001').json()
        record = {'connection': data, 'evidence': evidence,
                  'note': 'Real local call; review narrative against evidence. Not a quality guarantee.'}
        dest = Path(__file__).resolve().parents[1] / 'docs' / 'qa' / 'ollama-live.json'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
