"""MCP protocol smoke test: handshake, tool list, argument errors. Needs no Sibelius."""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    msgs = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
         'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '0'}}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
         'params': {'name': 'clicktrack', 'arguments': {'raw_wav': '/nope.wav', 'midi': '/nope.mid', 'out_wav': '/tmp/x.wav'}}},
        {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'sibelius', 'arguments': {'commands': []}}},
        {'jsonrpc': '2.0', 'id': 5, 'method': 'resources/list'},
    ]
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'mcp_server.py')], input=''.join(json.dumps(m) + '\n' for m in msgs),
                       capture_output=True, text=True, timeout=30)
    replies = {r['id']: r for r in map(json.loads, p.stdout.splitlines())}
    assert sorted(replies) == [1, 2, 3, 4, 5], replies               # the notification gets no reply
    assert replies[1]['result']['serverInfo']['name'] == 'sibelius-bridge'
    assert replies[1]['result']['protocolVersion'] == '2025-06-18'
    assert [t['name'] for t in replies[2]['result']['tools']] == ['sibelius', 'clicktrack']
    assert replies[3]['result']['isError'] and 'not found' in replies[3]['result']['content'][0]['text']
    assert replies[4]['result']['isError']
    assert replies[5]['error']['code'] == -32601
    print('mcp server: handshake, tools/list and error paths ok')


if __name__ == '__main__':
    main()
