#!/usr/bin/env python3
"""
HyperForge Virtualization Platform — Python Backend
Uses only Python standard library (no pip required).
Run: python3 backend.py
Access: http://localhost:8080
"""

import json
import math
import os
import random
import socket
import time
import threading
import uuid
import hashlib
import base64
import struct
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone

# ──────────────────────────────────────────────────────────────────────────────
# IN-MEMORY STATE
# ──────────────────────────────────────────────────────────────────────────────

NODES = {
    "hf-node-01": {
        "id": "hf-node-01", "status": "online", "cpu_cores": 32, "cpu_model": "AMD EPYC 7543",
        "mem_total": 131072, "mem_used": 68000, "disk_total": 2199023255552, "disk_used": 780000000000,
        "uptime": 4070700, "temp": 68, "load": [2.14, 1.98, 1.75], "ip": "10.0.0.1",
    },
    "hf-node-02": {
        "id": "hf-node-02", "status": "online", "cpu_cores": 32, "cpu_model": "AMD EPYC 7543",
        "mem_total": 131072, "mem_used": 95000, "disk_total": 2199023255552, "disk_used": 1200000000000,
        "uptime": 1987200, "temp": 72, "load": [4.21, 3.88, 3.50], "ip": "10.0.0.2",
    },
    "hf-node-03": {
        "id": "hf-node-03", "status": "online", "cpu_cores": 16, "cpu_model": "Intel Xeon E5-2680",
        "mem_total": 65536, "mem_used": 26000, "disk_total": 1099511627776, "disk_used": 380000000000,
        "uptime": 5270400, "temp": 61, "load": [0.88, 0.92, 0.95], "ip": "10.0.0.3",
    },
}

VMS = {
    100: {"id": 100, "name": "web-prod-01",  "status": "running", "node": "hf-node-01",
          "cpu": 12, "mem": 68, "disk": 34, "uptime_secs": 4070700, "ip": "10.0.1.20",
          "vcpus": 4, "mem_mb": 8192, "disk_gb": 80, "os": "Ubuntu 22.04", "type": "vm",
          "tags": ["production", "web"], "description": "Frontend web server cluster"},
    101: {"id": 101, "name": "db-master",    "status": "running", "node": "hf-node-01",
          "cpu": 48, "mem": 82, "disk": 61, "uptime_secs": 4070700, "ip": "10.0.1.21",
          "vcpus": 8, "mem_mb": 32768, "disk_gb": 500, "os": "Debian 12", "type": "vm",
          "tags": ["production", "database"], "description": "Primary PostgreSQL database"},
    102: {"id": 102, "name": "dev-sandbox",  "status": "stopped", "node": "hf-node-01",
          "cpu": 0,  "mem": 0,  "disk": 22, "uptime_secs": 0,       "ip": None,
          "vcpus": 2, "mem_mb": 4096, "disk_gb": 60, "os": "Fedora 39", "type": "vm",
          "tags": ["dev"], "description": "Developer sandbox environment"},
    103: {"id": 103, "name": "k8s-worker-01","status": "running", "node": "hf-node-02",
          "cpu": 71, "mem": 74, "disk": 55, "uptime_secs": 1987200, "ip": "10.0.1.30",
          "vcpus": 8, "mem_mb": 16384, "disk_gb": 200, "os": "Ubuntu 22.04", "type": "vm",
          "tags": ["k8s", "production"], "description": "Kubernetes worker node 1"},
    104: {"id": 104, "name": "k8s-worker-02","status": "running", "node": "hf-node-02",
          "cpu": 63, "mem": 70, "disk": 48, "uptime_secs": 1987200, "ip": "10.0.1.31",
          "vcpus": 8, "mem_mb": 16384, "disk_gb": 200, "os": "Ubuntu 22.04", "type": "vm",
          "tags": ["k8s", "production"], "description": "Kubernetes worker node 2"},
    105: {"id": 105, "name": "ci-runner",    "status": "paused",  "node": "hf-node-02",
          "cpu": 0,  "mem": 55, "disk": 30, "uptime_secs": 302820, "ip": "10.0.2.10",
          "vcpus": 4, "mem_mb": 8192, "disk_gb": 100, "os": "Ubuntu 22.04", "type": "ct",
          "tags": ["ci", "dev"], "description": "GitLab CI/CD runner"},
    106: {"id": 106, "name": "monitoring",   "status": "running", "node": "hf-node-03",
          "cpu": 18, "mem": 40, "disk": 44, "uptime_secs": 5270400, "ip": "10.0.1.50",
          "vcpus": 2, "mem_mb": 4096, "disk_gb": 150, "os": "Ubuntu 22.04", "type": "ct",
          "tags": ["infra", "monitoring"], "description": "Prometheus + Grafana stack"},
    107: {"id": 107, "name": "backup-agent", "status": "stopped", "node": "hf-node-03",
          "cpu": 0,  "mem": 0,  "disk": 8,  "uptime_secs": 0,       "ip": None,
          "vcpus": 1, "mem_mb": 1024, "disk_gb": 50, "os": "Debian 12", "type": "vm",
          "tags": ["infra", "backup"], "description": "Automated backup agent"},
}

