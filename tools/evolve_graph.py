"""可进化版本工作台入口；只操作独立版本仓库，不覆盖正式graph.json。"""
from __future__ import annotations

import argparse
from datetime import datetime
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.build_graph import build
from pipeline.evolution import EvolutionStore, digest, observation, read, write

DEFAULT_STORE = ROOT / "data/evolution/workbench"
PRODUCTION_STORE = ROOT / "data/evolution/production"
STANDARD = ROOT / "data/raw/WS-T872-2025_重排.txt"
PRIMARY = ROOT / "data/raw/国家基层高血压防治管理指南2025版_重排.txt"
ONTOLOGY = ROOT / "ontology/ontology.json"


def seed(store: EvolutionStore):
    """重放真实资料历史入库；不声称发现新发布的指南。"""
    state = store.state()
    if state["current"]:
        return {"status": "existing_workbench_reused", "store": str(store.root)}
    base = store.initialize(build(STANDARD), read(ONTOLOGY), [STANDARD], "历史回放：仅管理标准")
    proposal = store.propose([PRIMARY], "历史回放：加入已持有的基层指南；不是新指南发布")
    return {"baseline": base, "pending_proposal": proposal["id"], "store": str(store.root),
            "review_status": "pending_no_human_review_performed"}


def production(store: EvolutionStore):
    """将现有完整图谱纳入版本管理；不批准任何更新提案或医学结论。"""
    if store.state()["current"]:
        store.current_graph_path()  # 校验当前快照，不覆盖已有发布状态。
        return {"status": "existing_production_reused", "store": str(store.root)}
    graph = read(ROOT / "data/processed/graph.json")
    docs = [ROOT / "data/raw" / name for name in (
        "WS-T872-2025_重排.txt", "国家基层高血压防治管理指南2025版_重排.txt", "中国高血压临床实践指南2025版_重排.txt")]
    return store.initialize(graph, read(ONTOLOGY), docs,
                            "正式基线：沿用现有三份全文图谱；自动知识仍待核验")


def demo(root: Path, report_path: Path):
    """自动回归模拟审核，用测试身份留痕，绝不当成人工核验。"""
    if (root / "state.json").exists():
        raise ValueError("演示仓库已存在；请换一个新目录以保留旧证据")
    formal = ROOT / "data/processed/graph.json"
    original_hash = digest(formal.read_bytes())
    store = EvolutionStore(root)
    prepared = seed(store)
    pid = prepared["pending_proposal"]
    initial = store.state()["current"]
    proposal, bundle = store.proposal(pid)
    blocked = False
    try:
        store.publish(pid)
    except ValueError:
        blocked = True
    assert blocked
    assert not proposal["before"]["diabetes_paths"]
    assert len(proposal["after"]["diabetes_paths"]) == 2
    review = store.review(pid, "approve", "automated_acceptance_test", "自动验收模拟流程审核；不代表人工或临床审核", "automated_test")
    blocked_test = False
    try:
        store.publish(pid)
    except ValueError:
        blocked_test = True
    assert blocked_test
    released = store.publish(pid, allow_test_review=True)
    released_bundle = store.bundle(store.folder("releases", released["release_id"]))
    after = observation(released_bundle["graph"])
    old = store.bundle(store.folder("releases", initial))["graph"]
    retained = released_bundle["graph"].get("evolution_retained", [])
    retained_count = {}
    for key in ("threshold_candidates", "entity_candidates", "edge_candidates", "extraction_candidates"):
        current = {v["id"]: v for v in released_bundle["graph"].get(key, [])}
        missing = [v["id"] for v in old.get(key, []) if current.get(v["id"]) != v
                   and not any(r["collection"] == key and r["record"] == v for r in retained)]
        assert not missing
        retained_count[key] = {"baseline_count": len(old.get(key, [])), "lost_records": missing}
    rolled = store.rollback(initial, "automated_acceptance_test", "回滚回归测试；不删除更新版本", "automated_test")
    restored = observation(store.bundle(store.folder("releases", initial))["graph"])
    assert restored == proposal["before"]
    assert formal.read_bytes() and digest(formal.read_bytes()) == original_hash
    report = {"tested_at": datetime.now().astimezone().isoformat(),
              "kind": "real_document_historical_ingestion_replay_with_explicit_automated_reviewer",
              "store": str(root.resolve()), "baseline_release": initial, "proposal_id": pid,
              "published_release": released["release_id"], "review": review,
              "before": proposal["before"], "after": after, "rollback": rolled, "restored": restored,
              "unreviewed_publish_blocked": blocked, "test_review_requires_explicit_test_flag": blocked_test,
              "validation": proposal["validation"], "retention": retained_count,
              "formal_graph_unchanged_sha256": original_hash, "all_passed": True,
              "limits": ["不是新指南版本对比", "没有人工或医学审核", "不是Nexent页面实测",
                         "本体内容本次未变化，验证的是知识更新及本体约束检查", "更新后仍为pending"]}
    write(report_path, report)
    print("PASS 待审阻止发布 / 两跳证据前后变化 / 测试审核隔离 / 候选完整保留 / 回滚恢复 / 正式图谱未改")
    print("Report:", report_path)
    return report


