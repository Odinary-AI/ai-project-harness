#!/usr/bin/env python3
"""AI工程机制: explicit, project-local lifecycle and evidence. Python 3.10+."""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid
import fcntl

VERSION = '0.5.0-dev.1'
PACKAGE = Path(__file__).resolve().parents[1]
DEFAULTS = {'entrypoint': 'README.md', 'agent_policy': 'AGENTS.md',
            'requirements': 'docs/requirements.md', 'validation': 'TESTING.md',
            'status': 'docs/status.md'}
BLOCK = re.compile(r'```harness-task\n(.*?)\n```', re.S)
START, END = '<!-- harness:status:start -->', '<!-- harness:status:end -->'

class HarnessError(Exception):
    pass

def require(condition, message):
    if not condition:
        raise HarnessError(message)

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()

def load(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise HarnessError(f'无法读取 JSON {path}: {exc}') from exc

def safe(root, relative):
    root = root.resolve()
    require(isinstance(relative, str) and bool(relative.strip()), '路径必须是非空相对路径')
    p = Path(relative)
    require(not p.is_absolute() and '..' not in p.parts, f'路径超出项目: {relative}')
    target = root / p
    require(target.resolve().is_relative_to(root), f'符号链接超出项目: {relative}')
    return target

def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def write_json(path, obj):
    atomic(path, json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

@contextlib.contextmanager
def lock(root):
    p = safe(root, '.harness/lock')
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield

def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,80}', value), 'ID 只允许字母、数字、横线及下划线')
    return value

def nonempty(value, label):
    require(isinstance(value, str) and bool(value.strip()) and '[待填写]' not in value, f'{label}缺少真实内容')

def task_check_ids(t):
    require(isinstance(t, dict), '任务规格必须是 JSON 对象')
    acs = t.get('acceptance')
    require(isinstance(acs, list) and acs, '必须有验收标准')
    ids = set()
    for ac in acs:
        require(isinstance(ac, dict) and isinstance(ac.get('checks'), list), '验收检查须为数组')
        ids.update(identifier(cid) for cid in ac['checks'])
    return ids

def config(root, check_ids=None):
    return validate_config(root, load(safe(root, '.harness/project.json')), check_ids)

def validate_config(root, c, check_ids=None):
    require(isinstance(c, dict), '项目配置必须是 JSON 对象')
    require(c.get('schema_version') == 1, '不支持的配置版本；先按升级流程比较差异')
    require(isinstance(c.get('authorities'), dict), '缺少职责映射')
    for key in DEFAULTS:
        require(key in c['authorities'], f'缺少职责: {key}')
        safe(root, c['authorities'][key])
    status = safe(root, c['authorities']['status']).resolve()
    for role in ('requirements', 'validation', 'agent_policy'):
        policy = safe(root, c['authorities'][role]).resolve()
        existing = status.exists() and policy.exists()
        require(status != policy and not (existing and status.samefile(policy)),
                f'status 与 {role} 不能映射同一文件；状态写回会使规则证据失效，请映射独立状态文件')
        require(existing or str(status).casefold() != str(policy).casefold(),
                f'status 与 {role} 的未建立路径仅大小写不同，无法确认独立；先建立并核对实际文件后再映射')
    require(isinstance(c.get('checks'), dict), 'checks 必须为对象')
    for cid in c['checks'] if check_ids is None else sorted(check_ids):
        require(cid in c['checks'], f'验收标准引用未知检查: {cid}')
        check = c['checks'][cid]
        identifier(cid)
        require(isinstance(check, dict), f'{cid}: 检查配置应为对象')
        argv = check.get('argv')
        require(isinstance(argv, list) and argv and all(isinstance(x, str) and x for x in argv), f'{cid}: argv 必须为非空字符串数组')
        require(check.get('kind') in ('probe', 'tests'), f'{cid}: kind 必须为 probe 或 tests')
        nonempty(check.get('purpose'), cid + ' purpose')
        inputs = check.get('inputs')
        require(isinstance(inputs, list) and inputs, f'{cid}: 必须明确相关输入')
        for path in inputs:
            safe(root, path)
        require(isinstance(check.get('timeout', 300), (int, float)) and 0 < check.get('timeout', 300) <= 86400, f'{cid}: timeout 无效')
        require(isinstance(check.get('environment', []), list) and all(isinstance(x, str) and x for x in check.get('environment', [])), f'{cid}: environment 无效')
    return c

def placeholder(text):
    return bool(re.search(r'\[(?:待填写|待建立|真实路径|创建后|接入后|未确认)[^\]]*\]|\[TODO:', text))

def doctor(root, c, check_ids=None):
    validate_config(root, c, check_ids)
    gaps, files = [], []
    for role, rel in c['authorities'].items():
        p = safe(root, rel)
        exists = p.is_file()
        files.append({'role': role, 'path': rel, 'exists': exists})
        if not exists or not p.read_text().strip():
            gaps.append(f'{role}: 文件缺失或为空: {rel}')
        elif placeholder(p.read_text()):
            gaps.append(f'{role}: 仍有待填写模板: {rel}')
    if not c.get('confirmation_source'):
        gaps.append('缺少项目规则确认或有效授权来源')
    if not c['checks']:
        gaps.append('尚未配置项目验证命令')
    for cid in c['checks'] if check_ids is None else sorted(check_ids):
        for rel in c['checks'][cid]['inputs']:
            if not safe(root, rel).exists():
                gaps.append(f'{cid}: 输入缺失: {rel}')
    # Check real Markdown links, not illustrative paths in template code blocks.
    for rel in set(c['authorities'].values()):
        p = safe(root, rel)
        if not p.is_file():
            continue
        body = re.sub(r'```.*?```', '', p.read_text(), flags=re.S)
        for target in re.findall(r'\]\(([^)]+)\)', body):
            if target.startswith(('http:', 'https:', '#', 'mailto:')):
                continue
            target = target.split('#', 1)[0]
            candidate = p.parent / target
            if not candidate.exists():
                gaps.append(f'链接缺失: {rel} -> {target}')
    entry = safe(root, c['authorities']['entrypoint'])
    if entry.is_file():
        body = re.sub(r'```.*?```', '', entry.read_text(), flags=re.S)
        linked = {(entry.parent / target.split('#', 1)[0]).resolve()
                  for target in re.findall(r'\]\(([^)]+)\)', body)
                  if not target.startswith(('http:', 'https:', '#', 'mailto:'))}
        for role in ('agent_policy', 'requirements', 'validation', 'status'):
            target = safe(root, c['authorities'][role]).resolve()
            if target != entry.resolve() and target not in linked:
                gaps.append(f'项目入口未链接 {role}: {c["authorities"][role]}')
    return {'mechanism_version': VERSION, 'files': files, 'gaps': gaps,
            'ready': not gaps, 'readiness_kind': 'files_configuration_and_navigation',
            'boundary': 'ready 仅表示文件、配置及导航检查就绪，不等于接入任务完成。规则语义及授权来源由开发 AI 核对。独立平台适配的启用、信任及实际触发需另行验证。'}

def adopt(root, mapping_path=None, apply=False):
    cp = safe(root, '.harness/project.json')
    if cp.exists():
        c = config(root)
        if mapping_path:
            proposed = load(Path(mapping_path))
            require(all(c.get(k) == v for k, v in proposed.items()), '已有配置与新映射不同；请先比较并在授权范围内合并，不自动覆盖')
        return {'action': 'reused', **doctor(root, c)}
    mapping = load(Path(mapping_path)) if mapping_path else {}
    require(isinstance(mapping, dict), '项目映射必须为对象')
    authorities = {**DEFAULTS, **mapping.get('authorities', {})}
    if 'validation' not in mapping.get('authorities', {}) and not (root/'TESTING.md').exists():
        candidates = [p for p in ('CONTRIBUTING.md', 'doc/DESIGN-PRINCIPLES.md', 'docs/TESTING.md') if (root/p).exists()]
        require(not candidates, '发现验证规则候选，先明确 validation 映射: ' + ', '.join(candidates))
    c = {'schema_version': 1, 'mechanism_version': VERSION, 'authorities': authorities,
         'confirmation_source': mapping.get('confirmation_source', ''), 'checks': mapping.get('checks', {})}
    # Validate against the actual project so existing symlink aliases are visible.
    validate_config(root, c)
    actions = []
    for role, rel in authorities.items():
        p = safe(root, rel)
        require(not p.exists() or p.is_file(), f'目标不是文件: {rel}')
        actions.append({'role': role, 'path': rel, 'action': 'reused' if p.exists() else 'created'})
        if not p.exists():
            template = PACKAGE/'assets/templates/core'/DEFAULTS.get(role, '')
            require(template.is_file(), f'附加职责 {role} 先创建实际文件再映射')
    if not apply:
        return {'action': 'preview', 'files': actions, 'note': '尚未写入；--apply 实际建立缺失文件，随后填写并检查。'}
    with lock(root):
        require(not cp.exists(), '接入配置刚被其他执行者创建，请重新读取')
        receipt = {'time': now(), 'files': [], 'ready': False}
        write_json(safe(root, '.harness/adoption.json'), receipt)
        for item in actions:
            p = safe(root, item['path'])
            if not p.exists():
                template = PACKAGE/'assets/templates/core'/DEFAULTS.get(item['role'], '')
                require(template.is_file(), f'附加职责 {item["role"]} 先创建实际文件再映射')
                atomic(p, template.read_text())
            receipt['files'].append(item)
            write_json(safe(root, '.harness/adoption.json'), receipt)
        write_json(cp, c)
    return {'action': 'applied', **doctor(root, c)}

def task_path(root, tid):
    return safe(root, f'docs/tasks/{identifier(tid)}.md')

def read_task(root, tid):
    p = task_path(root, tid)
    require(p.is_file(), f'任务不存在: {tid}')
    body = p.read_text()
    blocks = BLOCK.findall(body)
    require(len(blocks) == 1, '任务必须有且仅有一个 harness-task 数据块')
    try:
        t = json.loads(blocks[0])
    except ValueError as exc:
        raise HarnessError('任务数据块损坏') from exc
    require(isinstance(t, dict), '任务数据块必须是 JSON 对象')
    require(t.get('schema_version') in (1, 2) and t.get('id') == tid, '任务版本或 ID 不一致')
    return t, body

def v2_defaults(t):
    t.setdefault('purpose', {})
    t.setdefault('document_sync', {'reviewed': False, 'no_change_reason': '', 'items': []})
    for key in ('decisions', 'changes', 'followups', 'human_items', 'risk_routes'):
        t.setdefault(key, [])
    return t

def human_item_gaps(root, t, required=False):
    """Validate only the information needed for a human decision."""
    gaps, materials = [], {}
    items = t.get('human_items', [])
    if not isinstance(items, list) or (required and not items):
        return ['等待人需要具体问题与材料'], materials
    for item in items:
        try:
            require(isinstance(item, dict)
                    and all(isinstance(item.get(k), str) and item[k].strip()
                            for k in ('id', 'question', 'recommendation'))
                    and isinstance(item.get('materials'), list) and item['materials'],
                    '待人事项缺问题或材料')
            for path in item['materials']:
                materials[path] = material_digest(root, path, t['id'])
            require(not item.get('acceptance_id') or item['acceptance_id'] in {a['id'] for a in t['acceptance']},
                    '待人事项引用未知验收')
        except (HarnessError, KeyError, TypeError, OSError) as exc:
            gaps.append(str(exc))
    return gaps, materials

def record_gaps(root, t):
    if t['schema_version'] == 1:
        return [], {}
    gaps, materials = human_item_gaps(root, t)
    def check(condition, message):
        if not condition: gaps.append(message)
    def material(rel):
        p = safe(root, rel)
        require(p.is_file() and bool(p.read_text().strip()), f'材料缺失或为空: {rel}')
        materials[rel] = digest(p.read_bytes())
    try:
        purpose = t['purpose']
        check(isinstance(purpose.get('user_outcome', t['goal']), str) and bool(purpose.get('user_outcome', t['goal']).strip()), '缺少用户结果')
        if purpose.get('stage_ref'): material(purpose['stage_ref'])
        sync = t['document_sync']
        check(sync.get('reviewed') is True, '文档影响尚未审阅')
        items = sync.get('items', [])
        require(isinstance(items, list), '同步事项必须为数组')
        if not items: check(bool(sync.get('no_change_reason', '').strip()), '无文档变化需要理由')
        covered, ids = set(), set()
        for item in items:
            identifier(item.get('id'));check(item['id'] not in ids, '同步 ID 重复');ids.add(item['id'])
            require(isinstance(item.get('decision_ids'), list), '缺少关联决定列表')
            covered.update(item['decision_ids'])
            check(item.get('status') in ('updated', 'not_needed'), f'{item["id"]}: 同步待处理')
            check(bool(item.get('reason', '').strip()), f'{item["id"]}: 缺少处置理由')
            if item.get('status') == 'updated': material(item['path'])
        decision_ids = set()
        for d in t['decisions']:
            identifier(d.get('id'));check(d['id'] not in decision_ids, '决定 ID 重复');decision_ids.add(d['id'])
            check(d.get('kind') in ('confirmed','authorized','candidate','rejected','observation'), '决定分类无效')
            check(bool(d.get('summary')) and bool(d.get('source')), '决定缺来源或含义')
            if d.get('kind') in ('confirmed', 'authorized') and d.get('rule_ref'):
                material(d['rule_ref']);check(d['id'] in covered, f'{d["id"]}: 规则决定未关联同步处置')
        check(covered <= decision_ids, '同步引用未知决定')
        for x in t['changes']:
            safe(root, x['path']);check(bool(x.get('summary')), '实际差异缺说明')
        for x in t['followups']:
            check(all(x.get(k) for k in ('id','summary','owner','trigger','source')), '范围外后续缺归属或触发')
        for x in t['risk_routes']:
            check(x.get('kind') in ('experiment','recovery','side_effect','incident'), '风险分类无效')
            check(type(x.get('applicable')) is bool and bool(x.get('reason')), '风险缺适用判断或理由')
            if x.get('applicable'): material(x['record_ref'])
    except (HarnessError, KeyError, TypeError, AttributeError, OSError) as exc:
        gaps.append(f'任务处置无效: {exc}')
    return gaps, materials

def migrate_task(root, c, tid, apply=False):
    with lock(root) if apply else contextlib.nullcontext():
        t, body = read_task(root, tid)
        if t['schema_version'] == 2: return {'applied': False, 'reason': 'already_v2'}
        original = task_path(root, tid).read_bytes()
        candidate = v2_defaults(dict(t));candidate['schema_version'] = 2
        result = {'applied': False, 'candidate': candidate, 'gaps': record_gaps(root, candidate)[0]}
        if apply:
            # UUID prevents overwriting even when the same original is migrated twice.
            backup = f'.harness/migrations/{tid}-{uuid.uuid4().hex}.md'
            atomic(safe(root, backup), original.decode())
            candidate['migration'] = {'backup': backup, 'sha256': digest(original), 'from': 1}
            write_task(root, c, candidate, body)
            result.update(applied=True, backup=backup)
        return result

def update_task(root, c, tid, candidate):
    require(isinstance(candidate, dict), '任务更新快照必须是 JSON 对象')
    with lock(root):
        t, body = read_task(root, tid)
        require(t['schema_version'] == 2, '旧任务先 migrate-task')
        require(candidate.get('updated_at') == t['updated_at'], '任务已变化，请重新读取')
        for key in ('id','schema_version','state','created_at','migration','review_source','review_sha256','review_kind','review_record_sha256'):
            require(candidate.get(key) == t.get(key), f'不能通过 update 改变 {key}')
        validate_task(candidate, c)
        write_task(root, c, candidate, body)
        return candidate

def human_summary(t, assessment):
    return {'updated_at': t.get('updated_at'), 'user_outcome': t.get('purpose', {}).get('user_outcome', t['goal']),
            'next_action': t['next_action'], 'next_reason': t.get('next_reason'),
            'human_items': t.get('human_items', []), 'gaps': assessment['gaps'],
            'evidence_conditions_met': assessment['conditions_met'],
            'note': '说明由开发 AI 记录；检查条件满足不代表语义或人的确认真实。'}

def contract(t):
    return {k: t[k] for k in ('id', 'goal', 'scope', 'authorization', 'acceptance')}

def review_record(t):
    managed = {'state', 'updated_at', 'next_action', 'next_reason',
               'review_source', 'review_sha256', 'review_kind', 'review_record_sha256'}
    return {k: v for k, v in t.items() if k not in managed}

def source_kind(root, rel, tid):
    return 'task_body' if safe(root, rel).resolve() == task_path(root, tid).resolve() else 'file'

def material_digest(root, rel, tid, kind='file'):
    p = safe(root, rel)
    require(p.is_file(), f'材料缺失或为空: {rel}')
    require(kind in ('file', 'task_body'), '材料指纹类型无效')
    if kind == 'task_body':
        require(p.resolve() == task_path(root, tid).resolve(), '任务正文材料对象不匹配')
        body = p.read_text()
        require(len(BLOCK.findall(body)) == 1, '任务正文必须有唯一数据块')
        content = BLOCK.sub('', body, count=1).encode()
    else:
        content = p.read_bytes()
    require(bool(content.strip()), f'材料缺失或为空: {rel}')
    return digest(content)

def reconcile_run(root, c, tid, runid, outcome, source):
    """Append a checked disposition. It never rewrites a RUN or supplies a pass."""
    identifier(runid)
    require(outcome in ('finished', 'stopped'), '未知结局不能解除在途缺口')
    with lock(root):
        t, _ = read_task(root, tid)
        require(t['schema_version'] == 2, '旧任务先 migrate-task')
        directory = safe(root, f'.harness/evidence/{tid}/{runid}')
        p = safe(root, str((directory/'summary.json').relative_to(root)))
        rec = load(p)
        require(isinstance(rec, dict) and rec.get('task_id') == tid and rec.get('run_id') == runid, 'RUN 对象不匹配')
        seal_path = safe(root, str((directory/'summary.sha256').relative_to(root)))
        require(seal_path.read_text().strip() == digest(p.read_bytes()), '执行回执校验和不符')
        require(rec.get('overall_status') == 'running', '只处置未结束的历史 RUN；已结束结果保留原样')
        require(safe(root, source).resolve() != safe(root, c['authorities']['status']).resolve(), '状态摘要不能作为现场核对材料')
        kind = source_kind(root, source, tid)
        result = {'schema_version': 1, 'task_id': tid, 'run_id': runid,
                  'run_sha256': digest(p.read_bytes()), 'outcome': outcome,
                  'source': source, 'source_kind': kind,
                  'source_sha256': material_digest(root, source, tid, kind), 'time': now()}
        result['sha256'] = digest(result)
        name = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f-') + uuid.uuid4().hex
        rel = f'.harness/reconciliations/{tid}/{runid}/{name}.json'
        write_json(safe(root, rel), result)
        return {'receipt': rel, **result}

def resolved_run(root, tid, runid, summary_path):
    base = safe(root, f'.harness/reconciliations/{tid}/{runid}')
    receipts = sorted(base.glob('*.json'))
    if not receipts:
        return None
    p = safe(root, str(receipts[-1].relative_to(root)))
    r = load(p)
    require(isinstance(r, dict), '在途处置必须是 JSON 对象')
    require(r.get('sha256') == digest({k:v for k,v in r.items() if k != 'sha256'}), '在途处置校验和不符')
    require(r.get('schema_version') == 1 and r.get('task_id') == tid and r.get('run_id') == runid, '在途处置对象不匹配')
    require(r.get('outcome') in ('finished', 'stopped'), '在途处置结局仍未知')
    require(r.get('run_sha256') == digest(summary_path.read_bytes()), '在途处置与原 RUN 不符')
    require(r.get('source_sha256') == material_digest(root, r.get('source'), tid, r.get('source_kind')), '现场核对材料已改变，需重新核对在途处置')
    return r['sha256']

def validate_task(t, c):
    require(t.get('schema_version') in (1,2), '未知任务版本')
    if t['schema_version'] == 2:
        require(all(isinstance(t.get(k), list) and all(isinstance(x, dict) for x in t[k]) for k in ('decisions','changes','followups','human_items','risk_routes')), 'v2记录列表无效')
        require(isinstance(t.get('purpose'), dict) and isinstance(t.get('document_sync'), dict), 'v2目标与同步字段缺失')
    for key in ('goal', 'scope', 'authorization', 'next_action'):
        nonempty(t.get(key), key)
    acs = t.get('acceptance')
    require(isinstance(acs, list) and acs, '必须有验收标准')
    seen = set()
    for ac in acs:
        identifier(ac.get('id'))
        require(ac['id'] not in seen, '验收标准 ID 重复')
        seen.add(ac['id'])
        nonempty(ac.get('text'), '验收标准')
        checks = ac.get('checks')
        require(isinstance(checks, list) and checks and len(set(checks)) == len(checks), '每项标准必须关联不重复的检查；人工材料也需检查存在')
        require(all(x in c['checks'] for x in checks), '验收标准引用未知检查')
        require(type(ac.get('human_required', False)) is bool, 'human_required 必须为布尔值')

def write_task(root, c, t, body):
    t['updated_at'] = now()
    newblock = '```harness-task\n' + json.dumps(t, ensure_ascii=False, indent=2) + '\n```'
    updated = BLOCK.sub(lambda _: newblock, body, count=1)
    sp = safe(root, c['authorities']['status'])
    prior = sp.read_text() if sp.exists() else '# 当前工作入口\n'
    rel = os.path.relpath(task_path(root, t['id']), sp.parent)
    section = f'{START}\n当前任务：[{t["id"]}]({rel})\n\n目标：{t["goal"]}\n\n任务执行状态：{t["state"]}\n\n下一动作：{t["next_action"]}\n\n详细验收、验证和人工验收以任务记录为准。\n{END}'
    if t.get('schema_version') == 2:
        snapshot = human_summary(t, assess(root, c, t))
        extra = [f'更新于：{t["updated_at"]}', f'用户结果：{snapshot["user_outcome"]}',
                 '当前检查：' + ('条件满足' if snapshot['evidence_conditions_met'] else '存在缺口')]
        if snapshot['next_reason']: extra.append(f'下一步原因：{snapshot["next_reason"]}')
        extra.extend('缺口：' + x for x in snapshot['gaps'])
        extra.extend(f'待人判断：{x.get("question")}；建议：{x.get("recommendation")}；材料：{x.get("materials")}' for x in snapshot['human_items'])
        section = section.replace(END, '\n'.join(extra) + '\n' + END)
    if START in prior or END in prior:
        require(prior.count(START) == 1 and prior.count(END) == 1 and prior.index(START) < prior.index(END), '状态托管区损坏，请先修复')
        prior = prior[:prior.index(START)] + section + prior[prior.index(END)+len(END):]
    else:
        prior = prior.rstrip() + '\n\n' + section + '\n'
    atomic(task_path(root, t['id']), updated)
    atomic(sp, prior)

def begin(root, c, spec):
    require(isinstance(spec, dict), '任务规格必须是 JSON 对象')
    t = dict(spec)
    identifier(t.get('id'))
    require(spec.get('schema_version', 2) == 2, '新建任务使用 schema_version=2；旧任务显式迁移')
    t.update(schema_version=2, state='in_progress', created_at=now(), human_acceptance={})
    v2_defaults(t)
    validate_task(t, c)
    require(doctor(root, c, task_check_ids(t))['ready'], '任务前置未就绪；核对共同规则及所选检查缺口')
    with lock(root):
        require(not task_path(root, t['id']).exists(), '任务已存在；使用 resume，不覆盖')
        write_task(root, c, t, '# ' + t['id'] + '\n\n```harness-task\n{}\n```\n\n## 执行事实与决定\n\n任务建立。实施后在此记录实际差异、决定及后续事项。\n')
    return t

def fingerprints(root, c, t, cid):
    chk = c['checks'][cid]
    paths = set(chk['inputs']) | {c['authorities'][k] for k in ('requirements', 'validation', 'agent_policy')}
    files = {}
    for rel in sorted(paths):
        p = safe(root, rel)
        require(p.exists(), f'相关输入缺失: {rel}')
        if p.is_dir():
            members = sorted(x for x in p.rglob('*') if x.is_file() and '__pycache__' not in x.parts and x.name != '.DS_Store')
            files[rel + '/'] = [str(x.relative_to(root)) for x in members]
        else:
            members = [p]
        for x in members:
            safe(root, str(x.relative_to(root)))
            files[str(x.relative_to(root))] = digest(x.read_bytes())
    environment = {'python': sys.version, 'platform': sys.platform}
    environment.update({k: digest(os.environ.get(k)) for k in chk.get('environment', [])})
    return {'files': files, 'environment': environment, 'check': digest(chk),
            'contract': digest(contract(t)), 'confirmation': digest(c.get('confirmation_source')),
            'runner': digest(Path(__file__).read_bytes())}

def seal(root, run, rec):
    write_json(safe(root, run + '/summary.json'), rec)
    atomic(safe(root, run + '/summary.sha256'), digest(safe(root, run + '/summary.json').read_bytes()) + '\n')

def stop_process_group(proc):
    """Bound cleanup of this execution's group, including descendants of an exited leader."""
    try:
        for signum in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, signum)
            except ProcessLookupError:
                proc.poll()
                return None
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                proc.poll()  # Reap the leader, but do not confuse its exit with group exit.
                try:
                    os.killpg(proc.pid, 0)
                except ProcessLookupError:
                    proc.poll()
                    return None
                except PermissionError:
                    # An exiting group can briefly be unqueryable on macOS.
                    # Retry within the deadline; EPERM never proves it stopped.
                    pass
                time.sleep(0.05)
        return '清理时限内未确认进程组消失'
    except (OSError, KeyboardInterrupt) as exc:
        return str(exc) or '清理被再次中断'

