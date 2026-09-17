#!/usr/bin/env python3
"""Run real unittest discovery and write the harness count protocol."""
import argparse
import json
import os
from pathlib import Path
import sys
import unittest
import uuid

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start', default='tests', help='测试目录，相对目标项目 cwd')
    p.add_argument('--pattern', default='test_*.py')
    p.add_argument('--report', help='独立运行时可指定报告位置；verify 注入的位置优先')
    a = p.parse_args()
    sys.path.insert(0, str(Path.cwd()))
    counts = {'total':0, 'failed':0, 'errors':0, 'skipped':0}
    try:
        suite = unittest.defaultTestLoader.discover(a.start, pattern=a.pattern)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        counts.update(total=result.testsRun, failed=len(result.failures), errors=len(result.errors), skipped=len(result.skipped))
    except (ImportError, OSError) as exc:
        print(f'无法发现测试: {exc}', file=sys.stderr)
        counts.update(total=1, errors=1)
    report = Path(os.environ.get('AI_PROJECT_HARNESS_REPORT') or a.report or f'.harness/reports/{uuid.uuid4().hex}.json')
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(counts, indent=2)+'\n')
    print(json.dumps({'report':str(report), **counts}))
    return 0 if counts['total'] > 0 and not any(counts[k] for k in ('failed','errors','skipped')) else 1

if __name__=='__main__':
    sys.exit(main())