def serve(store: EvolutionStore, port: int, test_review: bool = False, live: bool = False):
    token = secrets.token_urlsafe(32)
    esc = lambda value: html.escape(str(value), quote=True)

    def page(selected: str | None):
        state = store.state()
        statuses = {"pending":"待审核", "approved":"已批准，待发布", "deferred":"暂缓，继续待核验", "rejected":"已驳回本次发布", "published":"已发布"}
        labels = {"nodes":"实体节点", "edges":"关系断言", "thresholds":"可计算阈值", "decision_rules":"组合规则", "blocks":"原文块",
                  "threshold_candidates":"阈值候选", "edge_candidates":"关系候选", "entity_candidates":"实体候选", "extraction_candidates":"原文片段候选"}
        sections = ["<h1>知识更新审核工作台</h1>",
                    ("<p>正式知识版本管理：已连接配置为跟随本仓库的 Java MCP。批准并发布后，下次工具调用读取新版本；候选知识继续待核验。</p>" if live else "<p>历史回放工作台：与正式智能体隔离，不影响其回答。</p>"),
                    "<p>流程批准不等于医学核验，自动抽取记录继续 pending。</p>",
                    f"<p>当前版本：<code>{esc(state['current'])}</code>　<a href='/'>刷新</a></p>"]
        if live:
            sections.append("<h2>和 Nexent 怎么连接</h2><p>你仍在 <a href='http://192.168.100.150:3000/' target='_blank' rel='noreferrer'>原 Nexent 聊天窗口</a> 提问。连接链路：Nexent → kg-tools-real MCP → Java 8081 → 本仓库当前发布版本。</p>")
            sections.append("<p><a href='/mcp-status.json'>检查 Java MCP 实际正在使用的知识版本</a>。此检查从本机发起，不等于 Nexent 页面验收；请在 Nexent 提问：调用 graph_status，告诉我当前 release_id、文档数量和核验状态。</p>")
        if test_review:
            sections.append("<p class='notice'>自动验收专用：本页面审核及回滚记录为automated_test，不会记作人工审核。</p>")
        sections.append("<h2>变更提案</h2><ul>")
        for pid, entry in state["proposals"].items():
            p, _ = store.proposal(pid, state)
            sections.append(f"<li><a href='/?proposal={esc(pid)}'>{esc(p['label'])}</a> · {esc(statuses[entry['status']])}</li>")
        sections.append("</ul>")
        if selected:
            proposal, bundle = store.proposal(selected, state)
            status = state["proposals"][selected]["status"]
            sections.append(f"<h2>{esc(proposal['label'])}</h2><p>状态：{esc(statuses[status])}；基线：{esc(proposal['base_release'])}</p>")
            sections.append("<table><tr><th>记录集合</th><th>新增</th><th>修改</th><th>候选未再出现（完整保留）</th></tr>")
            for name, diff in proposal["diff"]["records"].items():
                sections.append(f"<tr><td>{esc(labels.get(name,name))}</td><td>{len(diff['added'])}</td><td>{len(diff['modified'])}</td><td>{len(diff['absent_from_candidate'])}</td></tr>")
            sections.append("</table>")
            schema = proposal["diff"]["ontology_changed"]
            sections.append(f"<p>本体内容变化：{'有' if schema else '无（本次是新增知识，未扩充本体）'}；结构和证据校验：{'通过' if proposal['validation']['passed'] else '未通过'}</p>")
            if not proposal["validation"]["passed"]:
                sections.append(f"<pre>{esc(json.dumps(proposal['validation'],ensure_ascii=False,indent=2))}</pre>")
            sections.append("<h3>同一个问题：合并糖尿病的高血压患者首选哪类药？</h3>")
            desc = lambda x: "找到两跳证据（待核验）" if x == "pending_evidence_found" else "未找到该人群的结构化方案证据"
            sections.append(f"<p>更新前：{desc(proposal['before']['diabetes_status'])}；更新后：{desc(proposal['after']['diabetes_status'])}。</p>")
            sections.append("<p>以下是离线证据观察，不是模型问答。更新后证据待核验，不自动给个体处方。</p>")
            edges = {v["id"]: v for v in bundle["graph"]["edges"]}
            for path in proposal["after"]["diabetes_paths"]:
                sections.append(f"<h4>{esc(' → '.join(path['nodes']))}</h4>")
                for eid in path["edge_ids"]:
                    e = edges[eid]
                    sections.append(f"<details><summary>{esc(e['relation'])} · {esc(e['file'])} · p{esc(e['page'])} §{esc(e['section'])}</summary><pre>{esc(json.dumps(e,ensure_ascii=False,indent=2))}</pre></details>")
            sections.append(f"<p><a href='/proposal.json?id={esc(selected)}'>下载完整提案JSON（含差异ID、校验和前后观察）</a></p>")
            sections.append(f"<p><a href='/candidate.json?id={esc(selected)}'>查看完整候选图谱（全部新增、修改记录及原文）</a></p>")
            if status != "published":
                sections.append(f"""<form method='post' action='/review'>
<input type='hidden' name='token' value='{token}'><input type='hidden' name='proposal' value='{esc(selected)}'>
<p><label>审核人 <input name='reviewer' required maxlength='100'></label></p>
<p><label>审核理由 <textarea name='reason' required maxlength='2000'></textarea></label></p>
<p>这里只确认是否允许发布这批待核验知识，不代表临床审核。请先展开原文检查。</p>
<button name='decision' value='defer'>保留待核验／暂缓</button>
<button name='decision' value='reject'>驳回本次发布（保留全部记录）</button>
<button name='decision' value='approve'>批准流程发布</button></form>""")
            if status == "approved":
                sections.append(f"<form method='post' action='/publish'><input type='hidden' name='token' value='{token}'><input type='hidden' name='proposal' value='{esc(selected)}'><button>发布已批准版本</button></form>")
        sections.append("<h2>加入资料，生成下一份提案</h2><p>先把带页码和章节的重排文本放入项目data/raw目录；刷新页面后选择。系统会保留基线已有来源并重新比对，新提案不会自动发布。</p>")
        options = "".join(f"<option value='{esc(p.name)}'>{esc(p.name)}</option>" for p in sorted((ROOT / "data/raw").glob("*_重排.txt")))
        sections.append(f"<form method='post' action='/propose'><input type='hidden' name='token' value='{token}'><p><label>资料文件 <select name='document' required>{options}</select></label></p><p><label>提案说明 <input name='label' required maxlength='200'></label></p><button>生成待审提案</button></form>")
        sections.append("<h2>发布历史与回滚</h2><p>回滚改变本仓库的当前版本指针，保留后续版本。跟随本仓库的Java MCP下次工具调用即生效；固定文件模式需重启。</p>")
        for rid in reversed(state["releases"]):
            folder = store.folder("releases", rid)
            bundle = store.bundle(folder)
            sections.append(f"<details><summary>{esc(rid)} · {esc(bundle['manifest']['kind'])}</summary><p>Java加载路径：<code>{esc(folder / 'graph.json')}</code></p>")
            if rid != state["current"]:
                sections.append(f"<form method='post' action='/rollback'><input type='hidden' name='token' value='{token}'><input type='hidden' name='release' value='{esc(rid)}'><label>操作人 <input name='reviewer' required></label><label>理由 <input name='reason' required></label><button>回滚到此版本</button></form>")
            sections.append("</details>")
        sections.append(f"<details><summary>完整流程事件（含操作人、理由和审核类型）</summary><pre>{esc(json.dumps(state['events'],ensure_ascii=False,indent=2))}</pre></details>")
        body = "\n".join(sections)
        return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>知识更新审核工作台</title><style>body{max-width:1100px;margin:32px auto;padding:0 20px;font:16px/1.7 system-ui;color:#172b4d;background:#f6f8fc}"
                "h1,h2{color:#163d74}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #ccd7e8;padding:8px;text-align:left}"
                "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#fff;padding:16px;border:1px solid #d8e0ec}details,form{background:white;padding:12px;margin:12px 0}"
                "input,textarea,button,select{font:inherit;margin:5px;padding:8px;max-width:95%}textarea{width:80%;height:70px}button{cursor:pointer}code{overflow-wrap:anywhere}"
                ".notice{background:#fff1c2;border:1px solid #d4a934;padding:12px}h4{overflow-wrap:anywhere}form{border:1px solid #d8e0ec}</style>" + body + "</html>")

    class Handler(BaseHTTPRequestHandler):
        def send(self, code, body, kind="text/html; charset=utf-8"):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def do_GET(self):
            if not self.allowed():
                return self.send(403, "Host不允许")
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            try:
                if url.path == "/mcp-status.json" and live:
                    from tools.check_live_connection import check
                    result = check(store)
                    return self.send(200, json.dumps(result, ensure_ascii=False, indent=2), "application/json; charset=utf-8")
                if url.path in {"/proposal.json", "/candidate.json"}:
                    proposal, bundle = store.proposal(query.get("id", [""])[0])
                    payload = proposal if url.path == "/proposal.json" else bundle["graph"]
                    return self.send(200, json.dumps(payload,ensure_ascii=False,indent=2), "application/json; charset=utf-8")
                if url.path != "/":
                    return self.send(404, "页面不存在")
                selected = query.get("proposal", [None])[0]
                if live and selected and selected not in store.state()["proposals"]:
                    if selected in EvolutionStore(DEFAULT_STORE).state()["proposals"]:
                        return self.send(200, "<meta charset='utf-8'><h1>这是历史回放提案</h1><p>正式工作台已与三份全文图谱连接。旧提案完整保存在独立历史仓库。</p><p><a href='/'>进入正式知识工作台</a></p><p><a href='http://127.0.0.1:8766/?proposal=" + esc(selected) + "'>查看原历史回放提案</a>（需保持历史回放服务运行）</p>")
                self.send(200, page(selected))
            except (ValueError, OSError, KeyError, RuntimeError) as exc:
                self.send(400, esc(exc))

        def do_POST(self):
            if not self.allowed():
                return self.send(403, "Host不允许")
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16000:
                    return self.send(400, "请求过大或为空")
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(size).decode("utf-8")).items()}
                if not secrets.compare_digest(form.get("token", ""), token):
                    return self.send(403, "请从本地工作台页面提交审核")
                pid = form.get("proposal", "")
                if self.path == "/review":
                    store.review(pid, form.get("decision", ""), form.get("reviewer", ""), form.get("reason", ""),
                                 "automated_test" if test_review else "human")
                elif self.path == "/publish":
                    store.publish(pid, allow_test_review=test_review)
                elif self.path == "/propose":
                    document = form.get("document", "")
                    choices = {p.name:p for p in (ROOT / "data/raw").glob("*_重排.txt") if p.is_file() and not p.is_symlink()}
                    if document not in choices or not form.get("label", "").strip():
                        raise ValueError("请选择data/raw中的重排文本并填写提案说明")
                    pid = store.propose([choices[document]],form["label"].strip())["id"]
                elif self.path == "/rollback":
                    store.rollback(form.get("release", ""), form.get("reviewer", ""), form.get("reason", ""),
                                   "automated_test" if test_review else "human")
                else:
                    return self.send(404, "动作不存在")
                self.send_response(303)
                self.send_header("Location", "/?proposal=" + pid if pid else "/")
                self.end_headers()
            except (ValueError, KeyError, OSError) as exc:
                self.send(400, "<p>操作未完成：" + esc(exc) + "</p><a href='/'>返回</a>")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"审核工作台：http://127.0.0.1:{port}/", flush=True)
    print("仅本机访问；Ctrl+C停止。当前模式：" + ("正式版本仓库，发布后MCP下次调用生效" if live else "独立历史回放"), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path)
    parser.add_argument("--production", action="store_true", help="使用正式三文档版本仓库；不创建历史演示提案")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("prepare", help="用真实资料历史回放准备待人工审核的工作台")
    subs.add_parser("status")
    subs.add_parser("init-production", help="导入现有三文档图谱为正式基线，不批准更新")
    init = subs.add_parser("init")
    init.add_argument("--doc", nargs="+", type=Path, required=True)
    init.add_argument("--label", required=True)
    propose = subs.add_parser("propose")
    propose.add_argument("--doc", nargs="+", type=Path, required=True)
    propose.add_argument("--label", required=True)
    propose.add_argument("--ontology", type=Path)
    review = subs.add_parser("review")
    review.add_argument("proposal")
    review.add_argument("decision", choices=["approve", "reject", "defer"])
    review.add_argument("--reviewer", required=True)
    review.add_argument("--reason", required=True)
    publish = subs.add_parser("publish")
    publish.add_argument("proposal")
    rollback = subs.add_parser("rollback")
    rollback.add_argument("release")
    rollback.add_argument("--reviewer", required=True)
    rollback.add_argument("--reason", required=True)
    web = subs.add_parser("serve")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--test-review", action="store_true", help="隔离测试仓库专用；全部审核记为automated_test")
    run = subs.add_parser("demo")
    run.add_argument("--report", type=Path, default=ROOT / "docs/validation/evolution-replay.json")
    launch = subs.add_parser("launch-java")
    launch.add_argument("--port", type=int)
    args = parser.parse_args()
    args.store = args.store or (PRODUCTION_STORE if args.production or args.command == "init-production" else DEFAULT_STORE)
    if args.production and args.store.resolve() != PRODUCTION_STORE.resolve():
        parser.error("--production 不与自定义 --store 混用")
    live = args.store.resolve() == PRODUCTION_STORE.resolve()
    store = EvolutionStore(args.store)
    try:
        if args.command == "init-production":
            result = production(store)
        elif args.command == "prepare":
            result = production(store) if live else seed(store)
        elif args.command == "init":
            result = store.initialize(build(args.doc), read(ONTOLOGY), args.doc, args.label)
        elif args.command == "propose":
            result = store.propose(args.doc, args.label, args.ontology)
        elif args.command == "review":
            result = store.review(args.proposal,args.decision,args.reviewer,args.reason)
        elif args.command == "publish":
            result = store.publish(args.proposal)
        elif args.command == "rollback":
            result = store.rollback(args.release,args.reviewer,args.reason)
        elif args.command == "status":
            result = store.state()
            result["current_graph_path"] = str(store.current_graph_path())
        elif args.command == "serve":
            if args.test_review and args.store.resolve() in {DEFAULT_STORE.resolve(), PRODUCTION_STORE.resolve()}:
                raise ValueError("测试审核模式必须--store指定独立测试仓库")
            production(store) if live else seed(store)
            serve(store, args.port, args.test_review, live)
            return 0
        elif args.command == "demo":
            if args.store.resolve() in {DEFAULT_STORE.resolve(), PRODUCTION_STORE.resolve()}:
                raise ValueError("自动回放必须--store指定独立测试仓库，不能使用人工工作台目录")
            demo(args.store,args.report)
            return 0
        elif args.command == "launch-java":
            args.port = args.port if args.port is not None else (8081 if live else 8083)
            jar = ROOT / "java-mcp/spring-ai-mcp-server/target/spring-ai-mcp-server-0.1.0.jar"
            production(store) if live else store.current_graph_path()
            print(f"启动Java跟随已发布版本：{store.root}", flush=True)
            return subprocess.call(["java", "-jar", str(jar), f"--server.port={args.port}", f"--kg.graph-path=", f"--kg.evolution-store={store.root}"], cwd=ROOT)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print("未完成：",exc,file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