STORAGE = {
    "local-lvm": {
        "id": "local-lvm", "type": "LVM-Thin", "total": 2250, "used": 1400,
        "nodes": ["hf-node-01", "hf-node-02"], "active": True, "shared": False,
    },
    "ceph-pool": {
        "id": "ceph-pool", "type": "Ceph RBD", "total": 8600, "used": 3175,
        "nodes": ["hf-node-01", "hf-node-02", "hf-node-03"], "active": True, "shared": True,
    },
    "nfs-backup": {
        "id": "nfs-backup", "type": "NFS", "total": 20000, "used": 8200,
        "nodes": ["hf-node-03"], "active": True, "shared": True,
    },
}

TASKS = []  # running/completed tasks

EVENTS = []  # audit log

METRIC_HISTORY = {vm_id: {
    "cpu": [max(5, min(95, vm["cpu"] + random.randint(-5, 5))) for _ in range(60)],
    "mem": [max(5, min(95, vm["mem"] + random.randint(-3, 3))) for _ in range(60)],
    "net_in":  [random.randint(10, 900) for _ in range(60)],
    "net_out": [random.randint(5,  400) for _ in range(60)],
} for vm_id, vm in VMS.items()}

NODE_METRIC_HISTORY = {nid: {
    "cpu":  [random.randint(20, 80) for _ in range(60)],
    "mem":  [random.randint(30, 90) for _ in range(60)],
    "load": [round(random.uniform(0.5, 5.0), 2) for _ in range(60)],
} for nid in NODES}

# ──────────────────────────────────────────────────────────────────────────────
# SIMULATION THREAD — updates metrics every 3 seconds
# ──────────────────────────────────────────────────────────────────────────────

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

