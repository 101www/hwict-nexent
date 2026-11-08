"""文件式版本仓库：提案和发布物不可变，审核不等于医学核验。

只替换仓库内部的current.json指针，不覆盖data/processed/graph.json。
进程间排他锁保护状态更新；每个提案绑定基线、候选快照和验证报告哈希。
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

ROOT = Path(__file__).resolve().parents[1]
COLLECTIONS = ("nodes", "edges", "thresholds", "decision_rules", "blocks",
               "threshold_candidates", "edge_candidates", "entity_candidates", "extraction_candidates")
CANDIDATES = COLLECTIONS[5:]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value) -> str:
    payload = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def identity(prefix: str) -> str:
    return prefix + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:10]


def validate(graph: dict, ontology: dict) -> dict:
    """结构、本体端点约束、证据字符区间；不能验证医学正确性。"""
    errors = []
    indices = {}
    for key in COLLECTIONS:
        rows = graph.get(key, [])
        if not isinstance(rows, list):
            errors.append(f"{key}: 必须为数组")
            rows = []
        index = {}
        for row in rows:
            if not isinstance(row, dict) or not row.get("id") or row["id"] in index:
                errors.append(f"{key}: 缺少ID、重复ID或记录格式错误")
                continue
            index[row["id"]] = row
            if row.get("verification") != "pending" or not isinstance(row.get("confidence"), (int, float)):
                errors.append(f"{key}/{row['id']}: 自动记录必须保留pending及confidence")
            elif not 0 <= row["confidence"] <= 1:
                errors.append(f"{key}/{row['id']}: confidence越界")
        indices[key] = index
    types = {v["name"] for v in ontology.get("entity_types", [])}
    relations = {v["name"]: v for v in ontology.get("relation_types", [])}
    for node in indices["nodes"].values():
        if node.get("type") not in types:
            errors.append(f"未定义实体类型: {node.get('type')}")
    for edge in indices["edges"].values():
        spec = relations.get(edge.get("relation"))
        if spec is None:
            errors.append(f"未定义关系: {edge.get('relation')}")
        for endpoint, field in (("headId", "head"), ("tailId", "tail")):
            node = indices["nodes"].get(edge.get(endpoint))
            if node is None:
                errors.append(f"{edge['id']}: 端点不存在")
            elif spec:
                allowed = spec.get(field, "*")
                allowed = allowed if isinstance(allowed, list) else [allowed]
                if "*" not in allowed and node["type"] not in allowed:
                    errors.append(f"{edge['id']}: {field}类型{node['type']}不满足{allowed}")
    checked = 0

    def evidence(item):
        nonlocal checked
        if isinstance(item, list):
            for child in item:
                evidence(child)
        elif isinstance(item, dict):
            if "block_id" in item and "evidence" in item:
                block = indices["blocks"].get(item["block_id"])
                start, end = item.get("start"), item.get("end")
                valid = (block is not None and isinstance(start, int) and isinstance(end, int)
                         and 0 <= start < end <= len(block["raw"])
                         and block["raw"][start:end] == item["evidence"]
                         and item.get("file") == block.get("file") and item.get("page") == block.get("page"))
                if not valid:
                    errors.append(f"证据偏移或文件/页码不一致: {item.get('id', item['block_id'])}")
                checked += 1
            for child in item.values():
                if isinstance(child, (list, dict)):
                    evidence(child)

    for key in COLLECTIONS:
        evidence(graph.get(key, []))
    if graph.get("discarded"):
        errors.append("discarded不得包含被丢弃记录")
    if graph.get("meta", {}).get("ontology_version") != ontology.get("version"):
        errors.append("图谱与本体版本不一致")
    return {"passed": not errors, "errors": sorted(set(errors)), "evidence_spans_checked": checked,
            "medical_validation": "not_performed", "checked_at": now()}


def changes(before: dict, after: dict, old_schema: dict, new_schema: dict) -> dict:
    detail = {}
    for key in COLLECTIONS:
        old = {v["id"]: v for v in before.get(key, [])}
        new = {v["id"]: v for v in after.get(key, [])}
        detail[key] = {"added": sorted(new.keys() - old.keys()),
                       "modified": sorted(k for k in new.keys() & old.keys() if new[k] != old[k]),
                       "absent_from_candidate": sorted(old.keys() - new.keys()),
                       "unchanged": sum(new[k] == old[k] for k in new.keys() & old.keys())}
    schema = {}
    for key in ("entity_types", "relation_types"):
        old = {v["name"]: v for v in old_schema.get(key, [])}
        new = {v["name"]: v for v in new_schema.get(key, [])}
        schema[key] = {"added": sorted(new.keys() - old.keys()),
                       "modified": sorted(k for k in old.keys() & new.keys() if old[k] != new[k]),
                       "removed": sorted(old.keys() - new.keys())}
    return {"records": detail, "ontology": schema,
            "ontology_changed": old_schema != new_schema,
            "interpretation": "新增事实不等于本体更新；差异不是已裁决医学冲突；缺失记录完整保留于快照及evolution_retained。"}


def observation(graph: dict) -> dict:
    """离线证据检查，不生成模型答案，不冒充Java的实际工具调用。"""
    nodes = {n["id"]: n for n in graph["nodes"]}
    targets = {k for k, n in nodes.items() if n["name"] == "高血压合并糖尿病患者" and n["type"] == "Population"}
    paths = []
    for first in graph["edges"]:
        if first["relation"] != "preferredRegimenFor" or first["tailId"] not in targets:
            continue
        group = first.get("regimen_group")
        if not group:
            continue
        for second in graph["edges"]:
            if (second["headId"] == first["headId"] and second.get("regimen_group") == group
                    and second["relation"] in {"hasComponent", "hasAlternativeComponent"}
                    and second.get("supporting_evidence")):
                paths.append({"nodes": [nodes[k]["name"] for k in (first["tailId"], first["headId"], second["tailId"])],
                              "edge_ids": [first["id"], second["id"]], "hops": 2})
    followups = [{k: e.get(k) for k in ("id", "headId", "tailId", "file", "evidence")}
                 for e in graph["edges"] if e["relation"] == "followUpEvery"]
    return {"kind": "offline_evidence_observation_not_llm_or_mcp", "diabetes_paths": paths,
            "diabetes_status": "pending_evidence_found" if paths else "structured_evidence_not_found",
            "followup_assertions": followups, "sufficient": False, "verification": "pending"}


def manifests(documents: list[Path]) -> list[dict]:
    return [{"file": p.name, "path": str(p.resolve()), "sha256": digest(p.read_bytes()),
             "bytes": p.stat().st_size} for p in documents]


def build_artifacts() -> dict[str, bytes]:
    return {source.parent.name + "__" + source.name: source.read_bytes()
            for source in [*sorted((ROOT / "ontology").glob("*.json")), *sorted((ROOT / "pipeline").glob("*.py"))]}


class EvolutionStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        lock = self.root / ".write.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ValueError("版本仓库正在写入，稍后重试；异常退出后请核实进程再处理.write.lock") from exc
        try:
            os.close(fd)
            yield
        finally:
            lock.unlink(missing_ok=True)

    def state(self):
        p = self.root / "state.json"
        return read(p) if p.exists() else {"current": None, "releases": [], "proposals": {}, "events": []}

    def folder(self, kind: str, ident: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", ident):
            raise ValueError("非法版本/提案ID")
        return self.root / kind / ident

    def bundle(self, folder: Path) -> dict:
        manifest = read(folder / "manifest.json")
        for name, expected in manifest["files"].items():
            if Path(name).name != name or digest((folder / name).read_bytes()) != expected:
                raise ValueError(f"快照已改变或损坏: {folder.name}/{name}")
        return {"graph": read(folder / "graph.json"), "ontology": read(folder / "ontology.json"), "manifest": manifest}

    def _save_bundle(self, folder: Path, graph: dict, ontology: dict, sources: list[dict], extra: dict,
                     artifacts: dict[str, bytes] | None = None):
        folder.mkdir(parents=True, exist_ok=False)
        write(folder / "graph.json", graph)
        write(folder / "ontology.json", ontology)
        # 保存实际使用的规则和构建代码，不仅记录版本号。
        files = ["graph.json", "ontology.json"]
        for name, payload in (artifacts if artifacts is not None else build_artifacts()).items():
            (folder / name).write_bytes(payload)
            files.append(name)
        frozen_sources = []
        for item in sources:
            payload = Path(item["path"]).read_bytes()
            if digest(payload) != item["sha256"]:
                raise ValueError("保存快照时源文件改变，请重新生成")
            name = "source__" + item["sha256"] + ".txt"
            (folder / name).write_bytes(payload)
            if name not in files:
                files.append(name)
            frozen_sources.append({**item, "snapshot": name})
        manifest = {"created_at": now(), "sources": frozen_sources,
                    "files": {n: digest((folder / n).read_bytes()) for n in files}, **extra}
        write(folder / "manifest.json", manifest)
        return manifest

    def _event(self, state: dict, event: dict):
        event = {"id": identity("EV-"), "at": now(), **event}
        write(self.root / "events" / (event["id"] + ".json"), event)
        state["events"].append(event)
        return event

    def _commit(self, state: dict):
        # state.json是唯一权威指针；读者不必拼接多个可变文件。
        write(self.root / "state.json", state)

    def initialize(self, graph: dict, ontology: dict, docs: list[Path], label: str) -> dict:
        with self.locked():
            state = self.state()
            if state["current"]:
                raise ValueError("仓库已有基线，不重复初始化")
            report = validate(graph, ontology)
            if not report["passed"]:
                raise ValueError("基线校验失败: " + str(report["errors"][:10]))
            ident = identity("R-")
            graph = json.loads(json.dumps(graph))
            graph["meta"]["evolution"] = {"release_id": ident, "kind": "imported_baseline", "label": label,
                                            "medical_verification": "pending"}
            folder = self.folder("releases", ident)
            self._save_bundle(folder, graph, ontology, manifests(docs), {"kind": "imported_baseline", "label": label})
            state["releases"].append(ident)
            state["current"] = ident
            self._event(state, {"action": "initialize", "release_id": ident, "label": label})
            self._commit(state)
            return {"release_id": ident, "graph_path": str(folder / "graph.json"), "validation": report}

    def propose(self, documents: list[Path], label: str, ontology_path: Path | None = None) -> dict:
        from .build_graph import build
        with self.locked():
            state = self.state()
            if not state["current"]:
                raise ValueError("请先初始化基线")
            base_id = state["current"]
            base_folder = self.folder("releases", base_id)
            base = self.bundle(base_folder)
            # 自动带上基线文档；同名文件不能默默替换，已有源变化必须重新作为doc传入。
            requested = {p.name: p.resolve() for p in documents}
            if len(requested) != len(documents):
                raise ValueError("新文档存在同名文件")
            sources = {}
            for item in base["manifest"]["sources"]:
                path = requested.get(item["file"], Path(item["path"]))
                if item["file"] not in requested and digest(path.read_bytes()) != item["sha256"]:
                    raise ValueError(f"旧来源已变更，请显式通过--doc提交新版本: {path.name}")
                sources[path.name] = path
            sources.update(requested)
            source_list = list(sources.values())
            before_sources = manifests(source_list)
            artifacts = build_artifacts()
            candidate = build(source_list)
            if before_sources != manifests(source_list):
                raise ValueError("建图期间源文档改变，请重试")
            if artifacts != build_artifacts():
                raise ValueError("建图期间规则或代码改变，请重新生成")
            ontology = read(ontology_path or ROOT / "ontology/ontology.json")
            candidate["meta"]["ontology_version"] = ontology["version"]
            delta = changes(base["graph"], candidate, base["ontology"], ontology)
            if delta["ontology_changed"] and ontology["version"] == base["ontology"]["version"]:
                raise ValueError("本体内容改变时必须显式增加本体版本号")
            # 候选中未再出现或被改写的完整旧记录仍保留；不把旧业务边继续当有效断言。
            retained = list(base["graph"].get("evolution_retained", []))
            for key, diff in delta["records"].items():
                old = {v["id"]: v for v in base["graph"].get(key, [])}
                for rid in diff["modified"] + diff["absent_from_candidate"]:
                    retained.append({"collection": key, "record_id": rid, "base_release": base_id,
                                     "reason": "modified_or_absent_from_candidate", "record": old[rid],
                                     "verification": "pending", "confidence": old[rid].get("confidence", 0.0)})
            candidate["evolution_retained"] = retained
            validation = validate(candidate, ontology)
            ident = identity("P-")
            folder = self.folder("proposals", ident)
            proposal = {"id": ident, "label": label, "created_at": now(), "base_release": base_id,
                        "base_manifest_sha256": digest((base_folder / "manifest.json").read_bytes()),
                        "diff": delta, "validation": validation,
                        "before": observation(base["graph"]), "after": observation(candidate),
                        "interpretation": "流程审核只授权发布这些待核验记录，不代表临床专家认可。"}
            manifest = self._save_bundle(folder, candidate, ontology, before_sources,
                                         {"kind": "proposal", "base_release": base_id}, artifacts)
            proposal["bundle_manifest_sha256"] = digest(manifest)
            write(folder / "proposal.json", proposal)
            state["proposals"][ident] = {"status": "pending", "proposal_sha256": digest(proposal), "review_event": None}
            self._event(state, {"action": "propose", "proposal_id": ident, "label": label})
            self._commit(state)
            return proposal

    def proposal(self, ident: str, state=None):
        state = state or self.state()
        folder = self.folder("proposals", ident)
        entry = state["proposals"].get(ident)
        if not entry:
            raise ValueError("提案不存在")
        proposal = read(folder / "proposal.json")
        if digest(proposal) != entry["proposal_sha256"]:
            raise ValueError("提案内容已改变，必须重新生成并审核")
        bundle = self.bundle(folder)
        if digest(bundle["manifest"]) != proposal["bundle_manifest_sha256"]:
            raise ValueError("提案快照清单已改变")
        return proposal, bundle

    def review(self, ident: str, decision: str, reviewer: str, reason: str, actor_kind: str = "human") -> dict:
        if decision not in {"approve", "reject", "defer"} or not reviewer.strip() or not reason.strip():
            raise ValueError("请填写审核人、理由及有效审核动作")
        if actor_kind not in {"human", "automated_test"}:
            raise ValueError("审核类型无效")
        with self.locked():
            state = self.state()
            proposal, _ = self.proposal(ident, state)
            if state["proposals"][ident]["status"] == "published":
                raise ValueError("已发布提案不可改写审核结论")
            if decision == "approve" and not proposal["validation"]["passed"]:
                raise ValueError("结构/本体校验未通过，不能批准")
            event = self._event(state, {"action": "review", "proposal_id": ident, "decision": decision,
                                       "reviewer": reviewer.strip(), "reason": reason.strip(), "actor_kind": actor_kind,
                                       "proposal_sha256": digest(proposal), "scope": "engineering_publication_only_not_medical_review"})
            state["proposals"][ident].update(status={"approve": "approved", "reject": "rejected", "defer": "deferred"}[decision],
                                              review_event=event["id"])
            self._commit(state)
            return event

    def publish(self, ident: str, allow_test_review: bool = False) -> dict:
        with self.locked():
            state = self.state()
            proposal, bundle = self.proposal(ident, state)
            entry = state["proposals"][ident]
            if entry["status"] != "approved":
                raise ValueError("必须先明确批准，待审/暂缓/驳回提案不能发布")
            review = next(e for e in state["events"] if e["id"] == entry["review_event"])
            if review["actor_kind"] != "human" and not allow_test_review:
                raise ValueError("自动测试审核不能用于实际发布")
            if proposal["base_release"] != state["current"]:
                raise ValueError("提案基线已过期，请基于当前版本重新生成并审核")
            baseline = self.folder("releases", state["current"])
            self.bundle(baseline)
            if digest((baseline / "manifest.json").read_bytes()) != proposal["base_manifest_sha256"]:
                raise ValueError("基线清单已改变")
            validation = validate(bundle["graph"], bundle["ontology"])
            if not validation["passed"]:
                raise ValueError("发布前校验失败")
            release_id = identity("R-")
            graph = bundle["graph"]
            graph["meta"]["evolution"] = {"release_id": release_id, "parent_release": state["current"],
                                            "proposal_id": ident, "review_event": review["id"],
                                            "review_actor_kind": review["actor_kind"], "medical_verification": "pending"}
            folder = self.folder("releases", release_id)
            # 发布的是被审核的规则/代码快照，不能用发布当天磁盘上的文件冒充构建时版本。
            folder.mkdir(parents=True, exist_ok=False)
            for name in bundle["manifest"]["files"]:
                shutil.copyfile(self.folder("proposals", ident) / name, folder / name)
            write(folder / "graph.json", graph)
            manifest = {**bundle["manifest"], "created_at": now(), "kind": "release", "proposal_id": ident,
                        "review": review, "parent_release": state["current"]}
            manifest["files"] = {n: digest((folder / n).read_bytes()) for n in manifest["files"]}
            write(folder / "manifest.json", manifest)
            state["current"] = release_id
            state["releases"].append(release_id)
            entry.update(status="published", release_id=release_id)
            self._event(state, {"action": "publish", "proposal_id": ident, "release_id": release_id,
                                "actor_kind": review["actor_kind"]})
            self._commit(state)
            return {"release_id": release_id, "graph_path": str(folder / "graph.json"), "validation": validation}

    def rollback(self, release_id: str, reviewer: str, reason: str) -> dict:
        if not reviewer.strip() or not reason.strip():
            raise ValueError("回滚需要操作人和理由")
        with self.locked():
            state = self.state()
            if release_id not in state["releases"]:
                raise ValueError("回滚目标不是已发布版本")
            self.bundle(self.folder("releases", release_id))
            previous = state["current"]
            state["current"] = release_id
            event = self._event(state, {"action": "rollback", "from_release": previous, "release_id": release_id,
                                       "reviewer": reviewer, "reason": reason})
            self._commit(state)
            return event

    def current_graph_path(self) -> Path:
        ident = self.state()["current"]
        if not ident:
            raise ValueError("尚未初始化")
        folder = self.folder("releases", ident)
        self.bundle(folder)
        return folder / "graph.json"
