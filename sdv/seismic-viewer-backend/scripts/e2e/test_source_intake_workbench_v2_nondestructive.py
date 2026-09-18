#!/usr/bin/env python3
"""
E2E-2 — Source Intake Workbench V2 non-destructive contract harness.

This harness verifies the backend-owned Source Intake Workbench public contract:
  GET  /api/source-intake/workbench
  POST /api/source-intake/workbench/use-repository
  POST /api/source-intake/workbench/clear-selected

It mutates only the Workbench active set for one repository and restores it by
calling use-repository at the end. It does not upload, delete, convert, rebuild,
load, unload, or alter MSI / Managed Data / SEG-Y / Zarr / document artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


JsonDict = Dict[str, Any]


@dataclass
class Client:
    base_url: str
    timeout: int = 30

    def _url(self, path: str, query: Optional[Dict[str, Any]] = None) -> str:
        if not path.startswith('/'):
            path = '/' + path
        url = self.base_url.rstrip('/') + path
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            if clean:
                url += '?' + urllib.parse.urlencode(clean)
        return url

    def request(self, method: str, path: str, payload: Optional[JsonDict] = None, query: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, str], Any, bytes]:
        url = self._url(path, query)
        data: Optional[bytes] = None
        headers = {'Accept': 'application/json'}
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
                parsed = self._parse_body(resp.headers.get('content-type', ''), body)
                return resp.status, dict(resp.headers), parsed, body
        except urllib.error.HTTPError as exc:
            body = exc.read()
            parsed = self._parse_body(exc.headers.get('content-type', ''), body)
            return exc.code, dict(exc.headers), parsed, body

    @staticmethod
    def _parse_body(content_type: str, body: bytes) -> Any:
        if 'application/json' in (content_type or '').lower():
            try:
                return json.loads(body.decode('utf-8'))
            except Exception:
                return {'_parse_error': True, '_raw': body.decode('utf-8', errors='replace')}
        text = body.decode('utf-8', errors='replace')
        try:
            return json.loads(text)
        except Exception:
            return text


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def as_rows(payload: Any) -> List[JsonDict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ('rows', 'items', 'repositories', 'data', 'results'):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def row_id(row: JsonDict) -> Optional[str]:
    for key in ('candidate_id', 'segy_file_id', 'id', 'source_id'):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def repository_id(row: JsonDict) -> Optional[str]:
    for key in ('repository_id', 'id'):
        value = row.get(key)
        if isinstance(value, str) and value.startswith('repo_'):
            return value
    return None


def candidate_count(row: JsonDict) -> int:
    for key in ('candidate_count', 'segy_file_count', 'line_count', 'volume_candidate_count'):
        value = row.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def get_json(client: Client, path: str, query: Optional[Dict[str, Any]] = None) -> Any:
    status, headers, parsed, body = client.request('GET', path, query=query)
    require(status == 200, f'GET {path} expected 200, got {status}: {parsed!r}')
    return parsed


def post_json(client: Client, path: str, payload: JsonDict) -> Any:
    status, headers, parsed, body = client.request('POST', path, payload=payload)
    require(status == 200, f'POST {path} expected 200, got {status}: {parsed!r}')
    return parsed


def validate_workbench_payload(payload: Any, expected_mode: str, expected_repo: str, label: str) -> List[str]:
    require(isinstance(payload, dict), f'{label}: workbench payload must be dict')
    require(payload.get('schema_version') == 'source_intake.workbench.v2', f'{label}: wrong schema_version: {payload.get("schema_version")!r}')
    require(payload.get('mode') == expected_mode, f'{label}: wrong mode: {payload.get("mode")!r}')
    require(payload.get('repository_id') == expected_repo, f'{label}: wrong repository_id: {payload.get("repository_id")!r}')
    rows = payload.get('rows')
    require(isinstance(rows, list), f'{label}: rows must be list')
    row_count = payload.get('row_count')
    require(row_count == len(rows), f'{label}: row_count {row_count!r} != len(rows) {len(rows)}')
    summary = payload.get('summary')
    require(isinstance(summary, dict), f'{label}: summary must be dict')
    if 'total' in summary:
        require(summary.get('total') == len(rows), f'{label}: summary.total {summary.get("total")!r} != len(rows) {len(rows)}')
    ids = []
    for row in rows:
        require(isinstance(row, dict), f'{label}: every row must be dict')
        rid = row_id(row)
        require(bool(rid), f'{label}: row missing candidate id keys')
        ids.append(str(rid))
    require(len(ids) == len(set(ids)), f'{label}: duplicate candidate ids in rows')
    return ids


def choose_repository(client: Client, mode: str) -> str:
    repos_payload = get_json(client, '/api/source-intake/repositories', {'mode': mode})
    repos = as_rows(repos_payload)
    candidates: List[Tuple[int, str, JsonDict]] = []
    for row in repos:
        rid = repository_id(row)
        count = candidate_count(row)
        if rid and count > 0:
            candidates.append((count, rid, row))
    require(candidates, f'No {mode} source-intake repository with candidates found')
    candidates.sort(reverse=True, key=lambda x: x[0])
    return candidates[0][1]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--mode', default='3d', choices=['2d', '3d'])
    parser.add_argument('--repository-id', default='')
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    client = Client(args.base_url)
    summary: List[str] = []

    started = time.strftime('%Y-%m-%d %H:%M:%S')
    summary.append(f'E2E-2 Source Intake Workbench V2 non-destructive test')
    summary.append(f'Timestamp: {started}')
    summary.append(f'Base URL: {args.base_url}')
    summary.append(f'Mode: {args.mode}')

    health = get_json(client, '/api/msi/health')
    write_json(out_dir / 'msi_health.json', health)
    require(bool(health.get('ok')), 'MSI health returned ok != true')

    md_before = get_json(client, '/api/managed-data/query', {'limit': 500, 'offset': 0})
    loaded_before = get_json(client, '/api/managed-data/loaded')
    msi_before = get_json(client, '/api/msi/datasets')
    write_json(out_dir / 'managed_data_before.json', md_before)
    write_json(out_dir / 'loaded_before.json', loaded_before)
    write_json(out_dir / 'msi_datasets_before.json', msi_before)

    repo_id = args.repository_id or choose_repository(client, args.mode)
    summary.append(f'Repository: {repo_id}')

    use_payload = {'mode': args.mode, 'repository_id': repo_id}
    use_result = post_json(client, '/api/source-intake/workbench/use-repository', use_payload)
    write_json(out_dir / '01_use_repository.json', use_result)
    ids_after_use = validate_workbench_payload(use_result, args.mode, repo_id, 'use-repository')
    require(len(ids_after_use) > 0, 'use-repository returned zero rows')
    summary.append(f'Use in Workbench rows: {len(ids_after_use)}')

    refresh_1 = get_json(client, '/api/source-intake/workbench', {'mode': args.mode, 'repository_id': repo_id})
    write_json(out_dir / '02_refresh_after_use.json', refresh_1)
    ids_refresh_1 = validate_workbench_payload(refresh_1, args.mode, repo_id, 'refresh-after-use')
    require(ids_refresh_1 == ids_after_use, 'Refresh after use-repository changed active rows')
    summary.append('Refresh after use-repository preserves rows: PASS')

    one_id = ids_after_use[0]
    clear_one_payload = {'mode': args.mode, 'repository_id': repo_id, 'candidate_ids': [one_id]}
    clear_one = post_json(client, '/api/source-intake/workbench/clear-selected', clear_one_payload)
    write_json(out_dir / '03_clear_one.json', clear_one)
    ids_after_clear_one = validate_workbench_payload(clear_one, args.mode, repo_id, 'clear-one')
    require(one_id not in ids_after_clear_one, 'Cleared candidate still present after clear-one')
    require(len(ids_after_clear_one) == len(ids_after_use) - 1, 'Clear-one did not remove exactly one row')
    summary.append('Clear one selected row: PASS')

    refresh_2 = get_json(client, '/api/source-intake/workbench', {'mode': args.mode, 'repository_id': repo_id})
    write_json(out_dir / '04_refresh_after_clear_one.json', refresh_2)
    ids_refresh_2 = validate_workbench_payload(refresh_2, args.mode, repo_id, 'refresh-after-clear-one')
    require(ids_refresh_2 == ids_after_clear_one, 'Refresh resurrected or changed rows after clear-one')
    summary.append('Refresh after clear-one does not resurrect row: PASS')

    remaining_ids = list(ids_after_clear_one)
    clear_all_payload = {'mode': args.mode, 'repository_id': repo_id, 'candidate_ids': remaining_ids}
    clear_all = post_json(client, '/api/source-intake/workbench/clear-selected', clear_all_payload)
    write_json(out_dir / '05_clear_all_remaining.json', clear_all)
    ids_after_clear_all = validate_workbench_payload(clear_all, args.mode, repo_id, 'clear-all')
    require(len(ids_after_clear_all) == 0, 'Clear-all did not produce zero rows')
    summary.append('Clear all remaining rows: PASS')

    refresh_3 = get_json(client, '/api/source-intake/workbench', {'mode': args.mode, 'repository_id': repo_id})
    write_json(out_dir / '06_refresh_after_clear_all.json', refresh_3)
    ids_refresh_3 = validate_workbench_payload(refresh_3, args.mode, repo_id, 'refresh-after-clear-all')
    require(len(ids_refresh_3) == 0, 'Refresh after clear-all resurrected rows')
    summary.append('Refresh after clear-all remains empty: PASS')

    restore = post_json(client, '/api/source-intake/workbench/use-repository', use_payload)
    write_json(out_dir / '07_restore_use_repository.json', restore)
    ids_restore = validate_workbench_payload(restore, args.mode, repo_id, 'restore-use-repository')
    require(ids_restore == ids_after_use, 'Restore use-repository did not restore original active row set')
    summary.append('Use in Workbench restores repository rows: PASS')

    md_after = get_json(client, '/api/managed-data/query', {'limit': 500, 'offset': 0})
    loaded_after = get_json(client, '/api/managed-data/loaded')
    msi_after = get_json(client, '/api/msi/datasets')
    write_json(out_dir / 'managed_data_after.json', md_after)
    write_json(out_dir / 'loaded_after.json', loaded_after)
    write_json(out_dir / 'msi_datasets_after.json', msi_after)

    require(md_before == md_after, 'Managed Data changed during non-destructive workbench test')
    require(loaded_before == loaded_after, 'Loaded data changed during non-destructive workbench test')
    require(msi_before == msi_after, 'MSI datasets changed during non-destructive workbench test')
    summary.append('Managed Data unchanged: PASS')
    summary.append('Loaded data unchanged: PASS')
    summary.append('MSI datasets unchanged: PASS')

    summary.append('E2E-2 SOURCE INTAKE WORKBENCH V2 NON-DESTRUCTIVE: PASS')
    (out_dir / 'e2e_2_summary.txt').write_text('\n'.join(summary) + '\n', encoding='utf-8')
    print('\n'.join(summary))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'E2E-2 SOURCE INTAKE WORKBENCH V2 NON-DESTRUCTIVE: FAIL: {exc}', file=sys.stderr)
        raise
