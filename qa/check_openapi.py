"""Offline contract integrity check: paths, operations, local references and secrets."""
import json
from pathlib import Path
import re

root=Path(__file__).resolve().parents[1]
document=json.loads((root/'docs/openapi.yaml').read_text(encoding='utf-8'))
assert document['openapi']=='3.0.3'
seen=set()
def check(value):
    if isinstance(value,dict):
        if '$ref' in value:
            assert value['$ref'].startswith('#/'), value
            target=document
            for part in value['$ref'][2:].split('/'): target=target[part]
        for item in value.values():check(item)
    elif isinstance(value,list):
        for item in value:check(item)
check(document)
for path,methods in document['paths'].items():
    for method,operation in methods.items():
        assert operation['operationId'] not in seen
        seen.add(operation['operationId'])
        required=set(re.findall(r'{([^}]+)}',path))
        declared={p['name'] for p in operation.get('parameters',[]) if p['in']=='path' and p['required']}
        assert required==declared,(path,required,declared)
        assert any(code.startswith('2') for code in operation['responses'])
        if method=='post':
            assert any(p['name']=='X-CSRFToken' for p in operation['parameters'])
            if not path.startswith('/auth/'):
                assert any(p['name']=='Idempotency-Key' for p in operation['parameters'])
for name,schema in document['components']['schemas'].items():
    if name.endswith('Input'):continue
    assert not {'password','password_hash','session_key'} & set(schema.get('properties',{})),name
print(f'PASS: {len(document["paths"])} paths, {len(seen)} unique operations; all references and path parameters resolved')
