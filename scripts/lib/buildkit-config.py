"""Reuse administrator-configured HTTPS Docker Hub mirrors in isolated BuildKit."""
import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit


def render(base: str, mirrors: list[str]) -> str:
    hosts = []
    for mirror in mirrors:
        url = urlsplit(mirror)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.query or url.fragment):
            raise ValueError('BuildKit requires credential-free HTTPS registry mirrors')
        hosts.append(url.netloc + url.path.rstrip('/'))
    if hosts:
        base += '\n[registry."docker.io"]\n  mirrors = ' + json.dumps(hosts) + '\n'
    return base


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(['docker', 'info', '--format', '{{json .RegistryConfig.Mirrors}}'],
                            capture_output=True, text=True, check=True)
    mirrors = json.loads(result.stdout) or []
    print(render((root / 'ops/buildkit/buildkitd.toml').read_text(), mirrors), end='')
