import os
import re
import uuid
import json
import logging
import tempfile
import textwrap
import inspect
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple, Callable, Union

import boto3
from botocore.exceptions import ClientError
from mcp.server.fastmcp import FastMCP

import graphviz
import vl_convert as vlc

from mcp_tools.status import update_job_status
from tool_instructions import tool_instructions_for

mcp = FastMCP("Diagram-Tools-Service")

LOG_LEVEL = os.getenv("DIAGRAM_LOG_LEVEL", "INFO").upper()
logging.basicConfig(stream=os.sys.stderr, level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("diagram_mcp")


def _tool(name: str):
    def decorator(func):
        doc = tool_instructions_for(name)
        if doc:
            func.__doc__ = doc
        return mcp.tool()(func)
    return decorator

USE_S3 = os.getenv("USE_S3", "false").lower() == "true"
S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
DOWNLOADS_BUCKET = (os.getenv("DOWNLOADS_BUCKET", "").strip() or S3_BUCKET)
DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", "/tmp/downloads")
DEFAULT_REGION = os.getenv("DEFAULT_AWS_REGION", "us-east-1")
URL_EXPIRES_SECONDS = max(60, int(os.getenv("DIAGRAM_URL_EXPIRES_SECONDS", "86400")))

MAX_POINTS = int(os.getenv("DIAGRAM_MAX_POINTS", "5000"))
MAX_NODES = int(os.getenv("DIAGRAM_MAX_NODES", "80"))
MAX_EDGES = int(os.getenv("DIAGRAM_MAX_EDGES", "260"))
MAX_LANES = int(os.getenv("DIAGRAM_MAX_LANES", "12"))
MAX_STEPS = int(os.getenv("DIAGRAM_MAX_STEPS", "100"))
MAX_PARTICIPANTS = int(os.getenv("DIAGRAM_MAX_PARTICIPANTS", "18"))
MAX_MESSAGES = int(os.getenv("DIAGRAM_MAX_MESSAGES", "160"))
MAX_EVENTS = int(os.getenv("DIAGRAM_MAX_EVENTS", "80"))

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")

TOKENS = {
    "bg": "#F8FAFC",
    "card": "#FFFFFF",
    "text": "#0F172A",
    "muted": "#334155",
    "border_18": "#CBD5E1",
    "border_12": "#E2E8F0",
    "grid_08": "#EEF2F7",
    "primary": "#2563EB",
    "edge": "#94A3B8",
    "palette": ["#2563EB", "#10B981", "#F59E0B", "#EF4444", "#A855F7", "#06B6D4", "#F97316"],
    "font": "Inter, Segoe UI, Helvetica, Arial",
}

def _rid() -> str:
    return uuid.uuid4().hex[:10]

def _ts_ms() -> int:
    return int(time.time() * 1000)

def _truncate(s: str, n: int = 800) -> str:
    s = s or ""
    return s if len(s) <= n else (s[:n] + "…(truncated)")

def _log_step(rid: str, step: str, **kv: Any) -> None:
    parts = [f"rid={rid}", f"step={step}"]
    for k, v in kv.items():
        parts.append(f"{k}={v}")
    logger.info("[diagram] " + " ".join(parts))

def _log_debug(rid: str, step: str, **kv: Any) -> None:
    if logger.isEnabledFor(logging.DEBUG):
        parts = [f"rid={rid}", f"step={step}"]
        for k, v in kv.items():
            parts.append(f"{k}={v}")
        logger.debug("[diagram] " + " ".join(parts))

def _log_error(rid: str, step: str, exc: Exception) -> None:
    logger.error("[diagram] rid=%s step=%s error=%s", rid, step, str(exc))
    logger.error("[diagram] rid=%s traceback=\n%s", rid, traceback.format_exc())

async def _progress(rid: str, message: str, pct: int) -> None:
    _log_debug(rid, "progress", message=message, pct=pct)
    try:
        if inspect.iscoroutinefunction(update_job_status):
            await update_job_status(message, pct)
        else:
            update_job_status(message, pct)
    except Exception:
        _log_debug(rid, "progress_failed")

def _sanitize_filename(filename: Optional[str], default_base: str, ext: str) -> str:
    raw = filename or f"{default_base}-{uuid.uuid4().hex[:8]}.{ext}"
    cleaned = _SAFE_NAME_RE.sub("_", raw).strip("._")
    if not cleaned:
        cleaned = f"{default_base}-{uuid.uuid4().hex[:8]}.{ext}"
    if not cleaned.lower().endswith(f".{ext}"):
        cleaned = f"{cleaned}.{ext}"
    return cleaned

def _content_type(ext: str) -> str:
    ext = (ext or "").lower().strip(".")
    if ext == "svg":
        return "image/svg+xml"
    return "image/png"

def _get_public_base_url() -> Optional[str]:
    return os.getenv("PUBLIC_BASE_URL") or os.getenv("API_PUBLIC_URL") or os.getenv("BASE_URL")

def _store_image(rid: str, local_path: str, filename: str, size_bytes: int) -> Dict[str, Any]:
    ext = filename.rsplit(".", 1)[-1].lower()
    _log_step(rid, "store_start", use_s3=USE_S3, filename=filename, size_bytes=size_bytes, downloads_dir=DOWNLOADS_DIR)

    if USE_S3:
        if not DOWNLOADS_BUCKET:
            return {"status": "error", "error": "DOWNLOADS_BUCKET/S3_BUCKET not configured"}
        key = f"downloads/{uuid.uuid4().hex}/{filename}"
        s3 = boto3.client("s3", region_name=DEFAULT_REGION)
        try:
            _log_step(rid, "s3_upload_start", bucket=DOWNLOADS_BUCKET, key=key)
            s3.upload_file(local_path, DOWNLOADS_BUCKET, key, ExtraArgs={"ContentType": _content_type(ext)})
            url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": DOWNLOADS_BUCKET, "Key": key},
                ExpiresIn=URL_EXPIRES_SECONDS,
            )
            _log_step(rid, "s3_upload_ok", bucket=DOWNLOADS_BUCKET, key=key)
            return {
                "status": "ok",
                "storage": "s3",
                "bucket": DOWNLOADS_BUCKET,
                "key": key,
                "filename": filename,
                "size_bytes": size_bytes,
                "image_url": url,
                "download_url": url,
            }
        except ClientError as exc:
            _log_error(rid, "s3_upload_error", exc)
            return _error_response(rid, "runtime", str(exc))

    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    final_path = os.path.join(DOWNLOADS_DIR, filename)
    os.replace(local_path, final_path)

    public_base = _get_public_base_url()
    download_url = f"{public_base.rstrip('/')}/downloads/{filename}" if public_base else f"/downloads/{filename}"
    _log_step(rid, "store_ok", storage="local", file_path=final_path, download_url=download_url)
    return {
        "status": "ok",
        "storage": "local",
        "filename": filename,
        "size_bytes": size_bytes,
        "file_path": final_path,
        "image_url": download_url,
        "download_url": download_url,
    }

