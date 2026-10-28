"""User and model attribution must survive every planning node's label."""
from types import SimpleNamespace

from core.graph import _record_usage_from_response


def test_usage_preserves_user_and_actual_model(monkeypatch):
    calls = []
    monkeypatch.setattr('services.usage_service.record_usage', lambda **values: calls.append(values))
    response = SimpleNamespace(usage_metadata={'input_tokens': 123, 'output_tokens': 45},
        response_metadata={'model_name': 'actual-model', 'model_provider': 'openai'})
    _record_usage_from_response({'user_id': 'account-id', 'session_id': 'conversation-id'},
                                response, provider='planner-gap', model_name='operations')
    assert len(calls) == 1
    assert calls[0]['user_id'] == 'account-id'
    assert calls[0]['session_id'] == 'conversation-id'
    assert calls[0]['model_name'] == 'actual-model'
    assert calls[0]['provider'] == 'openai'
    assert (calls[0]['input_tokens'], calls[0]['output_tokens']) == (123, 45)


def test_missing_usage_is_not_invented(monkeypatch):
    calls = []
    monkeypatch.setattr('services.usage_service.record_usage', lambda **values: calls.append(values))
    _record_usage_from_response({'user_id': 'account-id'}, SimpleNamespace(usage_metadata=None))
    _record_usage_from_response({}, SimpleNamespace(usage_metadata={'input_tokens': 100}))
    assert calls == []
