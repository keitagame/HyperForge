
# HyperForge — Virtualization Platform Backend

Python製の仮想化管理バックエンドです。**標準ライブラリのみ**で動作し、pip不要です。

## 起動方法

```bash
python3 backend.py
```

ブラウザで http://localhost:8080 を開く。

## アーキテクチャ

```
browser ──HTTP GET /──────────────→ index.html (static)
        ──REST /api/*─────────────→ JSON API
        ──WebSocket ws://…/ws─────→ リアルタイム更新 (3秒毎)
```

## REST API エンドポイント

| Method | Path | 説明 |
|--------|------|------|
| GET | /api/vms | VM一覧 |
| GET | /api/vms/{id} | VM詳細 + メトリクス履歴 |
| POST | /api/vms | VM作成 |
| POST | /api/vms/{id}/action | VM操作 (start/stop/pause/reboot/snapshot/migrate) |
| DELETE | /api/vms/{id} | VM削除 |
| GET | /api/nodes | ノード一覧 |
| GET | /api/nodes/{id} | ノード詳細 |
| POST | /api/nodes/{id}/action | ノード操作 (maintenance/online) |
| GET | /api/storage | ストレージ一覧 |
| GET | /api/cluster/summary | クラスター概要 |
| GET | /api/metrics | 全VMメトリクス |
| GET | /api/events?limit=N | イベントログ |
| GET | /api/tasks | タスク一覧 |

## WebSocket メッセージ

**サーバー → クライアント:**
- `{"type": "init", "vms": ..., "nodes": ..., "events": ...}` — 接続時の初期データ
- `{"type": "metrics_update", "vms": ..., "nodes": ..., "latest_event": ...}` — 3秒毎の更新
- `{"type": "vm_update", "vm": ...}` — VM状態変化
- `{"type": "vm_deleted", "vm_id": ...}` — VM削除通知
- `{"type": "task_done", "task": ...}` — タスク完了

## コンソールコマンド (UI内)

```
top                  — 実行中VMのCPU/MEM
df -h                — ストレージ使用状況
free -h              — クラスターメモリ
ps aux | grep qemu   — QEMUプロセス一覧
vm start <id>        — VM起動
vm stop <id>         — VM停止
vm reboot <id>       — VM再起動
help                 — ヘルプ
```

## 依存関係

Python 3.8+ のみ。外部ライブラリ不要。

## ポート変更

`backend.py` の末尾の `PORT = 8080` を変更してください。