def _wrap_label(label: str, width: int = 22) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    return "\n".join(textwrap.wrap(text, width=width))

def _with_tmpfile(prefix: str, suffix: str) -> str:
    fd, tmp_path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    return tmp_path

def _require_fmt(image_format: Optional[str]) -> str:
    fmt = (image_format or "svg").strip().lower()
    if fmt not in {"png", "svg"}:
        raise ValueError("image_format must be png or svg")
    return fmt

def _assert_limit(count: int, limit: int, what: str) -> None:
    if count > limit:
        raise ValueError(f"too many {what} (max {limit})")

def _slug(s: str) -> str:
    s = str(s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or uuid.uuid4().hex[:8]

def _layout_normalize(layout: Optional[str]) -> str:
    raw = (layout or "horizontal").strip()
    upper = raw.upper()
    if upper in {"TB", "BT"}:
        return "vertical"
    if upper in {"LR", "RL"}:
        return "horizontal"
    low = raw.lower()
    if low in {"vertical", "v", "topdown", "top_down"}:
        return "vertical"
    return "horizontal"

def _coerce_list(v: Any, name: str, repairs: List[str]) -> List[Any]:
    if v is None:
        repairs.append(f"{name}:missing->[]")
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        repairs.append(f"{name}:dict->list")
        return [v]
    raise ValueError(f"{name} must be a list")

def _normalize_payload(rid: str, diagram_type: str, payload: Dict[str, Any], layout: Optional[str]) -> Tuple[Dict[str, Any], str, List[str]]:
    dtype = (diagram_type or "").strip().lower()
    p = payload if isinstance(payload, dict) else {}
    repairs: List[str] = []

    alias_map = {
        "relations": "relationships",
        "rels": "relationships",
        "tables": "entities",
        "actors": "participants",
        "calls": "messages",
        "milestones": "events",
    }
    for src, dst in alias_map.items():
        if src in p and dst not in p:
            p[dst] = p[src]
            repairs.append(f"alias:{src}->{dst}")

    layout_norm = _layout_normalize(layout)

    if dtype in {"flow", "decision_tree", "org_chart", "mind_map", "network_graph", "state_machine"}:
        p["nodes"] = _coerce_list(p.get("nodes"), "nodes", repairs)
        p["edges"] = _coerce_list(p.get("edges"), "edges", repairs)
    elif dtype == "sequence":
        p["participants"] = _coerce_list(p.get("participants"), "participants", repairs)
        p["messages"] = _coerce_list(p.get("messages"), "messages", repairs)
    elif dtype == "swimlane":
        p["lanes"] = _coerce_list(p.get("lanes"), "lanes", repairs)
        p["steps"] = _coerce_list(p.get("steps"), "steps", repairs)
    # elif dtype == "timeline":
    #     p["events"] = _coerce_list(p.get("events"), "events", repairs)
    #     p["edges"] = _coerce_list(p.get("edges"), "edges", repairs)
    elif dtype == "erd":
        p["entities"] = _coerce_list(p.get("entities"), "entities", repairs)
        p["relationships"] = _coerce_list(p.get("relationships"), "relationships", repairs)

    if dtype in {"flow", "decision_tree", "org_chart", "mind_map", "network_graph", "state_machine"}:
        for i, n in enumerate(p.get("nodes", [])):
            if not isinstance(n, dict):
                continue
            if not str(n.get("id") or "").strip():
                base = n.get("label") or n.get("name") or f"node_{i+1}"
                n["id"] = _slug(base)
                repairs.append(f"nodes[{i}].id:autofill")

    if dtype == "erd":
        for i, e in enumerate(p.get("entities", [])):
            if not isinstance(e, dict):
                continue
            if not str(e.get("id") or "").strip():
                base = e.get("name") or f"entity_{i+1}"
                e["id"] = _slug(base)
                repairs.append(f"entities[{i}].id:autofill")

    if dtype == "swimlane":
        for i, ln in enumerate(p.get("lanes", [])):
            if not isinstance(ln, dict):
                continue
            if not str(ln.get("id") or "").strip():
                base = ln.get("label") or f"lane_{i+1}"
                ln["id"] = _slug(base)
                repairs.append(f"lanes[{i}].id:autofill")
        for i, st in enumerate(p.get("steps", [])):
            if not isinstance(st, dict):
                continue
            if not str(st.get("id") or "").strip():
                base = st.get("label") or f"step_{i+1}"
                st["id"] = _slug(base)
                repairs.append(f"steps[{i}].id:autofill")

    # if dtype == "timeline":
    #     for i, ev in enumerate(p.get("events", [])):
    #         if not isinstance(ev, dict):
    #             continue
    #         if not str(ev.get("id") or "").strip():
    #             base = (ev.get("date") or "") + "_" + (ev.get("label") or ev.get("title") or f"event_{i+1}")
    #             ev["id"] = _slug(base)
    #             repairs.append(f"events[{i}].id:autofill")

    if dtype in {"flow", "decision_tree", "org_chart", "mind_map", "network_graph", "state_machine"}:
        nodes = p.get("nodes", [])
        by_id: Dict[str, Dict[str, Any]] = {}
        ordered: List[str] = []
        dup_count = 0
        for n in nodes:
            if not isinstance(n, dict):
                continue
            nid = str(n.get("id") or "").strip()
            if not nid:
                continue
            if nid not in by_id:
                by_id[nid] = n
                ordered.append(nid)
            else:
                dup_count += 1
                if not str(by_id[nid].get("label") or "").strip() and str(n.get("label") or "").strip():
                    by_id[nid]["label"] = n.get("label")
                repairs.append(f"dedupe:nodes:{nid}")
        if dup_count:
            p["nodes"] = [by_id[nid] for nid in ordered]
            repairs.append(f"dedupe:nodes:count={dup_count}")

    if dtype == "erd":
        ents = p.get("entities", [])
        by_id: Dict[str, Dict[str, Any]] = {}
        ordered: List[str] = []
        merged = 0

        def _norm_fields(v: Any) -> List[str]:
            if v is None:
                return []
            if isinstance(v, list):
                return [str(x) for x in v]
            if isinstance(v, str):
                return [v]
            return [str(v)]

        for e in ents:
            if not isinstance(e, dict):
                continue
            eid = str(e.get("id") or "").strip()
            if not eid:
                continue
            if eid not in by_id:
                by_id[eid] = e
                ordered.append(eid)
                continue
            merged += 1
            base = by_id[eid]
            if not str(base.get("name") or "").strip() and str(e.get("name") or "").strip():
                base["name"] = e.get("name")
            base_fields = _norm_fields(base.get("fields"))
            add_fields = _norm_fields(e.get("fields"))
            seen = set()
            out: List[str] = []
            for f in base_fields + add_fields:
                if f not in seen:
                    seen.add(f)
                    out.append(f)
            base["fields"] = out
            repairs.append(f"merge:entities:{eid}")
        if merged:
            p["entities"] = [by_id[eid] for eid in ordered]
            repairs.append(f"merge:entities:count={merged}")

    def _drop_edges(edges: List[Any], valid: set, kind: str) -> List[Dict[str, Any]]:
        kept: List[Dict[str, Any]] = []
        dropped = 0
        for e in edges:
            if not isinstance(e, dict):
                dropped += 1
                continue
            src = str(e.get("from") or "").strip()
            dst = str(e.get("to") or "").strip()
            if not src or not dst or src not in valid or dst not in valid:
                dropped += 1
                continue
            kept.append(e)
        if dropped:
            repairs.append(f"drop_invalid:{kind}:count={dropped}")
        return kept

    if dtype in {"flow", "decision_tree", "org_chart", "mind_map", "network_graph", "state_machine"}:
        node_ids = {str(n.get("id") or "").strip() for n in p.get("nodes", []) if isinstance(n, dict)}
        p["edges"] = _drop_edges(p.get("edges", []), node_ids, "edges")

    # if dtype == "timeline":
    #     ev_ids = {str(ev.get("id") or "").strip() for ev in p.get("events", []) if isinstance(ev, dict)}
    #     p["edges"] = _drop_edges(p.get("edges", []), ev_ids, "edges")

    if dtype == "erd":
        ent_ids = {str(e.get("id") or "").strip() for e in p.get("entities", []) if isinstance(e, dict)}
        rels = p.get("relationships", [])
        kept: List[Dict[str, Any]] = []
        dropped = 0
        for r in rels:
            if not isinstance(r, dict):
                dropped += 1
                continue
            src = str(r.get("from") or "").strip()
            dst = str(r.get("to") or "").strip()
            if not src or not dst or src not in ent_ids or dst not in ent_ids:
                dropped += 1
                continue
            kept.append(r)
        if dropped:
            repairs.append(f"drop_invalid:relationships:count={dropped}")
        p["relationships"] = kept

    if dtype == "sequence":
        parts = [str(pv) for pv in p.get("participants", [])]
        pset = set(parts)
        msgs = p.get("messages", [])
        kept: List[Dict[str, Any]] = []
        dropped = 0
        for m in msgs:
            if not isinstance(m, dict):
                dropped += 1
                continue
            src = str(m.get("from") or "").strip()
            dst = str(m.get("to") or "").strip()
            if not src or not dst or src not in pset or dst not in pset:
                dropped += 1
                continue
            kept.append(m)
        if dropped:
            repairs.append(f"drop_invalid:messages:count={dropped}")
        p["messages"] = kept

    if dtype == "swimlane":
        lane_ids = {str(ln.get("id") or "").strip() for ln in p.get("lanes", []) if isinstance(ln, dict)}
        kept: List[Dict[str, Any]] = []
        dropped = 0
        for st in p.get("steps", []):
            if not isinstance(st, dict):
                dropped += 1
                continue
            lid = str(st.get("lane_id") or "").strip()
            if lid not in lane_ids:
                dropped += 1
                continue
            kept.append(st)
        if dropped:
            repairs.append(f"drop_invalid:steps:count={dropped}")
        p["steps"] = kept

    _log_step(
        rid,
        "normalize_payload_ok",
        diagram_type=dtype,
        layout_in=layout,
        layout_norm=layout_norm,
        repairs=";".join(repairs) if repairs else "none",
        keys=",".join(sorted(list(p.keys())))[:240],
    )
    return p, layout_norm, repairs

def graphviz_premium(dot: Union[graphviz.Digraph, graphviz.Graph], title: Optional[str], rankdir: str) -> None:
    dot.attr(
        rankdir=rankdir,
        bgcolor=TOKENS["bg"],
        pad="0.35",
        nodesep="0.52",
        ranksep="0.85",
        splines="ortho",
        concentrate="true",
    )
    if title:
        dot.attr(label=title, labelloc="t", fontsize="18", fontname="Helvetica")

    dot.attr(
        "node",
        shape="box",
        style="rounded,filled",
        fontname="Helvetica",
        fontsize="11",
        fontcolor=TOKENS["text"],
        color=TOKENS["border_18"],
        fillcolor=TOKENS["card"],
        penwidth="1.55",
        margin="0.20,0.14",
    )
    dot.attr(
        "edge",
        fontname="Helvetica",
        fontsize="10",
        fontcolor=TOKENS["muted"],
        color=TOKENS["edge"],
        penwidth="1.0",
        arrowsize="0.7",
    )

def cluster_premium(subgraph: graphviz.Digraph, label: str) -> None:
    subgraph.attr(
        label=label,
        labelloc="t",
        fontsize="12",
        fontname="Helvetica",
        fontcolor=TOKENS["text"],
        style="rounded,filled",
        color=TOKENS["border_12"],
        fillcolor=TOKENS["bg"],
        penwidth="1.2",
    )

def _render_graphviz(rid: str, dot: Union[graphviz.Digraph, graphviz.Graph], fmt: str, tmp_path: str) -> None:
    _log_step(rid, "graphviz_render_start", fmt=fmt, tmp_path=tmp_path, engine=getattr(dot, "engine", None))
    data = dot.pipe(format=fmt)
    with open(tmp_path, "wb") as f:
        f.write(data)
    _log_step(rid, "graphviz_render_ok", bytes=len(data))

def _edge_ortho(dot: Union[graphviz.Digraph, graphviz.Graph], src: str, dst: str, label: str = "") -> None:
    label = str(label or "").strip()
    if label:
        dot.edge(src, dst, xlabel=label)
    else:
        dot.edge(src, dst)

VEGALITE_PREMIUM_CONFIG: Dict[str, Any] = {
    "background": TOKENS["bg"],
    "padding": 12,
    "config": {
        "font": TOKENS["font"],
        "title": {"anchor": "start", "fontSize": 20, "fontWeight": 600, "color": TOKENS["text"], "offset": 14},
        "axis": {
            "labelFontSize": 13,
            "titleFontSize": 14,
            "labelColor": TOKENS["muted"],
            "titleColor": TOKENS["muted"],
            "domainColor": TOKENS["border_18"],
            "tickColor": TOKENS["border_18"],
            "grid": False,
            "labelPadding": 8,
            "tickSize": 5,
            "labelAngle": 0,
            # optional:
            "labelLimit": 220,
            "labelOverlap": False,
        },
        "axisY": {"grid": True, "gridColor": TOKENS["grid_08"], "gridWidth": 1},
        "legend": {
            "orient": "top",
            "direction": "horizontal",
            "title": None,
            "labelFontSize": 13,
            "labelColor": TOKENS["muted"],
            "symbolType": "circle",
            "symbolSize": 120,
        },
        "range": {"category": TOKENS["palette"]},
        "view": {"stroke": TOKENS["border_12"], "strokeWidth": 1, "cornerRadius": 10},
        "mark": {"color": TOKENS["primary"], "stroke": TOKENS["border_12"], "strokeWidth": 1},
        "line": {"strokeWidth": 3},
        "point": {"filled": True, "size": 70},
        "bar": {"cornerRadiusTopLeft": 6, "cornerRadiusTopRight": 6},
        "area": {"opacity": 0.25},
        "header": {"labelFontSize": 13, "labelColor": TOKENS["text"], "labelFontWeight": 600},
    },
}

def _strip_styling(spec: Dict[str, Any]) -> None:
    for k in ["config", "background", "autosize", "padding"]:
        spec.pop(k, None)

def _apply_premium_theme(rid: str, spec: Dict[str, Any], title: Optional[str], width: int, height: int) -> Dict[str, Any]:
    _log_step(rid, "vega_theme_apply_start", width=width, height=height, has_title=bool(title))
    s = json.loads(json.dumps(spec))
    _strip_styling(s)
    if title:
        s["title"] = title
    if "facet" not in s and "repeat" not in s and "hconcat" not in s and "vconcat" not in s:
        s["width"] = int(width)
        s["height"] = int(height)
    for k, v in VEGALITE_PREMIUM_CONFIG.items():
        s[k] = v
    _log_step(rid, "vega_theme_apply_ok")
    return s

def _estimate_row_count(spec: Dict[str, Any]) -> int:
    data = spec.get("data")
    if isinstance(data, dict) and "values" in data and isinstance(data["values"], list):
        return len(data["values"])
    return 0

def _render_vegalite(rid: str, spec: Dict[str, Any], fmt: str) -> bytes:
    _log_step(rid, "vega_render_start", fmt=fmt)
    spec_str = json.dumps(spec, separators=(",", ":"), ensure_ascii=False)
    if fmt == "svg":
        out = vlc.vegalite_to_svg(spec_str).encode("utf-8")
    else:
        out = vlc.vegalite_to_png(spec_str)
    _log_step(rid, "vega_render_ok", bytes=len(out))
    return out

def _write_bytes(rid: str, tmp_path: str, data: bytes) -> None:
    _log_step(rid, "write_tmp_start", tmp_path=tmp_path, bytes=len(data))
    with open(tmp_path, "wb") as f:
        f.write(data)
    _log_step(rid, "write_tmp_ok", tmp_path=tmp_path)

async def _finalize_file(rid: str, tmp_path: str, filename: str, extra: Dict[str, Any]) -> Dict[str, Any]:
    size_bytes = os.path.getsize(tmp_path)
    _log_step(rid, "finalize_start", filename=filename, size_bytes=size_bytes)
    result = _store_image(rid, tmp_path, filename, size_bytes)
    if result.get("status") == "ok":
        result.update(extra)
        _log_step(rid, "finalize_ok", image_url=result.get("image_url"))
    else:
        _log_step(rid, "finalize_error", error=result.get("error"))
    return result

def _parse_nodes_edges(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    nodes = payload.get("nodes") or []
    edges = payload.get("edges") or []
    return [n for n in nodes if isinstance(n, dict)], [e for e in edges if isinstance(e, dict)]

def build_flow(rid: str, payload: Dict[str, Any], title: Optional[str], layout: str, fmt: str):
    nodes, edges = _parse_nodes_edges(payload)
    if not nodes:
        raise ValueError("nodes are required")
    _assert_limit(len(nodes), MAX_NODES, "nodes")
    _assert_limit(len(edges), MAX_EDGES, "edges")

    node_ids: List[str] = []
    labels: Dict[str, str] = {}
    for idx, n in enumerate(nodes):
        nid = str(n.get("id") or "").strip()
        if not nid:
            raise ValueError(f"nodes[{idx}].id required")
        node_ids.append(nid)
        labels[nid] = _wrap_label(str(n.get("label") or nid), width=22)

    rankdir = "LR" if (layout or "horizontal").strip().lower() == "horizontal" else "TB"
    dot = graphviz.Digraph("flow", format=fmt)
    graphviz_premium(dot, title, rankdir)
    for nid in node_ids:
        dot.node(nid, labels[nid])
    for e in edges:
        _edge_ortho(dot, str(e.get("from")).strip(), str(e.get("to")).strip(), str(e.get("label") or ""))
    return dot, {"diagram_type": "flow", "node_count": len(node_ids), "edge_count": len(edges), "title": title or ""}

def build_decision_tree(rid: str, payload: Dict[str, Any], title: Optional[str], _layout: str, fmt: str):
    nodes, edges = _parse_nodes_edges(payload)
    if not nodes:
        raise ValueError("nodes are required")
    _assert_limit(len(nodes), MAX_NODES, "nodes")
    _assert_limit(len(edges), MAX_EDGES, "edges")

    node_ids: List[str] = []
    labels: Dict[str, str] = {}
    for idx, n in enumerate(nodes):
        nid = str(n.get("id") or "").strip()
        if not nid:
            raise ValueError(f"nodes[{idx}].id required")
        node_ids.append(nid)
        labels[nid] = _wrap_label(str(n.get("label") or nid), width=22)

    dot = graphviz.Digraph("decision", format=fmt)
    graphviz_premium(dot, title, "TB")
    dot.attr(ranksep="0.75", nodesep="0.65")
    for nid in node_ids:
        dot.node(nid, labels[nid])
    for e in edges:
        _edge_ortho(dot, str(e.get("from")).strip(), str(e.get("to")).strip(), str(e.get("label") or ""))
    return dot, {"diagram_type": "decision_tree", "node_count": len(node_ids), "edge_count": len(edges), "title": title or ""}

def build_org_chart(rid: str, payload: Dict[str, Any], title: Optional[str], _layout: str, fmt: str):
    nodes, edges = _parse_nodes_edges(payload)
    if not nodes:
        raise ValueError("nodes are required")
    _assert_limit(len(nodes), MAX_NODES, "nodes")
    _assert_limit(len(edges), MAX_EDGES, "edges")

    node_ids: List[str] = []
    labels: Dict[str, str] = {}
    for idx, n in enumerate(nodes):
        nid = str(n.get("id") or "").strip()
        if not nid:
            raise ValueError(f"nodes[{idx}].id required")
        node_ids.append(nid)
        labels[nid] = _wrap_label(str(n.get("label") or nid), width=22)

    dot = graphviz.Digraph("org", format=fmt)
    graphviz_premium(dot, title, "TB")
    dot.attr(ranksep="0.85", nodesep="0.55")
    for nid in node_ids:
        dot.node(nid, labels[nid])
    for e in edges:
        _edge_ortho(dot, str(e.get("from")).strip(), str(e.get("to")).strip(), str(e.get("label") or ""))
    return dot, {"diagram_type": "org_chart", "node_count": len(node_ids), "edge_count": len(edges), "title": title or ""}

def build_network_graph(rid: str, payload: Dict[str, Any], title: Optional[str], _layout: str, fmt: str):
    nodes, edges = _parse_nodes_edges(payload)
    if not nodes:
        raise ValueError("nodes are required")
    _assert_limit(len(nodes), MAX_NODES, "nodes")
    _assert_limit(len(edges), MAX_EDGES, "edges")

    node_ids: List[str] = []
    labels: Dict[str, str] = {}
    for idx, n in enumerate(nodes):
        nid = str(n.get("id") or "").strip()
        if not nid:
            raise ValueError(f"nodes[{idx}].id required")
        node_ids.append(nid)
        labels[nid] = _wrap_label(str(n.get("label") or nid), width=22)

    directed = bool(payload.get("directed", False))
    engine = str(payload.get("engine") or "sfdp").strip().lower()
    if engine not in {"sfdp", "neato", "fdp"}:
        engine = "sfdp"
    dot = graphviz.Digraph("net", format=fmt, engine=engine) if directed else graphviz.Graph("net", format=fmt, engine=engine)
    graphviz_premium(dot, title, "LR")
    dot.attr(splines="spline", overlap="false")
    for nid in node_ids:
        dot.node(nid, labels[nid])
    for e in edges:
        _edge_ortho(dot, str(e.get("from")).strip(), str(e.get("to")).strip(), str(e.get("label") or ""))
    return dot, {"diagram_type": "network_graph", "node_count": len(node_ids), "edge_count": len(edges), "title": title or "", "engine": engine, "directed": directed}

def build_state_machine(rid: str, payload: Dict[str, Any], title: Optional[str], _layout: str, fmt: str):
    nodes, edges = _parse_nodes_edges(payload)
    if not nodes:
        raise ValueError("nodes are required")
    _assert_limit(len(nodes), MAX_NODES, "nodes")
    _assert_limit(len(edges), MAX_EDGES, "edges")

    node_ids: List[str] = []
    labels: Dict[str, str] = {}
    for idx, n in enumerate(nodes):
        nid = str(n.get("id") or "").strip()
        if not nid:
            raise ValueError(f"nodes[{idx}].id required")
        node_ids.append(nid)
        labels[nid] = _wrap_label(str(n.get("label") or nid), width=22)

    rankdir = str(payload.get("rankdir") or "LR").strip().upper()
    if rankdir not in {"LR", "TB"}:
        rankdir = "LR"
    dot = graphviz.Digraph("state", format=fmt)
    graphviz_premium(dot, title, rankdir)

    node_set = set(node_ids)
    start = str(payload.get("start") or "").strip()
    if start and start not in node_set:
        raise ValueError("start references unknown node")

    if start:
        dot.node("__start__", "", shape="circle", width="0.25", height="0.25", style="filled",
                 fillcolor="#DBEAFE", color=TOKENS["primary"])
        dot.edge("__start__", start)

    for nid in node_ids:
        dot.node(nid, labels[nid])
    for e in edges:
        _edge_ortho(dot, str(e.get("from")).strip(), str(e.get("to")).strip(), str(e.get("label") or ""))
    return dot, {"diagram_type": "state_machine", "node_count": len(node_ids), "edge_count": len(edges), "title": title or "", "start": start or None}

def build_mind_map(rid: str, payload: Dict[str, Any], title: Optional[str], _layout: str, fmt: str):
    nodes, edges = _parse_nodes_edges(payload)
    if not nodes:
        raise ValueError("nodes are required")
    _assert_limit(len(nodes), MAX_NODES, "nodes")
    _assert_limit(len(edges), MAX_EDGES, "edges")

    node_ids: List[str] = []
    labels: Dict[str, str] = {}
    for idx, n in enumerate(nodes):
        nid = str(n.get("id") or "").strip()
        if not nid:
            raise ValueError(f"nodes[{idx}].id required")
        node_ids.append(nid)
        labels[nid] = _wrap_label(str(n.get("label") or nid), width=22)

    center = str(payload.get("center") or payload.get("root") or (node_ids[0] if node_ids else "")).strip()
    if center not in set(node_ids):
        raise ValueError("center/root references unknown node")

    dot = graphviz.Graph("mind", format=fmt, engine="twopi")
    graphviz_premium(dot, title, "LR")
    dot.attr(root=center, overlap="false", splines="spline")
    for nid in node_ids:
        dot.node(nid, labels[nid])
    dot.node(center, labels[center], penwidth="1.8", color=TOKENS["primary"], fillcolor="#EEF2FF")
    for e in edges:
        _edge_ortho(dot, str(e.get("from")).strip(), str(e.get("to")).strip(), str(e.get("label") or ""))
    return dot, {"diagram_type": "mind_map", "node_count": len(node_ids), "edge_count": len(edges), "title": title or "", "center": center}

def build_sequence(rid: str, payload: Dict[str, Any], title: Optional[str], _layout: str, fmt: str):
    participants = [str(x) for x in (payload.get("participants") or [])]
    messages = [m for m in (payload.get("messages") or []) if isinstance(m, dict)]
    if len(participants) < 2:
        raise ValueError("participants must include at least 2 entries")
    _assert_limit(len(participants), MAX_PARTICIPANTS, "participants")
    _assert_limit(len(messages), MAX_MESSAGES, "messages")

    dot = graphviz.Digraph("sequence", format=fmt)
    graphviz_premium(dot, title, "LR")
    dot.attr(ranksep="0.85", nodesep="0.85")
    dot.attr("node", shape="plaintext", fontsize="12")
    for p in participants:
        dot.node(p, p)
    dot.attr("node", shape="box", style="rounded,filled", fillcolor="#EEF2FF", color=TOKENS["border_18"])

    for idx, m in enumerate(messages):
        _edge_ortho(dot, str(m.get("from")).strip(), str(m.get("to")).strip(), str(m.get("label") or f"step {idx+1}"))
    return dot, {"diagram_type": "sequence", "participant_count": len(participants), "message_count": len(messages), "title": title or ""}

def build_swimlane(rid: str, payload: Dict[str, Any], title: Optional[str], _layout: str, fmt: str):
    lanes = [ln for ln in (payload.get("lanes") or []) if isinstance(ln, dict)]
    steps = [st for st in (payload.get("steps") or []) if isinstance(st, dict)]
    if not lanes or not steps:
        raise ValueError("lanes and steps are required")
    _assert_limit(len(lanes), MAX_LANES, "lanes")
    _assert_limit(len(steps), MAX_STEPS, "steps")

    lane_ids: List[str] = []
    lane_labels: Dict[str, str] = {}
    for lane in lanes:
        lid = str((lane or {}).get("id") or "").strip()
        if not lid:
            raise ValueError("each lane must have id")
        if lid in lane_labels:
            raise ValueError(f"duplicate lane id: {lid}")
        lane_ids.append(lid)
        lane_labels[lid] = str((lane or {}).get("label") or lid)

    step_ids: List[str] = []
    step_lane: Dict[str, str] = {}
    step_label: Dict[str, str] = {}
    next_of: Dict[str, str] = {}
    for idx, s in enumerate(steps):
        sid = str((s or {}).get("id") or f"step-{idx+1}")
        step_ids.append(sid)
        step_lane[sid] = str((s or {}).get("lane_id") or "")
        step_label[sid] = _wrap_label(str((s or {}).get("label") or sid), width=22)
        nxt = str((s or {}).get("next_id") or "").strip()
        if nxt:
            next_of[sid] = nxt

    dot = graphviz.Digraph("swimlane", format=fmt)
    graphviz_premium(dot, title, "LR")
    dot.attr(ranksep="0.9", nodesep="0.65")

    for lid in lane_ids:
        with dot.subgraph(name=f"cluster_{lid}") as c:
            cluster_premium(c, lane_labels[lid])
            for sid in step_ids:
                if step_lane.get(sid) == lid:
                    c.node(sid, step_label[sid])

    step_set = set(step_ids)
    edge_count = 0
    for sid, nxt in next_of.items():
        if nxt in step_set:
            dot.edge(sid, nxt)
            edge_count += 1

    return dot, {"diagram_type": "swimlane", "lane_count": len(lanes), "step_count": len(steps), "edge_count": edge_count, "title": title or ""}


def build_erd(rid: str, payload: Dict[str, Any], title: Optional[str], _layout: str, fmt: str):
    entities = [e for e in (payload.get("entities") or []) if isinstance(e, dict)]
    relationships = [r for r in (payload.get("relationships") or []) if isinstance(r, dict)]
    if not entities:
        raise ValueError("entities are required")
    _assert_limit(len(entities), MAX_NODES, "entities")
    _assert_limit(len(relationships), MAX_EDGES, "relationships")

    entity_ids: List[str] = []
    entity_names: Dict[str, str] = {}
    entity_fields: Dict[str, List[str]] = {}

    for idx, e in enumerate(entities):
        eid = str((e or {}).get("id") or "").strip()
        if not eid:
            raise ValueError("entities require id")
        if eid in entity_names:
            raise ValueError(f"duplicate entity id: {eid}")
        entity_ids.append(eid)
        entity_names[eid] = str((e or {}).get("name") or eid)
        fields = (e or {}).get("fields") or []
        if not isinstance(fields, list):
            fields = [fields]
        entity_fields[eid] = [str(f) for f in fields]

    dot = graphviz.Digraph("erd", format=fmt)
    dot.attr(rankdir="LR", bgcolor=TOKENS["bg"], pad="0.25", nodesep="0.55", ranksep="0.85", splines="polyline")
    if title:
        dot.attr(label=title, labelloc="t", fontsize="18", fontname="Helvetica")

    dot.attr("node", shape="none", margin="0", fontname="Helvetica")
    dot.attr("edge", color=TOKENS["edge"], penwidth="1.1", arrowsize="0.7", fontname="Helvetica", fontsize="10")

    for eid in entity_ids:
        name = entity_names[eid]
        fields = entity_fields[eid]
        header = f'<TR><TD BGCOLOR="#E2E8F0" ALIGN="CENTER"><FONT COLOR="{TOKENS["text"]}"><B>{name}</B></FONT></TD></TR>'
        rows = []
        for f in fields or [""]:
            rows.append(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="10">{(f or "&nbsp;")}</FONT></TD></TR>')
        html = (
            '<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="6" '
            f'COLOR="{TOKENS["border_12"]}">'
            + header
            + "".join(rows)
            + "</TABLE>>"
        )
        dot.node(eid, label=html)

    for r in relationships:
        src = str((r or {}).get("from") or "").strip()
        dst = str((r or {}).get("to") or "").strip()
        label = str((r or {}).get("label") or "").strip()
        card = str((r or {}).get("cardinality") or "").strip()
        kwargs: Dict[str, Any] = {}
        if card and ":" in card:
            left, right = card.split(":", 1)
            kwargs.update(
                {
                    "taillabel": left.upper(),
                    "headlabel": right.upper(),
                    "labeldistance": "1.6",
                    "labelangle": "0",
                    "labelfloat": "true",
                }
            )
        if label:
            kwargs["label"] = label
        dot.edge(src, dst, **kwargs)

    return dot, {"diagram_type": "erd", "node_count": len(entities), "edge_count": len(relationships), "title": title or ""}

BUILDERS: Dict[str, Callable[[str, Dict[str, Any], Optional[str], str, str], Tuple[Any, Dict[str, Any]]]] = {
    "flow": build_flow,
    "sequence": build_sequence,
    "swimlane": build_swimlane,
    "decision_tree": build_decision_tree,
    "erd": build_erd,
    "org_chart": build_org_chart,
    "mind_map": build_mind_map,
    "network_graph": build_network_graph,
    "state_machine": build_state_machine,
#    "timeline": build_timeline,
}

def _error_response(
    rid: str,
    error_type: str,
    error: str,
    *,
    errors: Optional[List[Dict[str, str]]] = None,
    repairs: Optional[List[str]] = None,
    minimal_example: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Standard error schema for all tools."""
    rep = repairs or []
    err_list = errors or []
    _log_step(
        rid,
        "error_response",
        error_type=error_type,
        error=_truncate(str(error), 900),
        errors=_truncate(json.dumps(err_list, ensure_ascii=False), 900) if err_list else "[]",
        repairs=";".join(rep) if rep else "none",
    )
    out: Dict[str, Any] = {
        "status": "error",
        "error_type": error_type,
        "rid": rid,
        "error": str(error),
        "errors": err_list,
        "repairs_applied": rep,
    }
    if minimal_example is not None:
        out["minimal_example"] = minimal_example
    return out


def _validation_error(
    rid: str,
    errors: List[Dict[str, str]],
    repairs: List[str],
    minimal_example: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # Backwards-compatible wrapper for validation errors
    return _error_response(
        rid,
        "validation",
        errors[0]["message"] if errors else "validation error",
        errors=errors,
        repairs=repairs,
        minimal_example=minimal_example,
    )

@_tool("generate_diagram")
async def generate_diagram(
    diagram_type: str,
    payload: Dict[str, Any],
    title: Optional[str] = None,
    layout: Optional[str] = "horizontal",
    filename: Optional[str] = None,
    image_format: Optional[str] = "svg",
) -> Dict[str, Any]:
    rid = _rid()
    start_ms = _ts_ms()
    _log_step(rid, "tool_enter", tool="generate_diagram", diagram_type=diagram_type, image_format=image_format, layout=layout, has_title=bool(title))
    await _progress(rid, "Tool: Generate Diagram", 60)

    dtype = (diagram_type or "").strip().lower()
    if dtype not in BUILDERS:
        return _validation_error(rid, [{"path": "diagram_type", "message": f"must be one of: {', '.join(sorted(BUILDERS.keys()))}"}], repairs=[])

    tmp_path = None
    try:
        fmt = _require_fmt(image_format)
        safe_name = _sanitize_filename(filename, dtype, fmt)

        payload_norm, layout_norm, repairs = _normalize_payload(rid, dtype, payload or {}, layout)

        if dtype in {"flow", "decision_tree", "org_chart", "mind_map", "network_graph", "state_machine"} and not payload_norm.get("nodes"):
            return _validation_error(
                rid,
                [{"path": "payload.nodes", "message": "required (non-empty list)"}],
                repairs=repairs,
                minimal_example={"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}], "edges": [{"from": "a", "to": "b"}]},
            )
        if dtype == "sequence" and len(payload_norm.get("participants") or []) < 2:
            return _validation_error(
                rid,
                [{"path": "payload.participants", "message": "must include at least 2 entries"}],
                repairs=repairs,
                minimal_example={"participants": ["Client", "API"], "messages": [{"from": "Client", "to": "API", "label": "request"}]},
            )
        if dtype == "swimlane" and (not payload_norm.get("lanes") or not payload_norm.get("steps")):
            return _validation_error(
                rid,
                [{"path": "payload.lanes/steps", "message": "lanes and steps are required"}],
                repairs=repairs,
                minimal_example={
                    "lanes": [{"id": "user", "label": "User"}, {"id": "api", "label": "API"}],
                    "steps": [{"id": "s1", "label": "Login", "lane_id": "user", "next_id": "s2"}, {"id": "s2", "label": "Auth", "lane_id": "api"}],
                },
            )
        # if dtype == "timeline" and not payload_norm.get("events"):
        #     return _validation_error(
        #         rid,
        #         [{"path": "payload.events", "message": "events are required"}],
        #         repairs=repairs,
        #         minimal_example={"events": [{"id": "e1", "date": "2026-02-01", "label": "Kickoff"}, {"id": "e2", "date": "2026-02-10", "label": "Release"}]},
        #    )
        if dtype == "erd" and not payload_norm.get("entities"):
            return _validation_error(
                rid,
                [{"path": "payload.entities", "message": "entities are required"}],
                repairs=repairs,
                minimal_example={"entities": [{"id": "users", "name": "users", "fields": ["id", "email"]}], "relationships": []},
            )

        _log_step(rid, "tool_validated", dtype=dtype, fmt=fmt, filename=safe_name, layout_norm=layout_norm, repairs=";".join(repairs) if repairs else "none")
        tmp_path = _with_tmpfile(prefix=f"{dtype}-", suffix=f".{fmt}")
        _log_step(rid, "tmp_created", tmp_path=tmp_path)

        _log_step(rid, "builder_start", builder=dtype)
        dot_or_graph, meta = BUILDERS[dtype](rid, payload_norm, title, layout_norm, fmt)
        meta["repairs_applied"] = repairs
        _log_step(rid, "builder_ok", meta=_truncate(json.dumps(meta, ensure_ascii=False), 900))

        _render_graphviz(rid, dot_or_graph, fmt, tmp_path)
        result = await _finalize_file(rid, tmp_path, safe_name, meta)

        dur_ms = _ts_ms() - start_ms
        _log_step(rid, "tool_exit", status=result.get("status"), duration_ms=dur_ms, image_url=result.get("image_url"))
        return result

    except ValueError as exc:
        return _validation_error(rid, [{"path": "payload", "message": str(exc)}], repairs=[])
    except Exception as exc:
        _log_error(rid, "tool_error", exc)
        dur_ms = _ts_ms() - start_ms
        _log_step(rid, "tool_exit", status="error", duration_ms=dur_ms)
        return _error_response(rid, "runtime", str(exc))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
                _log_debug(rid, "tmp_removed", tmp_path=tmp_path)
            except OSError:
                _log_debug(rid, "tmp_remove_failed", tmp_path=tmp_path)


def _is_light_timeline_payload(raw: dict) -> bool:
    if not isinstance(raw, dict):
        return False
    if "$schema" in raw:
        return False

    events = raw.get("events")
    if events is None:
        events = raw.get("milestones")

    if not isinstance(events, list) or not events:
        return False

    t = str(raw.get("type") or "").strip().lower()
    return t in {"", "timeline"}


def _is_light_timeline_payload(raw: dict) -> bool:
    if not isinstance(raw, dict):
        return False
    if "$schema" in raw:
        return False

    events = raw.get("events")
    if events is None:
        events = raw.get("milestones")

    if not isinstance(events, list) or not events:
        return False

    t = str(raw.get("type") or "").strip().lower()
    return t in {"", "timeline"}




@_tool("generate_chart_vegalite_json")
async def generate_chart_vegalite_json(
    vegalite_json: str,
    title: Optional[str] = None,
    filename: Optional[str] = None,
    image_format: Optional[str] = "svg",
    width: int = 1000,
    height: int = 520,
) -> Dict[str, Any]:
    rid = _rid()
    start_ms = _ts_ms()
    _log_step(rid, "tool_enter", tool="generate_chart_vegalite_json", image_format=image_format, has_title=bool(title), width=width, height=height)
    await _progress(rid, "Tool: Generate Chart (Vega-Lite)", 58)

    tmp_path = None
    try:
        fmt = _require_fmt(image_format)
        safe_name = _sanitize_filename(filename, "chart", fmt)

        _log_step(rid, "spec_received", bytes=len(vegalite_json or ""), preview=_truncate(vegalite_json or "", 600))

        raw = json.loads(vegalite_json or "{}")
        # if isinstance(raw, dict) and _is_light_timeline_payload(raw):
        #     _log_step(rid, "spec_upgrade_detected", kind="timeline", events=len(raw.get("events") or []))
        #     raw = _build_vega_timeline_spec(raw["events"], width=width, height=height)
        #     _log_step(rid, "spec_upgrade_ok", kind="timeline")

        if not isinstance(raw, dict):
            return _validation_error(rid, [{"path": "vegalite_json", "message": "must decode to an object"}], repairs=[])

        row_count = _estimate_row_count(raw)
        _log_step(rid, "spec_parsed", row_count=row_count)
        if row_count and row_count > MAX_POINTS:
            return _validation_error(rid, [{"path": "data.values", "message": f"too many rows (max {MAX_POINTS})"}], repairs=[])

        spec = _apply_premium_theme(rid, raw, title=title, width=width, height=height)

        logger.info(f"[diagram spec] {spec}")

        tmp_path = _with_tmpfile(prefix="chart-", suffix=f".{fmt}")
        _log_step(rid, "tmp_created", tmp_path=tmp_path, filename=safe_name)

        img_bytes = _render_vegalite(rid, spec, fmt)
        _write_bytes(rid, tmp_path, img_bytes)

        result = await _finalize_file(
            rid,
            tmp_path,
            safe_name,
            {
                "chart_type": "vega_lite",
                "title": title or (raw.get("title") if isinstance(raw.get("title"), str) else "") or "",
                "format": fmt,
                "row_count": row_count or None,
            },
        )
        dur_ms = _ts_ms() - start_ms
        _log_step(rid, "tool_exit", status=result.get("status"), duration_ms=dur_ms, image_url=result.get("image_url"))
        return result

    except Exception as exc:
        _log_error(rid, "tool_error", exc)
        dur_ms = _ts_ms() - start_ms
        _log_step(rid, "tool_exit", status="error", duration_ms=dur_ms)
        return _error_response(rid, "runtime", str(exc))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
                _log_debug(rid, "tmp_removed", tmp_path=tmp_path)
            except OSError:
                _log_debug(rid, "tmp_remove_failed", tmp_path=tmp_path)

if __name__ == "__main__":
    try:
        mcp.run(transport="stdio")
    except TypeError:
        mcp.run()
