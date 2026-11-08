"""同一JVM、同一MCP会话验证发布/回滚；隔离仓库使用显式自动测试审核。"""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'java-mcp')]
from pipeline.evolution import EvolutionStore, read, write, digest
from tools.evolve_graph import seed
from mcp_client import McpClient

def main():
    output = ROOT / 'docs/validation/evolution-live-mcp.json'
    formal = ROOT / 'data/processed/graph.json'
    original_hash = digest(formal.read_bytes())
    with tempfile.TemporaryDirectory(prefix='live-mcp-', dir=ROOT / 'data/evolution') as temp:
        store = EvolutionStore(Path(temp))
        prepared = seed(store)
        initial, pid = prepared['baseline']['release_id'], prepared['pending_proposal']
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        jar = ROOT / 'java-mcp/spring-ai-mcp-server/target/spring-ai-mcp-server-0.1.0.jar'
        log_path = output.with_suffix('.log')
        with log_path.open('w', encoding='utf-8') as log:
            proc = subprocess.Popen(['java', '-Dkg.allowTestReleases=true', '-jar', str(jar),
                '--server.address=127.0.0.1', f'--server.port={port}', '--kg.graph-path=',
                f'--kg.evolution-store={store.root}'], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            report = {'tested_at': datetime.now().astimezone().isoformat(), 'java_pid': proc.pid,
                'kind': 'actual_sse_same_jvm_same_mcp_session_not_nexent_or_model',
                'review_actor_kind': 'automated_test', 'phases': []}
            try:
                deadline = time.monotonic() + 45
                while True:
                    if proc.poll() is not None:
                        raise RuntimeError(f'Java启动失败，见{log_path}')
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.3): break
                    except OSError:
                        if time.monotonic() > deadline: raise TimeoutError('Java未就绪')
                        time.sleep(.2)
                client = McpClient(f'http://127.0.0.1:{port}/sse')
                def observe(phase, expected_release, count):
                    assert proc.poll() is None
                    status = client.call('graph_status', {})
                    result = client.call('resolve_regimen', {'population':'高血压合并糖尿病患者'})
                    paths = [p for item in result['items'] for p in item.get('paths', [])]
                    for data in (status, result):
                        assert data['knowledge_version']['release_id'] == expected_release
                        assert data['knowledge_version']['verification'] == 'pending'
                    assert len(paths) == count, (phase, len(paths))
                    assert all(p['hops'] == 2 for p in paths)
                    report['phases'].append({'phase':phase, 'java_pid':proc.pid,
                        'release_id':expected_release, 'path_count':len(paths),
                        'graph_status':status, 'resolve_regimen':result})
                    print('PASS', phase, 'same_java_pid=',proc.pid, 'paths=',len(paths), flush=True)
                observe('pending_does_not_change_agent', initial, 0)
                store.review(pid, 'approve', 'automated_live_mcp_test',
                    '自动化发布回归；非人工或医学核验', 'automated_test')
                observe('approved_but_not_published', initial, 0)
                published = store.publish(pid, allow_test_review=True)['release_id']
                observe('published_without_restart', published, 2)
                store.rollback(initial, 'automated_live_mcp_test', '同进程回滚测试', 'automated_test')
                observe('rollback_without_restart', initial, 0)
                state = store.state()
                state['current'] = pid
                write(store.root / 'state.json', state)
                try:
                    client.call('graph_status', {})
                except RuntimeError as exc:
                    report['invalid_pointer_rejected'] = str(exc)
                else:
                    raise AssertionError('未发布提案指针不应加载')
                state['current'] = initial
                write(store.root / 'state.json', state)
                observe('recovered_pointer', initial, 0)
                assert original_hash == digest(formal.read_bytes())
                report.update(all_passed=True, formal_graph_unchanged_sha256=original_hash,
                    limits=['历史入库回放，非新指南发布', '自动测试审核，非临床审核', '本报告不是Nexent页面实测'])
                write(output, report)
            finally:
                proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
    print('Saved', output)

if __name__ == '__main__': main()
