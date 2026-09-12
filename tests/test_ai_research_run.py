"""Checks for experiment bookkeeping; these do not validate GPU inference."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_research import run


class ConfigTests(unittest.TestCase):
    def read(self, cfg):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps(cfg))
            return run.read_config(path)

    def test_reject_mutable_revision(self):
        cfg = run.read_config(run.DEFAULT_CONFIG)
        cfg['revision'] = 'main'
        with self.assertRaises(ValueError):
            self.read(cfg)

    def test_reject_duplicate_ids_and_invalid_limits(self):
        cfg = run.read_config(run.DEFAULT_CONFIG)
        cfg['prompts'][1]['id'] = cfg['prompts'][0]['id']
        with self.assertRaises(ValueError):
            self.read(cfg)
        for value in [True, 0, 129, 1.5]:
            cfg = run.read_config(run.DEFAULT_CONFIG)
            cfg['max_new_tokens'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.read(cfg)

    def test_no_silent_input_truncation(self):
        run.check_input_length(512, 512)
        with self.assertRaisesRegex(ValueError, 'No truncation'):
            run.check_input_length(513, 512)

    def test_eos_wins_at_token_limit(self):
        self.assertEqual(run.stop_reason([1, 2], [2], 2), 'eos')
        self.assertEqual(run.stop_reason([1, 3], [2], 2), 'max_new_tokens')
        self.assertEqual(run.stop_reason([], [2], 2), 'other')


class RecordingTests(unittest.TestCase):
    def invoke(self, folder, implementation):
        with patch('sys.argv', ['ai_research.run', '--output-root', folder]), \
             patch.object(run, 'execute', side_effect=implementation), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return run.main()

    def test_failed_run_preserves_partial_results_and_manifest(self):
        def fail(cfg, directory, manifest):
            (directory / 'results.jsonl').write_text('{"prompt_id":"first"}\n')
            raise RuntimeError('simulated inference failure')
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(self.invoke(folder, fail), 1)
            directory = next(Path(folder).iterdir())
            manifest = json.loads((directory / 'manifest.json').read_text())
            self.assertEqual(manifest['status'], 'failed')
            self.assertEqual(manifest['error']['type'], 'RuntimeError')
            self.assertTrue((directory / 'results.jsonl').exists())
            self.assertEqual((directory / 'source/run.py').read_bytes(), Path(run.__file__).read_bytes())

    def test_runs_have_distinct_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            for _ in range(2):
                self.assertEqual(self.invoke(folder, lambda *args: None), 0)
            directories = list(Path(folder).iterdir())
            self.assertEqual(len(directories), 2)
            for directory in directories:
                self.assertEqual(json.loads((directory / 'manifest.json').read_text())['status'], 'completed')

    def test_config_check_does_not_run_inference(self):
        with patch('sys.argv', ['ai_research.run', '--check-config']), patch.object(run, 'execute') as execute, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run.main(), 0)
            execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