def verify(root, c, tid, cid):
    identifier(cid)
    t, _ = read_task(root, tid)
    validate_task(t, c)
    require(t['schema_version'] == 2, '旧任务继续执行前须 migrate-task')
    require(t['state'] == 'in_progress', '任务须为进行中；暂停或结束后先显式恢复并核对范围')
    require(cid in {x for ac in t['acceptance'] for x in ac['checks']}, '检查不在当前任务验收范围')
    chk = c['checks'][cid]
    initial = fingerprints(root, c, t, cid)
    runid = dt.datetime.now(dt.timezone.utc).strftime('RUN-%Y%m%dT%H%M%S%f-') + uuid.uuid4().hex[:8]
    run = f'.harness/evidence/{tid}/{runid}'
    rec = {'schema_version': 1, 'task_id': tid, 'run_id': runid, 'check_id': cid,
           'started_at': now(), 'finished_at': None, 'argv': chk['argv'], 'cwd': str(root),
           'overall_status': 'running', 'verification_status': 'unverified', 'exit_code': None,
           'inputs': initial, 'validity': 'indeterminate', 'counts': None, 'reason': '', 'pid': os.getpid()}
    with lock(root):
        safe(root, run).mkdir(parents=True, exist_ok=False)
        seal(root, run, rec)
    env = os.environ.copy()
    env['AI_PROJECT_HARNESS_REPORT'] = str(safe(root, run + '/test-report.json'))
    proc = None
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        with safe(root, run + '/output.log').open('wb') as log:
            try:
                proc = subprocess.Popen(chk['argv'], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                rec['child_pid'] = proc.pid
                seal(root, run, rec)
                rec['exit_code'] = proc.wait(timeout=chk.get('timeout', 300))
                rec['overall_status'] = 'passed' if rec['exit_code'] == 0 else 'failed'
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                reason = 'timeout' if isinstance(exc, subprocess.TimeoutExpired) else 'signal_or_interrupt'
                rec['overall_status'] = 'running'
                rec['reason'] = reason + '；本次进程组停止状态未知，先核对现场再追加处置'
                if proc is not None:
                    cleanup_error = stop_process_group(proc)
                    rec['exit_code'] = proc.returncode
                    if cleanup_error is None:
                        rec['overall_status'] = 'interrupted'
                        rec['reason'] = reason
                    else:
                        rec['reason'] += '：' + cleanup_error
            except OSError as exc:
                rec['overall_status'] = 'error'
                rec['reason'] = str(exc)
        if chk['kind'] == 'tests' and rec['overall_status'] in ('passed', 'failed'):
            try:
                counts = load(safe(root, run + '/test-report.json'))
                require(isinstance(counts, dict), '计数报告必须是 JSON 对象')
                require(all(type(counts.get(k)) is int and counts[k] >= 0 for k in ('total', 'failed', 'errors', 'skipped')), '计数报告字段无效')
                require(counts['failed'] + counts['errors'] + counts['skipped'] <= counts['total'], '计数报告不一致')
                rec['counts'] = counts
                if (counts['total'] == 0 or counts['skipped'] == counts['total']) and rec['exit_code'] == 0:
                    rec['overall_status'] = 'skipped'
                elif counts['failed'] or counts['errors'] or counts['skipped']:
                    rec['overall_status'] = 'failed'
                    rec['reason'] = '存在失败、异常或未覆盖的必需测试'
                rec['report_sha256'] = digest(safe(root, run + '/test-report.json').read_bytes())
            except HarnessError as exc:
                rec['overall_status'] = 'error'
                rec['reason'] = str(exc)
        try:
            current_t, _ = read_task(root, tid)
            rec['validity'] = 'valid' if fingerprints(root, config(root, task_check_ids(current_t)), current_t, cid) == initial else 'invalidated'
        except HarnessError as exc:
            rec['validity'] = 'indeterminate'
            rec['reason'] += str(exc)
        rec['verification_status'] = 'verified' if rec['overall_status'] == 'passed' and rec['validity'] == 'valid' else 'unverified'
    finally:
        signal.signal(signal.SIGTERM, previous)
        rec['finished_at'] = None if rec['overall_status'] == 'running' else now()
        logpath = safe(root, run + '/output.log')
        rec['log_sha256'] = digest(logpath.read_bytes()) if logpath.exists() else None
        seal(root, run, rec)
    return {'run': run, **rec}

def fingerprint_changes(before, after):
    """Explain identity changes without returning values (including env hashes)."""
    if not isinstance(before, dict):
        return [{'kind': 'fingerprint', 'name': 'inputs', 'change': 'unavailable'}]
    changes = []
    for group in ('files', 'environment'):
        old, new = before.get(group, {}), after.get(group, {})
        if not isinstance(old, dict):
            changes.append({'kind': 'fingerprint', 'name': group, 'change': 'unavailable'})
            continue
        for name in sorted(old.keys() | new.keys()):
            if name not in old or name not in new or old[name] != new[name]:
                kind = 'directory' if group == 'files' and name.endswith('/') else ('file' if group == 'files' else 'environment')
                changes.append({'kind': kind, 'name': name,
                                'change': 'added' if name not in old else 'removed' if name not in new else 'modified'})
    for name in ('check', 'contract', 'confirmation', 'runner'):
        if before.get(name) != after.get(name):
            changes.append({'kind': name, 'name': name, 'change': 'modified'})
    return changes


def assess_check(root, c, t, cid, directory, rec):
    """One check evaluation supplies both the legacy gate and its explanation."""
    result = {'run_id': rec['run_id'] if rec else None,
              'execution_status': rec.get('overall_status', 'unknown') if rec else 'not_run',
              'evidence_status': 'missing' if rec is None else 'unverified',
              'conditions_met': False, 'log': None, 'diagnostics': []}
    def explain(code, message, action, changes=None):
        item = {'code': code, 'message': message, 'action': action}
        if changes: item['changes'] = changes
        result['diagnostics'].append(item)
    if rec is None:
        gap = '缺少执行证据'
        explain('missing_run', gap, f'核对执行前置后运行 verify {t["id"]} {cid}。')
        return result, gap
    result['log'] = str((directory/'output.log').relative_to(root))
    current, input_error = None, None
    try:
        current = fingerprints(root, c, t, cid)
    except (HarnessError, OSError) as exc:
        input_error = str(exc)
    changes = fingerprint_changes(rec.get('inputs'), current) if current is not None else []
    if changes or rec.get('validity') == 'invalidated':
        result['evidence_status'] = 'stale'
        explain('inputs_changed', '相关输入变化，证据已失效' if changes else '执行期间输入曾变化，该次证据仍失效',
                f'核对列出的变化及当前验证对象；仍需此检查时重新运行 verify {t["id"]} {cid}。', changes)
    elif input_error or rec.get('validity') != 'valid':
        result['evidence_status'] = 'unknown'
        explain('inputs_unavailable', input_error or '执行时输入有效性未确定', '补齐或核对相关输入及环境后重新评估；不使用旧通过代替。')
    # Keep the original gate order and messages for existing consumers.
    stage = 'execution'
    try:
        require(rec.get('overall_status') == 'passed' and rec.get('verification_status') == 'verified' and rec.get('exit_code') == 0, '最近执行未通过或未结束')
        stage = 'inputs'
        if input_error: raise HarnessError(input_error)
        require(rec.get('validity') == 'valid' and rec.get('inputs') == current, '相关输入变化，证据已失效')
        stage = 'log'
        require(digest((directory/'output.log').read_bytes()) == rec.get('log_sha256'), '日志损坏或缺失')
        if c['checks'][cid]['kind'] == 'tests':
            stage = 'counts'
            counts = rec.get('counts') or {}
            require(counts.get('total', 0) > 0 and all(counts.get(k) == 0 for k in ('failed', 'errors', 'skipped')), '必需测试计数未通过')
            stage = 'report'
            require(digest((directory/'test-report.json').read_bytes()) == rec.get('report_sha256'), '测试计数报告损坏')
    except (HarnessError, OSError) as exc:
        gap = str(exc)
        if stage in ('log', 'report', 'counts'):
            result['evidence_status'] = 'invalid'
            explain('invalid_' + stage, gap, '核对该 RUN 原始日志与报告，保留损坏记录；重新取得有效证据。')
        elif stage == 'execution' and (rec.get('overall_status') != 'passed' or not result['diagnostics']):
            running = rec.get('overall_status') == 'running'
            explain('execution_unfinished' if running else 'execution_failed', gap,
                    '先核对现场与副作用；仅在确认结局后按 reconcile-run 追加处置，不盲目重放。' if running else
                    f'查看日志及 RUN 摘要，修复失败或补齐环境后运行 verify {t["id"]} {cid}；不回退旧成功。')
        return result, gap
    result.update(conditions_met=True, evidence_status='valid')
    return result, None


def assess(root, c, t):
    validate_task(t, c)
    gaps = list(doctor(root, c, task_check_ids(t))['gaps'])
    rgaps, materials = record_gaps(root, t)
    gaps.extend(rgaps)
    if t['schema_version'] == 2 and t.get('state') == 'completed' and not t.get('review_source'):
        gaps.append('已完成任务缺审阅材料')
    if t['schema_version'] == 2 and t.get('review_source'):
        try:
            require(material_digest(root, t['review_source'], t['id'], t.get('review_kind', 'file')) == t.get('review_sha256'), '审阅材料已改变，需重新审阅并完成')
            if t.get('review_record_sha256'):
                require(digest(review_record(t)) == t['review_record_sha256'], '受审任务记录已改变，需重新审阅并完成')
        except (HarnessError, OSError) as exc:
            gaps.append(str(exc))
    selected = {}
    base = safe(root, f'.harness/evidence/{t["id"]}')
    dirs = sorted((p for p in base.iterdir() if p.is_dir()), reverse=True) if base.exists() else []
    records, reconciliations = [], {}
    for directory in dirs:
        try:
            safe(root, str(directory.relative_to(root)))
            for name in ('summary.json', 'summary.sha256', 'output.log', 'test-report.json'):
                safe(root, str((directory/name).relative_to(root)))
            p = directory/'summary.json'
            rec = load(p)
            require(isinstance(rec, dict), '执行回执必须是 JSON 对象')
            require((directory/'summary.sha256').read_text().strip() == digest(p.read_bytes()), '执行回执校验和不符')
            require(rec.get('task_id') == t['id'] and rec.get('run_id') == directory.name, 'RUN 对象不匹配')
            if rec.get('overall_status') == 'running':
                resolution = resolved_run(root, t['id'], directory.name, p)
                if resolution is None:
                    gaps.append(f'{directory.name}: 执行仍在进行或中断后结局未知，先核对现场并 reconcile-run')
                else:
                    reconciliations[directory.name] = resolution
            records.append((directory, rec))
        except (HarnessError, OSError) as exc:
            gaps.append(f'无效执行回执 {directory.name}: {exc}')
    global_gaps = list(gaps)
    check_results, acceptance_results = {}, []
    for ac in t['acceptance']:
        for cid in ac['checks']:
            if cid in selected:
                continue
            matches = [(p, r) for p, r in records if r.get('check_id') == cid]
            if not matches:
                selected[cid] = None
                detail, gap = assess_check(root, c, t, cid, None, None)
            else:
                directory, rec = matches[0]
                selected[cid] = rec['run_id']
                detail, gap = assess_check(root, c, t, cid, directory, rec)
            check_results[cid] = detail
            if gap: gaps.append(f'{cid}: {gap}')
        human_status = 'not_required'
        if ac.get('human_required'):
            h = t.get('human_acceptance', {}).get(ac['id'], {})
            if h.get('status') != 'accepted' or not h.get('source') or h.get('contract') != digest(contract(t)):
                human_status = 'pending'
                gaps.append(f'{ac["id"]}: 必需人工验收未确认、无来源或范围已改变')
            else:
                human_status = 'recorded'
        met = not global_gaps and human_status != 'pending' and all(check_results[cid]['conditions_met'] for cid in ac['checks'])
        acceptance_results.append({'id': ac['id'], 'text': ac['text'], 'checks': ac['checks'],
                                   'human_status': human_status, 'conditions_met': met})
    return {'task_id': t['id'], 'time': now(), 'conditions_met': not gaps, 'gaps': gaps, 'runs': selected,
            'global_gaps': global_gaps, 'check_results': check_results, 'acceptance_results': acceptance_results,
            'record_fingerprint': digest({'task': {k:v for k,v in t.items() if k not in ('state','updated_at','next_action','next_reason')}, 'materials': materials, 'reconciliations': reconciliations}),
            'coverage': 'v2' if t['schema_version'] == 2 else 'legacy',
            'contract': digest(contract(t)), 'boundary': '机械条件检查；不证明人工来源真实性、需求语义正确或平台强制阻断。'}

def close(root, c, tid, complete=False, review_source=None):
    with lock(root):
        t, body = read_task(root, tid)
        assessed = dict(t)
        if complete and t['schema_version'] == 2:
            for key in ('review_source','review_sha256','review_kind','review_record_sha256'):
                assessed.pop(key, None)
            assessed['state'] = 'in_progress'
        result = assess(root, c, assessed)
        if complete:
            nonempty(review_source, '真实差异及语义审阅来源')
            if t['schema_version'] == 2:
                require(safe(root, review_source).resolve() != safe(root, c['authorities']['status']).resolve(), '状态摘要不能作为审阅材料；请引用任务正文或独立审阅文件')
                review_kind = source_kind(root, review_source, tid)
                result['review_sha256'] = material_digest(root, review_source, tid, review_kind)
            if not result['conditions_met']:
                t['state'] = 'blocked'
                t['next_action'] = '处理交付缺口：' + '; '.join(result['gaps'])
            else:
                t['state'] = 'completed'
                t['next_action'] = '当前工程任务已完成；后续工作按新授权建立任务。'
                t['review_source'] = review_source
                if t['schema_version'] == 2:
                    t.update(review_sha256=result['review_sha256'], review_kind=review_kind,
                             review_record_sha256=digest(review_record(t)))
            write_task(root, c, t, body)
        if complete and result['conditions_met']:
            result['record_fingerprint'] = assess(root, c, t)['record_fingerprint']
        result['task_state'] = t['state']
        path = f'.harness/close/{tid}/{dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%f")}.json'
        write_json(safe(root, path), result)
        result['receipt'] = path
        return result

def resume(root, c, tid, activate=False):
    with lock(root):
        t, body = read_task(root, tid)
        if activate:
            require(t['schema_version'] == 2, '旧任务继续执行前须 migrate-task')
            require(t['state'] != 'cancelled', '已取消任务需新建有明确授权的任务')
            if t['state'] == 'completed':
                t['next_action'] = '核对恢复原因、现行任务范围和证据，继续当前授权内尚未完成的工作。'
            t['state'] = 'in_progress'
            write_task(root, c, t, body)
        assessment = assess(root, c, t)
        return {'task': t, 'assessment': assessment, 'summary': human_summary(t, assessment), 'task_record': str(task_path(root, tid)),
                'note': '核对现场和在途操作后再运行；resume 不执行测试、不重发副作用。'}

def readable_assessment(assessment):
    execution = {'not_run': '未执行', 'passed': '通过', 'failed': '失败', 'error': '异常',
                 'skipped': '跳过/零测试', 'running': '进行中或结局未知', 'interrupted': '已中断'}
    evidence = {'missing': '缺失', 'valid': '有效', 'stale': '已失效', 'invalid': '损坏或不合格',
                'unknown': '无法判定', 'unverified': '未验证'}
    humans = {'not_required': '不要求', 'pending': '待确认或需重新确认', 'recorded': '已记录确认（未核实来源真实性）'}
    kinds = {'file': '文件', 'directory': '目录清单', 'environment': '环境', 'check': '检查定义',
             'contract': '任务标准', 'confirmation': '授权来源', 'runner': '执行器', 'fingerprint': '输入指纹'}
    changes = {'added': '新增', 'removed': '移除', 'modified': '变化', 'unavailable': '无法比较'}
    lines = ['交付机械条件：' + ('已满足' if assessment['conditions_met'] else '有缺口')]
    lines.extend('共同缺口：' + gap for gap in assessment['global_gaps'])
    for ac in assessment['acceptance_results']:
        lines.append(f'验收 {ac["id"]}：{ac["text"]}；检查：{", ".join(ac["checks"]) or "仅人工"}；'
                     f'机械条件：{"满足" if ac["conditions_met"] else "有缺口"}；人工：{humans[ac["human_status"]]}')
    for cid, item in assessment['check_results'].items():
        lines.append(f'检查 {cid}：执行{execution.get(item["execution_status"], "未知")}；'
                     f'证据{evidence[item["evidence_status"]]}；RUN：{item["run_id"] or "无"}')
        if item['log']: lines.append('  日志：' + item['log'])
        for d in item['diagnostics']:
            lines.append('  原因：' + d['message'])
            for change in d.get('changes', []):
                lines.append(f'    {kinds[change["kind"]]} {change["name"]}：{changes[change["change"]]}')
            lines.append('  处置：' + d['action'])
    lines.append(assessment['boundary'])
    return lines


def readable_close(result):
    return '\n'.join([f'任务：{result["task_id"]}', f'任务执行状态：{result["task_state"]}',
                      *readable_assessment(result), f'交付回执：{result["receipt"]}'])


def readable_resume(result):
    t, assessment = result['task'], result['assessment']
    labels = {'not_started':'未开始','in_progress':'进行中','blocked':'阻塞',
              'interrupted':'已中断','completed':'已完成','cancelled':'已取消'}
    lines = [f'任务：{t["id"]}', f'目标：{t["goal"]}', f'范围：{t["scope"]}',
             f'任务执行状态：{labels.get(t["state"], t["state"])}',
             f'下一动作：{t["next_action"]}', f'任务记录：{result["task_record"]}']
    if t['schema_version'] == 2:
        lines += [f'用户结果：{t["purpose"].get("user_outcome", t["goal"]) or "未填写"}',
                  f'更新于：{t.get("updated_at")}']
        if t.get('next_reason'): lines.append(f'下一步原因：{t["next_reason"]}')
        lines += [f'待人判断：{x.get("question") or "未填写"}；建议：{x.get("recommendation") or "未填写"}；材料：{x.get("materials") or "未填写"}' for x in t['human_items']]
    lines.extend(readable_assessment(assessment))
    lines.append(result['note'])
    return '\n'.join(lines)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', help='目标项目目录')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('adopt', help='预览或实际建立项目文件，已有文件不覆盖')
    p.add_argument('--mapping'); p.add_argument('--apply', action='store_true')
    sub.add_parser('doctor', help='检查接入、配置、真实内容与引用')
    p = sub.add_parser('begin', help='从 JSON 规格建立唯一任务记录'); p.add_argument('--spec', required=True)
    p = sub.add_parser('verify', help='实际执行项目配置的检查并保存独立 RUN'); p.add_argument('task'); p.add_argument('check')
    p = sub.add_parser('close', help='重新核对交付条件；可据实标记完成'); p.add_argument('task'); p.add_argument('--complete', action='store_true'); p.add_argument('--review-source')
    p.add_argument('--format', choices=['json','text'], default='json', help='文本验收视图或完整 JSON；不改变判定与命令副作用')
    p = sub.add_parser('pause', help='保存中断状态及下一动作'); p.add_argument('task'); p.add_argument('--next', required=True)
    p = sub.add_parser('resume', help='读取任务、证据与下一动作'); p.add_argument('task'); p.add_argument('--activate', action='store_true')
    p.add_argument('--format', choices=['json','text'], default='json', help='文本摘要或完整 JSON；不改变执行状态')
    p = sub.add_parser('migrate-task', help='旧任务升级预览；--apply 保留原件并写入'); p.add_argument('task'); p.add_argument('--apply', action='store_true')
    p = sub.add_parser('reconcile-run', help='现场核对后追加历史在途 RUN 处置，不改写原件或代替验证')
    p.add_argument('task'); p.add_argument('run'); p.add_argument('--outcome', choices=['finished','stopped'], required=True); p.add_argument('--source', required=True)
    p = sub.add_parser('update', help='用带更新时间的完整 JSON 快照更新任务'); p.add_argument('task'); p.add_argument('--spec', required=True)
    a = parser.parse_args(argv)
    root = Path(a.root).resolve()
    try:
        require(root.is_dir(), '目标项目目录不存在')
        if a.command == 'adopt':
            result = adopt(root, a.mapping, a.apply)
        else:
            spec = load(Path(a.spec)) if a.command == 'begin' else None
            selection = None if a.command == 'doctor' else task_check_ids(spec if spec is not None else read_task(root, a.task)[0])
            c = config(root, selection)
            if a.command == 'doctor': result = doctor(root, c)
            elif a.command == 'begin': result = begin(root, c, spec)
            elif a.command == 'migrate-task': result = migrate_task(root, c, a.task, a.apply)
            elif a.command == 'update': result = update_task(root, c, a.task, load(Path(a.spec)))
            elif a.command == 'verify': result = verify(root, c, a.task, a.check)
            elif a.command == 'close': result = close(root, c, a.task, a.complete, a.review_source)
            elif a.command == 'reconcile-run': result = reconcile_run(root, c, a.task, a.run, a.outcome, a.source)
            elif a.command == 'resume': result = resume(root, c, a.task, a.activate)
            else:
                nonempty(a.next, '下一动作')
                with lock(root):
                    t, body = read_task(root, a.task)
                    require(t['schema_version'] == 2, '旧任务继续执行前须 migrate-task')
                    require(t['state'] not in ('completed', 'cancelled'), '已结束任务不能暂停')
                    t['state'], t['next_action'] = 'interrupted', a.next
                    write_task(root, c, t, body)
                    result = t
        if a.command == 'resume' and a.format == 'text':
            print(readable_resume(result))
        elif a.command == 'close' and a.format == 'text':
            print(readable_close(result))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if a.command == 'verify': return 0 if result['verification_status'] == 'verified' else 1
        if a.command == 'close': return 0 if result['conditions_met'] else 1
        if a.command == 'doctor': return 0 if result['ready'] else 1
        return 0
    except (HarnessError, KeyError, TypeError, ValueError, OSError) as exc:
        print(json.dumps({'error': str(exc), 'status': 'error'}, ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())
