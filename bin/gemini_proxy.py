#!/usr/bin/env python3
import argparse
import json
import logging
import os
import subprocess
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('gemini_proxy')

app = FastAPI()

@app.get('/health')
async def health():
    return {'status': 'ok'}

@app.get('/v1/models')
async def models():
    return {
        'object': 'list',
        'data': [
            {'id': 'gemini', 'object': 'model', 'created': int(time.time()), 'owned_by': 'google'},
            {'id': 'gemini-3.8-flash-high', 'object': 'model', 'created': int(time.time()), 'owned_by': 'google'}
        ]
    }

def format_messages_for_agy(messages):
    prompt_parts = []
    for msg in messages:
        role = msg.get('role', 'user').upper()
        content = msg.get('content', '')
        if isinstance(content, list):
            text_blocks = [c.get('text', '') for c in content if isinstance(c, dict) and c.get('type') == 'text']
            content = '\n'.join(text_blocks)
        prompt_parts.append(f'[{role}]\n{content}')
    return '\n\n'.join(prompt_parts)

@app.post('/v1/chat/completions')
async def chat_completions(req: Request):
    body = await req.json()
    model = body.get('model', 'gemini-3.8-flash-high')
    messages = body.get('messages', [])
    stream = body.get('stream', False)
    
    full_prompt = format_messages_for_agy(messages)
    logger.info(f'Received chat completion for model={model}, stream={stream}, prompt_len={len(full_prompt)}')
    
    # Esegue agy CLI con il modello Gemini 3.8 Flash
    cmd = [
        '/opt/homebrew/bin/agy',
        '-p', full_prompt,
        '--model', 'gemini-3.8-flash-high',
        '--dangerously-skip-permissions'
    ]
    
    env = os.environ.copy()
    env['HOME'] = '/Users/fabiomalagutti'
    env['PATH'] = '/Users/fabiomalagutti/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'
    env['SSH_CLIENT'] = '127.0.0.1 1234 22'
    env['SSH_CONNECTION'] = '127.0.0.1 1234 127.0.0.1 22'
    
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd='/Users/fabiomalagutti', env=env)
        stdout, stderr = proc.communicate(timeout=300)
        
        with open('/tmp/gemini_proxy_debug.log', 'a') as df:
            df.write(f'CMD: {cmd}\nRET: {proc.returncode}\nOUT: {stdout[:200]}\nERR: {stderr[:200]}\n---\n')
            
        if proc.returncode != 0:
            logger.error(f'agy error: {stderr}')
            reply_text = f'[Antigravity Execution Notice]\n{stderr or stdout}'
        else:
            reply_text = stdout
    except Exception as e:
        logger.error(f'Proxy execution exception: {e}')
        reply_text = f'Proxy Error: {str(e)}'
        
    completion_id = f'chatcmpl-{uuid.uuid4().hex[:12]}'
    created_ts = int(time.time())
    
    if stream:
        async def event_generator():
            first_chunk = {
                'id': completion_id,
                'object': 'chat.completion.chunk',
                'created': created_ts,
                'model': model,
                'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': ''}, 'finish_reason': None}]
            }
            yield f'data: {json.dumps(first_chunk)}\n\n'
            
            chunk = {
                'id': completion_id,
                'object': 'chat.completion.chunk',
                'created': created_ts,
                'model': model,
                'choices': [{'index': 0, 'delta': {'content': reply_text}, 'finish_reason': None}]
            }
            yield f'data: {json.dumps(chunk)}\n\n'
            
            end_chunk = {
                'id': completion_id,
                'object': 'chat.completion.chunk',
                'created': created_ts,
                'model': model,
                'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]
            }
            yield f'data: {json.dumps(end_chunk)}\n\n'
            yield 'data: [DONE]\n\n'
            
        return StreamingResponse(event_generator(), media_type='text/event-stream')
    else:
        return JSONResponse({
            'id': completion_id,
            'object': 'chat.completion',
            'created': created_ts,
            'model': model,
            'choices': [{
                'index': 0,
                'message': {'role': 'assistant', 'content': reply_text},
                'finish_reason': 'stop'
            }],
            'usage': {
                'prompt_tokens': len(full_prompt) // 4,
                'completion_tokens': len(reply_text) // 4,
                'total_tokens': (len(full_prompt) + len(reply_text)) // 4
            }
        })

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8015)
    args = parser.parse_args()
    uvicorn.run(app, host='127.0.0.1', port=args.port)
