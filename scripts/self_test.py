#!/usr/bin/env python3
"""Portable APH lifecycle smoke tests. Only temporary fixture projects are used.

Run with the same Python 3.10+ interpreter used for harness.py. Reports real
unittest counts to stdout and, when set, AI_PROJECT_HARNESS_REPORT. This does not
test a consumer project's adapters, product behavior, or platform hooks.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HARNESS = Path(__file__).resolve().with_name('harness.py')


class MechanismTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='aph-self-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in ('AGENTS.md', 'TESTING.md', 'requirements.md', 'status.md'):
            (self.root/name).write_text('# Isolated fixture\nActual fixture rules.\n')
        (self.root/'README.md').write_text('\n'.join(f'[{p}]({p})' for p in ('AGENTS.md', 'TESTING.md', 'requirements.md', 'status.md')))
        (self.root/'input.txt').write_text('initial')
        self.check_code = ('import os,json\nfrom pathlib import Path\n'
                           'assert Path("input.txt").read_text()\n'
                           'Path(os.environ["AI_PROJECT_HARNESS_REPORT"]).write_text(json.dumps(dict(total=1,failed=0,errors=0,skipped=0)))\n')
        (self.root/'check.py').write_text(self.check_code)
        self.mapping = {'authorities':{'entrypoint':'README.md', 'agent_policy':'AGENTS.md', 'requirements':'requirements.md', 'validation':'TESTING.md', 'status':'status.md'},
                        'confirmation_source':'Isolated self-test fixture authorization',
                        'checks':{'fixture':{'purpose':'Verify fixture evidence handling', 'argv':[sys.executable, 'check.py'], 'kind':'tests', 'inputs':['input.txt', 'check.py'], 'timeout':2}}}
        self.save('mapping.json', self.mapping)
        self.call('adopt', '--mapping', 'mapping.json', '--apply')
        self.spec = {'id':'TASK-001', 'goal':'Verify isolated lifecycle', 'scope':'Temporary fixture only', 'authorization':'Self-test invocation', 'next_action':'Run fixture and inspect evidence',
                     'acceptance':[{'id':'AC-01', 'text':'Fixture evidence is current', 'checks':['fixture'], 'human_required':False}],
                     'document_sync':{'reviewed':True, 'no_change_reason':'Fixture rules unchanged', 'items':[]}}

    def save(self, name, value):
        (self.root/name).write_text(json.dumps(value))

    def call(self, *args, expected=0):
        proc = subprocess.run([sys.executable, '-B', str(HARNESS), '--root', str(self.root), *args],
                              cwd=self.root, capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
        return json.loads(proc.stdout or proc.stderr)

    def begin(self):
        self.save('task.json', self.spec)
        self.call('begin', '--spec', 'task.json')

    def assess(self):
        return self.call('resume', 'TASK-001')['assessment']

    def verify(self, expected=0):
        return self.call('verify', 'TASK-001', 'fixture', expected=expected)

    def test_success_resume_and_unrelated_change(self):
        self.begin(); self.verify()
        self.assertTrue(self.assess()['conditions_met'])
        self.call('pause', 'TASK-001', '--next', 'Inspect state before continuing')
        before = {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.call('resume', 'TASK-001')['task']['state'], 'interrupted')
        self.assertEqual(before, {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.call('resume', 'TASK-001', '--activate')
        (self.root/'unrelated.txt').write_text('unrelated')
        self.assertTrue(self.assess()['conditions_met'])
        (self.root/'review.md').write_text('Synthetic fixture review; not human acceptance.')
        self.assertEqual(self.call('close', 'TASK-001', '--complete', '--review-source', 'review.md')['task_state'], 'completed')

    def test_missing_acceptance_rejected(self):
        self.spec['acceptance'] = []; self.save('task.json', self.spec)
        self.call('begin', '--spec', 'task.json', expected=2)

    def test_missing_run_blocks(self):
        self.begin(); self.assertFalse(self.assess()['conditions_met'])

    def test_latest_failure_blocks_old_success(self):
        self.begin(); self.verify()
        (self.root/'check.py').write_text('raise SystemExit(1)\n')
        self.verify(expected=1)
        (self.root/'check.py').write_text(self.check_code)
        self.assertFalse(self.assess()['conditions_met'])

    def test_skipped_zero_missing_and_invalid_report_block(self):
        self.begin()
        for report in ({'total':1, 'failed':0, 'errors':0, 'skipped':1}, {'total':2, 'failed':0, 'errors':0, 'skipped':1}, {'total':0, 'failed':0, 'errors':0, 'skipped':0}, None, []):
            with self.subTest(report=report):
                code = 'pass\n' if report is None else 'import os\nfrom pathlib import Path\nPath(os.environ["AI_PROJECT_HARNESS_REPORT"]).write_text(' + repr(json.dumps(report)) + ')\n'
                (self.root/'check.py').write_text(code)
                self.verify(expected=1); self.assertFalse(self.assess()['conditions_met'])

    def test_corrupt_log_and_receipt_block(self):
        self.begin(); run = self.verify()
        (self.root/run['run']/'output.log').write_text('corrupted')
        self.assertFalse(self.assess()['conditions_met'])
        (self.root/run['run']/'summary.json').write_text('{}')
        self.assertFalse(self.assess()['conditions_met'])

    def test_related_change_blocks(self):
        self.begin(); self.verify(); (self.root/'input.txt').write_text('changed')
        self.assertFalse(self.assess()['conditions_met'])

    def test_during_run_change_blocks(self):
        (self.root/'check.py').write_text(self.check_code + 'Path("input.txt").write_text("changed during execution")\n')
        self.begin(); self.verify(expected=1)
        self.assertFalse(self.assess()['conditions_met'])

    def test_timeout_blocks(self):
        (self.root/'check.py').write_text('import time\ntime.sleep(10)\n')
        self.begin(); result = self.verify(expected=1)
        self.assertEqual(result['overall_status'], 'interrupted')
        self.assertFalse(self.assess()['conditions_met'])


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MechanismTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'total':result.testsRun, 'failed':len(result.failures) + len(result.unexpectedSuccesses), 'errors':len(result.errors), 'skipped':len(result.skipped)}
    target = os.environ.get('AI_PROJECT_HARNESS_REPORT')
    if target:
        path = Path(target); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report) + '\n')
    print(json.dumps(report))
    return 0 if result.wasSuccessful() and report['total'] and not report['skipped'] else 1


if __name__ == '__main__':
    sys.exit(main())
