from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_mcs_aind_batch import key_for, refresh, submit, worker, write_json


class McsBatchTests(unittest.TestCase):
    def make_plan(self, root):
        ids = ['group/condition/one', 'group/condition/two', 'group/condition/missing']
        rows = [{'recording_id': value, 'key': key_for(value), 'status': 'prepared' if i < 2 else 'blocked',
                 'stage': 'ready' if i < 2 else 'preflight', 'reason': '' if i < 2 else 'Missing acquisition geometry',
                 **({'task_index': i} if i < 2 else {})} for i, value in enumerate(ids)]
        plan = {'records': rows, 'tasks': [r['key'] for r in rows[:2]], 'concurrency': 2, 'code_root': str(root / 'code')}
        write_json(root / 'batch_manifest.json', plan)
        return plan

    def test_ledger_keeps_blocked_rows_and_combines_per_recording_state(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            plan = self.make_plan(root)
            write_json(root / 'submission.json', {'job_id': '12345'})
            write_json(root / 'status' / f"{plan['tasks'][0]}.json",
                       {'status': 'completed', 'stage': 'complete', 'deleted_bytes': 1024, 'h5_cleanup_status': 'deleted'})
            summary = refresh(root)
            self.assertEqual(summary['statuses'], {'completed': 1, 'submitted': 1, 'blocked': 1})
            self.assertEqual(summary['deleted_h5_bytes'], 1024)
            with (root / 'recordings.csv').open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[2]['reason'], 'Missing acquisition geometry')

    def test_submit_is_bounded_and_refuses_duplicates_or_ambiguous_retry(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            self.make_plan(root)
            with patch('run_mcs_aind_batch.subprocess.run') as run:
                run.return_value.stdout = '12345;cluster\n'
                submit(root)
                self.assertIn('--array=0-1%2', run.call_args_list[0].args[0])
                self.assertIn('--dependency=afterany:12345', run.call_args_list[1].args[0])
                with self.assertRaises(FileExistsError):
                    submit(root)
                self.assertEqual(run.call_count, 2)
            (root / 'submission.json').unlink()
            with self.assertRaises(FileExistsError):
                submit(root)

    def test_scheduler_timeout_is_not_left_running(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            plan = self.make_plan(root)
            write_json(root / 'submission.json', {'job_id': '12345'})
            write_json(root / 'status' / f"{plan['tasks'][0]}.json", {'status': 'running', 'stage': 'pipeline'})
            with patch('run_mcs_aind_batch.subprocess.run') as run:
                run.return_value.stdout = '12345_0|TIMEOUT|0:0|\n12345_1|PENDING|0:0|\n'
                summary = refresh(root, scheduler=True)
            self.assertEqual(summary['statuses'], {'failed': 1, 'submitted': 1, 'blocked': 1})

    def test_worker_rejects_out_of_range_before_any_processing(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            self.make_plan(root)
            with patch('run_mcs_aind_batch.subprocess.run') as run:
                with self.assertRaises(ValueError):
                    worker(root, -1)
                with self.assertRaises(ValueError):
                    worker(root, 2)
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
