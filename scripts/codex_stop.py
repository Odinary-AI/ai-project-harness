#!/usr/bin/env python3
"""Codex lifecycle adapter; no model calls, trust overrides or business retries."""
import argparse
import json
from pathlib import Path
import shlex
import sys
import uuid
import harness as h


def binding_path(root, session):
    h.nonempty(session, 'session ID')
    return h.safe(root, '.harness/codex/' + h.digest(session) + '.json')


def bind(root, session, task):
    t, _ = h.read_task(root, task)
    h.require(t['schema_version'] == 2, '先迁移任务')
    with h.lock(root):
        p = binding_path(root, session)
        if p.exists():
            old = h.load(p)
            h.require(old['task'] == task, '会话已绑定其他任务；先显式 unbind')
            return old
        rec = {'session': session, 'task': task, 'bound_at': h.now(), 'turn': None,
               'disposition': None, 'reason': None, 'retry_gap': None}
        h.write_json(p, rec)
        return rec


def disposition(root, session, turn, mode, reason):
    h.nonempty(turn, 'turn ID');h.nonempty(reason, '本轮处置依据')
    h.require(mode in ('progress','completion','waiting_human','interrupted'), '处置无效')
    with h.lock(root):
        p = binding_path(root, session);rec = h.load(p)
        t, _ = h.read_task(root, rec['task'])
        if mode == 'waiting_human':
            gaps, _ = h.human_item_gaps(root, t, required=True)
            h.require(not gaps, '; '.join(gaps))
        if mode == 'interrupted': h.require(t['state'] in ('interrupted','blocked'), '先记录任务中断或阻塞')
        rec.update(turn=turn, disposition=mode, reason=reason, updated_at=h.now())
        h.write_json(p, rec)
        return rec


def handle(root, event):
    h.require(isinstance(event, dict), '事件必须为对象')
    h.require(event.get('hook_event_name') == 'Stop', '仅处理 Stop')
    h.require(Path(event.get('cwd', '')).resolve() == root.resolve(), '事件项目不匹配')
    session = event.get('session_id');turn = event.get('turn_id')
    h.nonempty(turn, 'turn ID')
    p = binding_path(root, session)
    with h.lock(root):
        if not p.exists():
            return {'systemMessage':'AI工程机制：会话未显式绑定，未启用该任务检查。'}
        rec = h.load(p)
        h.require(rec['session'] == session, '会话绑定不匹配')
        t, _ = h.read_task(root, rec['task'])
        gaps = []
        mode = rec['disposition'] if rec['turn'] == turn else None
        if mode is None:
            gaps = ['本轮未记录处置；请记录进度、完成候选、等待人或中断，不扩大当前授权。']
        elif mode == 'completion':
            assessment = h.assess(root, h.config(root, h.task_check_ids(t)), t)
            gaps = assessment['gaps']
            if t['state'] != 'completed': gaps = gaps + ['尚未通过 close --complete']
            directory = h.safe(root, '.harness/close/' + t['id'])
            receipts = sorted(directory.glob('*.json')) if directory.exists() else []
            if receipts:
                latest_path = h.safe(root, str(receipts[-1].relative_to(root)))
                latest = h.load(latest_path)
                if not (latest.get('task_id') == t['id'] and latest.get('conditions_met') is True
                        and latest.get('task_state') == 'completed'
                        and latest.get('record_fingerprint') == assessment['record_fingerprint']):
                    gaps = gaps + ['交付回执未覆盖当前任务记录']
            else: gaps = gaps + ['缺少交付回执']
        elif mode == 'waiting_human':
            gaps, _ = h.human_item_gaps(root, t, required=True)
        elif mode == 'interrupted' and t['state'] not in ('interrupted','blocked'):
            gaps = ['任务中断状态不一致']
        # Bound retry across auto-continuation turns as well as duplicate events.
        gapkey = h.digest({'task': rec['task'], 'gaps': gaps}) if gaps else None
        exhausted = bool(gaps) and (event.get('stop_hook_active') is True or rec.get('retry_gap') == gapkey)
        if gaps and not exhausted:
            output = {'decision':'block','reason':'AI工程机制检查发现：' + '; '.join(gaps) + ' 仅处理原授权范围；不能自行确认人工验收。'}
            rec['retry_gap'] = gapkey
        elif gaps:
            output = {'systemMessage':'AI工程机制仍有缺口，停止自动续轮；任务未获完成认可：' + '; '.join(gaps)}
        else:
            output = {}
            rec['retry_gap'] = None
        receipt = {'event_id':uuid.uuid4().hex,'time':h.now(),'session':session,'turn':turn,
                   'task':rec['task'],'disposition':mode,'gaps':gaps,'output':output,
                   'adapter_sha256':h.digest(Path(__file__).read_bytes()),'task_sha256':h.digest(t)}
        h.write_json(h.safe(root, '.harness/codex/events/' + receipt['event_id'] + '.json'), receipt)
        h.write_json(p, rec)
        return output


def proposed_config(root):
    command = shlex.join([sys.executable, str(Path(__file__).resolve()), '--root', str(root), 'event'])
    return {'description':'AI工程机制 Stop 适配；需平台审阅信任。',
            'hooks':{'Stop':[{'hooks':[{'type':'command','command':command,'timeout':10}]}]}}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('bind','turn','unbind'):
        a=sub.add_parser(name);a.add_argument('--session',required=True)
        if name=='bind': a.add_argument('--task',required=True)
        if name=='turn':
            a.add_argument('--turn',required=True);a.add_argument('--mode',required=True);a.add_argument('--reason',required=True)
    sub.add_parser('event');sub.add_parser('config')
    a=p.parse_args();root=Path(a.root).resolve()
    try:
        h.require(root.is_dir(), '项目不存在')
        if a.command=='bind':result=bind(root,a.session,a.task)
        elif a.command=='turn':result=disposition(root,a.session,a.turn,a.mode,a.reason)
        elif a.command=='config':result=proposed_config(root)
        elif a.command=='unbind':
            with h.lock(root): binding_path(root,a.session).unlink(missing_ok=True)
            result={'unbound':True}
        else:result=handle(root,json.load(sys.stdin))
        print(json.dumps(result,ensure_ascii=False));return 0
    except (h.HarnessError, OSError, ValueError, KeyError, TypeError) as exc:
        if a.command=='event':
            # Failure is visible; never pretend the platform must block on an error.
            print(json.dumps({'systemMessage':'AI工程机制适配执行异常，保障状态未知：'+str(exc)},ensure_ascii=False));return 0
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr);return 2

if __name__=='__main__':sys.exit(main())