def simulate():
    """Background thread that drifts VM/node metrics to simulate a live cluster."""
    LOG_MSGS = [
        ("info",  "ceph health check: HEALTH_OK"),
        ("info",  "VM 101 memory threshold OK"),
        ("warn",  "hf-node-02 load average: {load:.2f}"),
        ("info",  "VM 103 network: {net} Mb/s in"),
        ("info",  "vzdump VM 103: {pct}% complete"),
        ("err",   "Storage latency spike: ceph-pool"),
        ("info",  "VM 104 snapshot created"),
        ("warn",  "hf-node-01 temperature: {temp}°C"),
    ]
    pct = 0
    while True:
        time.sleep(3)
        try:
            # drift VM metrics
            for vm_id, vm in VMS.items():
                if vm["status"] == "running":
                    vm["cpu"] = _clamp(vm["cpu"] + random.randint(-6, 6), 3, 97)
                    vm["mem"] = _clamp(vm["mem"] + random.randint(-2, 2), 5, 98)
                    METRIC_HISTORY[vm_id]["cpu"].append(vm["cpu"])
                    METRIC_HISTORY[vm_id]["cpu"] = METRIC_HISTORY[vm_id]["cpu"][-60:]
                    METRIC_HISTORY[vm_id]["mem"].append(vm["mem"])
                    METRIC_HISTORY[vm_id]["mem"] = METRIC_HISTORY[vm_id]["mem"][-60:]
                    ni = _clamp(random.randint(10, 950), 0, 1000)
                    no = _clamp(random.randint(5, 450), 0, 1000)
                    METRIC_HISTORY[vm_id]["net_in"].append(ni)
                    METRIC_HISTORY[vm_id]["net_in"] = METRIC_HISTORY[vm_id]["net_in"][-60:]
                    METRIC_HISTORY[vm_id]["net_out"].append(no)
                    METRIC_HISTORY[vm_id]["net_out"] = METRIC_HISTORY[vm_id]["net_out"][-60:]

            # drift node metrics
            for nid, node in NODES.items():
                if node["status"] == "online":
                    node["temp"] = _clamp(node["temp"] + random.randint(-1, 1), 40, 95)
                    node["load"][0] = round(_clamp(node["load"][0] + random.uniform(-0.3, 0.3), 0.1, 16.0), 2)
                    cpu_pct = _clamp(int(node["load"][0] / node["cpu_cores"] * 100), 1, 99)
                    NODE_METRIC_HISTORY[nid]["cpu"].append(cpu_pct)
                    NODE_METRIC_HISTORY[nid]["cpu"] = NODE_METRIC_HISTORY[nid]["cpu"][-60:]

            # push a log event
            pct = (pct + 7) % 100
            tpl = random.choice(LOG_MSGS)
            msg = tpl[1].format(
                load=NODES["hf-node-02"]["load"][0],
                net=random.randint(100, 900),
                pct=pct,
                temp=NODES["hf-node-01"]["temp"],
            )
            EVENTS.append({"ts": time.time(), "level": tpl[0], "msg": msg})
            if len(EVENTS) > 200:
                EVENTS.pop(0)

            # broadcast to WebSocket clients
            payload = json.dumps({"type": "metrics_update", "vms": {
                str(k): {"cpu": v["cpu"], "mem": v["mem"]} for k, v in VMS.items()
            }, "nodes": {
                nid: {"temp": nd["temp"], "load": nd["load"][0]} for nid, nd in NODES.items()
            }, "latest_event": EVENTS[-1] if EVENTS else None})
            WS_MANAGER.broadcast(payload)
        except Exception as e:
            print(f"[sim error] {e}")


# ──────────────────────────────────────────────────────────────────────────────
# WEBSOCKET MANAGER (RFC 6455, stdlib only)
# ──────────────────────────────────────────────────────────────────────────────

class WSClient:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr

    def send(self, text: str):
        try:
            data = text.encode("utf-8")
            header = bytearray()
            header.append(0x81)  # FIN + text opcode
            if len(data) < 126:
                header.append(len(data))
            elif len(data) < 65536:
                header.append(126)
                header += struct.pack(">H", len(data))
            else:
                header.append(127)
                header += struct.pack(">Q", len(data))
            self.conn.sendall(bytes(header) + data)
        except Exception:
            WSManager._clients.discard(self)


class WSManager:
    _clients: set = set()

    def add(self, client):
        self._clients.add(client)

    def remove(self, client):
        self._clients.discard(client)

    def broadcast(self, text: str):
        dead = set()
        for c in list(self._clients):
            try:
                c.send(text)
            except Exception:
                dead.add(c)
        self._clients -= dead


WS_MANAGER = WSManager()


def _ws_handshake(request_line, headers_raw) -> bytes:
    """Parse HTTP headers and return the 101 upgrade response."""
    headers = {}
    for line in headers_raw.split("\r\n"):
        if ": " in line:
            k, v = line.split(": ", 1)
            headers[k.lower()] = v
    key = headers.get("sec-websocket-key", "")
    accept = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
    ).decode()
    return (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
    ).encode()


