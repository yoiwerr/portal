"""Exercise deployment failure boundaries using fake Docker, never a real DB."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
FAKE = r'''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['CALL_LOG'], 'a') as out:
    out.write(json.dumps([Path(sys.argv[0]).name, *args]) + '\n')
if Path(sys.argv[0]).name == 'curl':
    sys.exit(0)
if args == ['info', '--format', '{{json .RegistryConfig.Mirrors}}']:
    print('["https://registry.example.test/"]')
if args[:2] == ['buildx', 'inspect'] and '--bootstrap' not in args and os.environ.get('NEW_BUILDER'):
    sys.exit(1)
if args[:2] == ['buildx', 'create'] and os.environ.get('CAPTURE_CONFIG'):
    Path(os.environ['CAPTURE_CONFIG']).write_text(Path(args[args.index('--buildkitd-config')+1]).read_text())
if args[:2] == ['inspect', '--format']:
    print('536870912 1073741824 100000 75000')
if 'ps' in args and args[-1] == 'postgres':
    if not os.environ.get('MISSING_DATABASE'): print('existing-postgres')
if 'build' in args and 'compose' in args:
    if os.environ.get('HOLD_BUILD'):
        Path(os.environ['HOLD_BUILD']).touch()
        deadline = time.monotonic() + 12
        while not Path(os.environ['HOLD_BUILD'] + '.release').exists():
            if time.monotonic() > deadline: sys.exit(90)
            time.sleep(.02)
    if os.environ.get('FAIL_BUILD'): sys.exit(42)
if 'up' in args and args[-1] == os.environ.get('FAIL_START'): sys.exit(43)
if args[-2:] == ['nginx', '-t'] and os.environ.get('FAIL_NGINX'): sys.exit(44)
'''


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='portal-deploy-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'scripts', self.root / 'scripts')
        shutil.copytree(ROOT / 'ops/buildkit', self.root / 'ops/buildkit')
        # Isolate certificate/environment validation; its real script is separately checked.
        check = self.root / 'scripts/check-production-config.sh'
        check.write_text('#!/bin/bash\nexit 0\n')
        check.chmod(0o755)
        (self.root / '.env').write_text('# Test-only: no real credentials\n')
        (self.root / 'bin').mkdir()
        for name in ('docker', 'curl'):
            script = self.root / 'bin' / name
            script.write_text(FAKE)
            script.chmod(0o755)
        self.log = self.root / 'calls.jsonl'
        self.env = {**os.environ, 'PATH': f"{self.root / 'bin'}:{os.environ['PATH']}",
                    'CALL_LOG': str(self.log)}

    def run_script(self, *args, **overrides):
        return subprocess.run(['bash', str(self.root / 'scripts' / args[0]), *args[1:]],
                              env={**self.env, **overrides}, capture_output=True,
                              text=True, timeout=20)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_default_updates_only_dude_without_recreating_database(self):
        result = self.run_script('update.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        builds = [c[-1] for c in calls if 'compose' in c and 'build' in c]
        self.assertEqual(builds, ['dude-admin', 'dude-api'])
        starts = [c for c in calls if 'up' in c]
        self.assertEqual([c[-1] for c in starts], ['postgres', 'dude-admin', 'dude-api', 'nginx'])
        self.assertIn('--no-recreate', starts[0])
        for c in starts[1:3]:
            self.assertIn('--no-deps', c)
            self.assertIn('--wait', c)
        self.assertFalse(any('prune' in c or 'down' in c for c in calls))
        self.assertFalse(any('--insecure' in c or '-k' in c for c in calls))

    def test_failed_build_never_starts_apps_or_switches_proxy(self):
        result = self.run_script('update.sh', FAIL_BUILD='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([c[-1] for c in self.calls() if 'up' in c], ['postgres'])
        self.assertIn(['docker', 'buildx', 'stop', 'portal-low-memory'], self.calls())
        self.assertNotIn('Update finished', result.stdout)

    def test_failed_health_does_not_switch_proxy(self):
        result = self.run_script('update.sh', '--no-build', FAIL_START='dude-api')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[-1] == 'nginx' and 'up' in c for c in self.calls()))

    def test_nginx_test_failure_preserves_running_proxy(self):
        result = self.run_script('update.sh', 'nginx', FAIL_NGINX='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[-1] == 'nginx' and 'up' in c for c in self.calls()))

    def test_missing_existing_database_stops_before_build(self):
        result = self.run_script('update.sh', MISSING_DATABASE='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any('up' in c or 'build' in c for c in self.calls()))

    def test_concurrent_entry_points_are_rejected(self):
        hold = str(self.root / 'building')
        first = subprocess.Popen(['bash', str(self.root / 'scripts/build.sh'), 'dude-api'],
                                 env={**self.env, 'HOLD_BUILD': hold},
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 6
            while not Path(hold).exists() and first.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(Path(hold).exists(), 'first build did not reach fake Docker')
            second = self.run_script('update.sh', 'journal')
            self.assertNotEqual(second.returncode, 0)
            self.assertIn('Another Portal', second.stderr)
            self.assertEqual([c[-1] for c in self.calls() if 'compose' in c and 'build' in c], ['dude-api'])
        finally:
            Path(hold + '.release').touch()
            out, err = first.communicate(timeout=8)
        self.assertEqual(first.returncode, 0, out + err)

    def test_invalid_service_does_not_invoke_docker(self):
        result = self.run_script('build.sh', 'postgres')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_new_builder_inherits_mirrors_and_applies_resource_limits(self):
        config = self.root / 'captured.toml'
        result = self.run_script('build.sh', 'dude-api', NEW_BUILDER='1', CAPTURE_CONFIG=str(config))
        self.assertEqual(result.returncode, 0, result.stderr)
        import tomllib
        actual = tomllib.loads(config.read_text())
        self.assertEqual(actual['registry']['docker.io']['mirrors'], ['registry.example.test'])
        self.assertEqual(actual['worker']['oci']['max-parallelism'], 1)
        create = next(c for c in self.calls() if c[1:3] == ['buildx', 'create'])
        for option in ('memory=512m', 'memory-swap=1g', 'cpu-quota=75000'):
            self.assertIn(option, create)


if __name__ == '__main__':
    unittest.main()
