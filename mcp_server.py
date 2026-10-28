#!/usr/bin/env python3
"""MCP server for the Sibelius bridge (stdio, Python standard library only).

Tools:
  sibelius     run ClaudeBridge commands in the open Sibelius score (via ./sib)
  clicktrack   build a dry, exact click track from a raw click export + MIDI export

Register with Claude Code:   claude mcp add sibelius -- python3 /path/to/sibelius-bridge/mcp_server.py
Claude Desktop config entry: {"command": "python3", "args": ["/path/to/sibelius-bridge/mcp_server.py"]}
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = '0.1.0'

COMMANDS = """Commands (one per array item, fields split by |, P = part index from `parts`, 0 = full score):
info | parts | staves|P | map|P[|from|to] | break|P|bars|system,page,none,NotEndOfSystem,...
setup|P[|StaffSize=7,PageTopMargin=12,...] | rules|P[|SpacesBetweenSystems=10,...]
optimize|P[|from|to] | resetspace|P | resetpos|P | multirests|P|0/1 | split|P|bars|0/1
hideempty|P|staves|from|to | showempty|... | texts|P | replacetext|P|find|repl | deltext|P|exact
settext|P|style|text | scoreinfo[|Title=...,Composer=...] | dynabove|P|textDy|hairpinDy
nudge|P|bar|style|dx|dy | show|P | pdf|P|/abs/path.pdf | save[|/abs/copy.sib]
Bars are internal bar numbers; ranges look like 4,8,12 or 1-40. Plugin edits cannot be undone in
Sibelius: save a numbered copy first. Special: ["reload"] reinstalls the plugin and restarts Sibelius."""

TOOLS = [
    {
        'name': 'sibelius',
        'description': 'Run ClaudeBridge commands in the score open in Sibelius 2020 and return the '
                       'plugin output. Several commands run in one plugin pass. Sibelius must be running '
                       'with the Claude Bridge shortcut assigned, and is brought to the front.\n' + COMMANDS,
        'inputSchema': {
            'type': 'object',
            'properties': {'commands': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1,
                                        'description': "e.g. [\"parts\", \"map|3\"]"}},
            'required': ['commands'],
        },
    },
    {
        'name': 'clicktrack',
        'description': 'Turn a Sibelius/NotePerformer click export into a dry click on the exact '
                       'tempo-map grid (keeps accents, beats and soft subdivision clicks) and verify '
                       'the written file. raw_wav: File > Export > Audio with only the click soloed, '
                       'WAV 24-bit. midi: File > Export > MIDI of the same score.',
        'inputSchema': {
            'type': 'object',
            'properties': {'raw_wav': {'type': 'string'}, 'midi': {'type': 'string'},
                           'out_wav': {'type': 'string'}},
            'required': ['raw_wav', 'midi', 'out_wav'],
        },
    },
]


def run(argv, timeout):
    try:
        p = subprocess.run(argv, cwd=HERE, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f'timed out after {timeout}s', True
    out = (p.stdout + p.stderr).strip()
    return out or f'exit code {p.returncode}', p.returncode != 0


def call_tool(name, args):
    if name == 'sibelius':
        cmds = args.get('commands') or []
        if not cmds or not all(isinstance(c, str) and c and '\n' not in c for c in cmds):
            return 'commands must be a non-empty list of one-line strings', True
        return run([os.path.join(HERE, 'sib'), *cmds], timeout=600)
    if name == 'clicktrack':
        paths = [os.path.expanduser(args.get(k, '')) for k in ('raw_wav', 'midi', 'out_wav')]
        missing = [p for p in paths[:2] if not os.path.isfile(p)]
        if missing:
            return f'file not found: {", ".join(missing)}', True
        return run([sys.executable, os.path.join(HERE, 'clicktrack.py'), *paths], timeout=900)
    return f'unknown tool: {name}', True


def handle(msg):
    """one JSON-RPC message in, the response dict out (None for notifications)"""
    method, mid = msg.get('method'), msg.get('id')
    if mid is None:
        return None
    if method == 'initialize':
        version = msg.get('params', {}).get('protocolVersion', '2025-06-18')
        result = {'protocolVersion': version, 'capabilities': {'tools': {}},
                  'serverInfo': {'name': 'sibelius-bridge', 'version': VERSION}}
    elif method == 'ping':
        result = {}
    elif method == 'tools/list':
        result = {'tools': TOOLS}
    elif method == 'tools/call':
        params = msg.get('params', {})
        text, is_error = call_tool(params.get('name'), params.get('arguments') or {})
        result = {'content': [{'type': 'text', 'text': text}], 'isError': is_error}
    else:
        return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32601, 'message': f'method not found: {method}'}}
    return {'jsonrpc': '2.0', 'id': mid, 'result': result}


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line))
        except json.JSONDecodeError:
            reply = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'parse error'}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    main()