def _ws_recv_frame(conn) -> str | None:
    """Read one WebSocket frame and return decoded text (or None on error)."""
    try:
        raw = conn.recv(2)
        if len(raw) < 2:
            return None
        b1, b2 = raw[0], raw[1]
        masked = bool(b2 & 0x80)
        plen = b2 & 0x7F
        if plen == 126:
            plen = struct.unpack(">H", conn.recv(2))[0]
        elif plen == 127:
            plen = struct.unpack(">Q", conn.recv(8))[0]
        mask = conn.recv(4) if masked else b""
        payload = conn.recv(plen)
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        opcode = b1 & 0x0F
        if opcode == 8:  # close
            return None
        return payload.decode("utf-8", errors="ignore")
    except Exception:
        return None


def handle_ws_connection(conn, addr, path):
    client = WSClient(conn, addr)
    WS_MANAGER.add(client)
    # send initial state
    client.send(json.dumps({
        "type": "init",
        "vms": {str(k): v for k, v in VMS.items()},
        "nodes": NODES,
        "events": EVENTS[-20:],
    }))
    conn.settimeout(60)
    while True:
        msg = _ws_recv_frame(conn)
        if msg is None:
            break
        # handle client→server messages (e.g. ping)
    WS_MANAGER.remove(client)
    try:
        conn.close()
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# REST API HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def make_task(action, target, status="running"):
    task = {
        "id": str(uuid.uuid4())[:8],
        "action": action,
        "target": target,
        "status": status,
        "started": time.time(),
        "finished": None,
    }
    TASKS.append(task)

    def complete():
        time.sleep(random.uniform(1.5, 3.5))
        task["status"] = "ok"
        task["finished"] = time.time()
        EVENTS.append({"ts": time.time(), "level": "info",
                        "msg": f"Task {task['action']} {task['target']} completed"})
        WS_MANAGER.broadcast(json.dumps({"type": "task_done", "task": task}))

    threading.Thread(target=complete, daemon=True).start()
    return task


def fmt_uptime(secs):
    d = secs // 86400
    h = (secs % 86400) // 3600
    return f"{d}d {h}h" if d else f"{h}h"


# ──────────────────────────────────────────────────────────────────────────────
# HTTP REQUEST HANDLER
# ──────────────────────────────────────────────────────────────────────────────

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))


class HyperForgeHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  [{self.address_string()}] {fmt % args}")

    # ── WebSocket upgrade (must happen before HTTP routing) ──────────────────
    def handle_websocket_upgrade(self):
        raw = self.raw_requestline.decode()
        # collect all request bytes seen so far
        # headers_raw was already read by BaseHTTPRequestHandler
        header_block = ""
        for k, v in self.headers.items():
            header_block += f"{k}: {v}\r\n"
        resp = _ws_handshake(raw, header_block)
        self.connection.sendall(resp)
        threading.Thread(
            target=handle_ws_connection,
            args=(self.connection, self.client_address, self.path),
            daemon=True,
        ).start()
        # keep this handler thread alive until WS thread takes over
        # (BaseHTTPRequestHandler will close connection otherwise)
        # We return to let the caller return immediately; WS thread owns the conn

    # ── Routing ─────────────────────────────────────────────────────────────
    def do_GET(self):
        # WebSocket upgrade
        if (self.headers.get("Upgrade", "").lower() == "websocket" and
                self.path.startswith("/ws")):
            self.handle_websocket_upgrade()
            return

        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/") or "/"
        qs     = parse_qs(parsed.query)

        # Static files
        if path == "/" or path == "/index.html":
            self.serve_file("index.html", "text/html")
            return

        # ── API ──────────────────────────────────────────────────────────────
        if path.startswith("/api/"):
            self.handle_api_get(path, qs)
            return

        self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")
        self.handle_api_post(path, body)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")
        self.handle_api_delete(path)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    # ── CORS ─────────────────────────────────────────────────────────────────
    def send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    # ── JSON response ────────────────────────────────────────────────────────
    def json_resp(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_cors()
        self.end_headers()
        self.wfile.write(body)

    # ── Static file ──────────────────────────────────────────────────────────
    def serve_file(self, filename, mime):
        fpath = os.path.join(STATIC_DIR, filename)
        if not os.path.exists(fpath):
            self.send_error(404)
            return
        with open(fpath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", len(data))
        self.send_cors()
        self.end_headers()
        self.wfile.write(data)

    # ── GET API routes ───────────────────────────────────────────────────────
    def handle_api_get(self, path, qs):
        # GET /api/vms
        if path == "/api/vms":
            vms_out = []
            for v in VMS.values():
                out = dict(v)
                out["uptime"] = fmt_uptime(v["uptime_secs"]) if v["uptime_secs"] else "—"
                out["ip_display"] = v["ip"] or "—"
                vms_out.append(out)
            self.json_resp({"vms": vms_out, "count": len(vms_out)})
            return

        # GET /api/vms/{id}
        if path.startswith("/api/vms/"):
            parts = path.split("/")
            try:
                vm_id = int(parts[3])
            except (IndexError, ValueError):
                self.json_resp({"error": "invalid id"}, 400); return
            vm = VMS.get(vm_id)
            if not vm:
                self.json_resp({"error": "not found"}, 404); return
            out = dict(vm)
            out["uptime"] = fmt_uptime(vm["uptime_secs"]) if vm["uptime_secs"] else "—"
            # include metric history
            hist = METRIC_HISTORY.get(vm_id, {})
            out["history"] = hist
            self.json_resp(out)
            return

        # GET /api/nodes
        if path == "/api/nodes":
            self.json_resp({"nodes": list(NODES.values())})
            return

        # GET /api/nodes/{id}
        if path.startswith("/api/nodes/"):
            nid = path.split("/")[3]
            node = NODES.get(nid)
            if not node:
                self.json_resp({"error": "not found"}, 404); return
            out = dict(node)
            out["history"] = NODE_METRIC_HISTORY.get(nid, {})
            # include VMs on this node
            out["vms"] = [v["id"] for v in VMS.values() if v["node"] == nid]
            self.json_resp(out)
            return

        # GET /api/storage
        if path == "/api/storage":
            self.json_resp({"storage": list(STORAGE.values())})
            return

        # GET /api/cluster/summary
        if path == "/api/cluster/summary":
            running = sum(1 for v in VMS.values() if v["status"] == "running")
            stopped = sum(1 for v in VMS.values() if v["status"] == "stopped")
            paused  = sum(1 for v in VMS.values() if v["status"] == "paused")
            total_mem = sum(n["mem_total"] for n in NODES.values())
            used_mem  = sum(n["mem_used"]  for n in NODES.values())
            self.json_resp({
                "nodes": {"total": len(NODES), "online": sum(1 for n in NODES.values() if n["status"] == "online")},
                "vms": {"total": len(VMS), "running": running, "stopped": stopped, "paused": paused},
                "memory": {"total_mb": total_mem, "used_mb": used_mem, "pct": round(used_mem / total_mem * 100, 1)},
                "storage": {s["id"]: {"used_pct": round(s["used"] / s["total"] * 100, 1)} for s in STORAGE.values()},
            })
            return

        # GET /api/tasks
        if path == "/api/tasks":
            self.json_resp({"tasks": TASKS[-50:]})
            return

        # GET /api/events
        if path == "/api/events":
            limit = int(qs.get("limit", ["50"])[0])
            self.json_resp({"events": EVENTS[-limit:]})
            return

        # GET /api/metrics  — returns current snapshot of all VM metrics
        if path == "/api/metrics":
            snap = {}
            for vm_id, vm in VMS.items():
                snap[vm_id] = {
                    "cpu": vm["cpu"], "mem": vm["mem"], "disk": vm["disk"],
                    "status": vm["status"],
                    "history": METRIC_HISTORY.get(vm_id, {}),
                }
            self.json_resp({"metrics": snap, "ts": time.time()})
            return

        self.json_resp({"error": "unknown endpoint"}, 404)

    # ── POST API routes ──────────────────────────────────────────────────────
    def handle_api_post(self, path, body):
        # POST /api/vms  — create VM
        if path == "/api/vms":
            new_id = max(VMS.keys()) + 1 if VMS else 100
            node   = body.get("node", "hf-node-01")
            vm = {
                "id": new_id,
                "name":    body.get("name", f"vm-{new_id}"),
                "status":  "stopped",
                "node":    node,
                "cpu": 0, "mem": 0, "disk": 5,
                "uptime_secs": 0, "ip": None,
                "vcpus":   int(body.get("vcpus", 2)),
                "mem_mb":  int(body.get("mem_mb", 2048)),
                "disk_gb": int(body.get("disk_gb", 32)),
                "os":      body.get("os", "Ubuntu 22.04"),
                "type":    body.get("type", "vm"),
                "tags":    body.get("tags", []),
                "description": body.get("description", ""),
            }
            VMS[new_id] = vm
            METRIC_HISTORY[new_id] = {"cpu": [0]*60, "mem": [0]*60, "net_in": [0]*60, "net_out": [0]*60}
            EVENTS.append({"ts": time.time(), "level": "info", "msg": f"VM {new_id} ({vm['name']}) created"})
            task = make_task("create", f"VM {new_id}")
            self.json_resp({"vm": vm, "task": task}, 201)
            return

        # POST /api/vms/{id}/action
        if "/action" in path:
            parts = path.split("/")
            try:
                vm_id = int(parts[3])
            except (IndexError, ValueError):
                self.json_resp({"error": "invalid id"}, 400); return
            vm = VMS.get(vm_id)
            if not vm:
                self.json_resp({"error": "not found"}, 404); return

            action = body.get("action", "")
            if action == "start" and vm["status"] in ("stopped", "paused"):
                vm["status"] = "running"
                vm["uptime_secs"] = 0
                vm["cpu"] = random.randint(5, 20)
                vm["mem"] = random.randint(20, 50)
                import ipaddress
                vm["ip"] = f"10.0.{random.randint(1,3)}.{random.randint(10,200)}"
                EVENTS.append({"ts": time.time(), "level": "info", "msg": f"VM {vm_id} started"})
            elif action == "stop" and vm["status"] == "running":
                vm["status"] = "stopped"
                vm["cpu"] = 0; vm["mem"] = 0; vm["uptime_secs"] = 0; vm["ip"] = None
                EVENTS.append({"ts": time.time(), "level": "info", "msg": f"VM {vm_id} stopped"})
            elif action == "pause" and vm["status"] == "running":
                vm["status"] = "paused"
                vm["cpu"] = 0
                EVENTS.append({"ts": time.time(), "level": "info", "msg": f"VM {vm_id} paused"})
            elif action == "reboot" and vm["status"] == "running":
                vm["uptime_secs"] = 0
                EVENTS.append({"ts": time.time(), "level": "info", "msg": f"VM {vm_id} rebooted"})
            elif action == "snapshot":
                EVENTS.append({"ts": time.time(), "level": "info", "msg": f"VM {vm_id} snapshot taken"})
            elif action == "migrate":
                target_node = body.get("target_node")
                if target_node and target_node in NODES:
                    vm["node"] = target_node
                    EVENTS.append({"ts": time.time(), "level": "info",
                                   "msg": f"VM {vm_id} migrated to {target_node}"})
                else:
                    self.json_resp({"error": "invalid target node"}, 400); return
            else:
                self.json_resp({"error": f"action '{action}' not valid for status '{vm['status']}'"}, 422)
                return

            task = make_task(action, f"VM {vm_id}")
            WS_MANAGER.broadcast(json.dumps({"type": "vm_update", "vm": vm}))
            self.json_resp({"ok": True, "vm": vm, "task": task})
            return

        # POST /api/nodes/{id}/action
        if "/api/nodes/" in path and "/action" in path:
            nid = path.split("/")[3]
            node = NODES.get(nid)
            if not node:
                self.json_resp({"error": "not found"}, 404); return
            action = body.get("action", "")
            if action == "maintenance":
                node["status"] = "maintenance"
            elif action == "online":
                node["status"] = "online"
            else:
                self.json_resp({"error": "unknown action"}, 422); return
            EVENTS.append({"ts": time.time(), "level": "warn",
                           "msg": f"Node {nid} set to {node['status']}"})
            task = make_task(action, nid)
            self.json_resp({"ok": True, "node": node, "task": task})
            return

        self.json_resp({"error": "unknown endpoint"}, 404)

    # ── DELETE API routes ────────────────────────────────────────────────────
    def handle_api_delete(self, path):
        # DELETE /api/vms/{id}
        if path.startswith("/api/vms/"):
            try:
                vm_id = int(path.split("/")[3])
            except (IndexError, ValueError):
                self.json_resp({"error": "invalid id"}, 400); return
            vm = VMS.pop(vm_id, None)
            if not vm:
                self.json_resp({"error": "not found"}, 404); return
            METRIC_HISTORY.pop(vm_id, None)
            EVENTS.append({"ts": time.time(), "level": "warn",
                           "msg": f"VM {vm_id} ({vm['name']}) deleted"})
            task = make_task("delete", f"VM {vm_id}", status="ok")
            WS_MANAGER.broadcast(json.dumps({"type": "vm_deleted", "vm_id": vm_id}))
            self.json_resp({"ok": True, "deleted": vm_id, "task": task})
            return

        self.json_resp({"error": "unknown endpoint"}, 404)


# ──────────────────────────────────────────────────────────────────────────────
# THREADED HTTP SERVER with WebSocket support
# ──────────────────────────────────────────────────────────────────────────────

class ThreadedHTTPServer(HTTPServer):
    """Handles each request in a new thread."""
    def process_request(self, request, client_address):
        t = threading.Thread(
            target=self._process_request_thread,
            args=(request, client_address),
            daemon=True,
        )
        t.start()

    def _process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception as e:
            print(f"[request error] {e}")
        finally:
            self.shutdown_request(request)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

HOST, PORT = "0.0.0.0", 8080

if __name__ == "__main__":
    # Start simulation thread
    sim_thread = threading.Thread(target=simulate, daemon=True)
    sim_thread.start()

    # Seed initial events
    EVENTS.extend([
        {"ts": time.time() - 300, "level": "info",  "msg": "HyperForge cluster initialized — 3 nodes online"},
        {"ts": time.time() - 240, "level": "info",  "msg": "ceph health check: HEALTH_OK"},
        {"ts": time.time() - 180, "level": "warn",  "msg": "hf-node-02 load average: 4.21"},
        {"ts": time.time() - 120, "level": "info",  "msg": "VM 103 network: 820 Mb/s in"},
        {"ts": time.time() - 60,  "level": "err",   "msg": "Storage latency spike: ceph-pool"},
        {"ts": time.time() - 30,  "level": "info",  "msg": "VM 104 snapshot created"},
    ])

    server = ThreadedHTTPServer((HOST, PORT), HyperForgeHandler)
    print(f"""
╔══════════════════════════════════════════╗
║      HyperForge Backend  v1.0.0          ║
╠══════════════════════════════════════════╣
║  HTTP  →  http://localhost:{PORT}         ║
║  WS    →  ws://localhost:{PORT}/ws        ║
║  API   →  http://localhost:{PORT}/api/    ║
╠══════════════════════════════════════════╣
║  Nodes:  3   VMs: {len(VMS)}   CT: 2           ║
╚══════════════════════════════════════════╝
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[shutdown] HyperForge stopped.")
