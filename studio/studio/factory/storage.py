"""Versioned, atomic local artifacts; metadata does not affect reproducibility."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

VERSION = 'factory-simulation/2'


def content_hash(run):
    content = {k:v for k,v in run.items() if k not in ('run_id','created_at','content_hash')}
    encoded = json.dumps(content,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def atomic_text(path, writer):
    path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as stream:
            writer(stream); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def save(path,run):
    atomic_text(path,lambda stream: json.dump(run,stream,ensure_ascii=False,allow_nan=False,separators=(',',':')))


def read_json(path):
    def invalid(value): raise ValueError(f'non-finite JSON number: {value}')
    with open(path,encoding='utf-8-sig') as stream: return json.load(stream,parse_constant=invalid)


def load(path):
    run = read_json(path)
    if not isinstance(run,dict) or run.get('schema_version') != VERSION:
        raise ValueError('unsupported factory artifact version')
    if run.get('content_hash') != content_hash(run): raise ValueError('artifact content hash mismatch')
    return run


def save_events(path,run):
    def write(stream):
        for event in run['events']:
            stream.write(json.dumps({'schema_version':'factory-event/1','run_id':run['run_id'],
                                     'content_hash':run['content_hash'],**event},ensure_ascii=False,allow_nan=False)+'\n')
    atomic_text(path,write)
