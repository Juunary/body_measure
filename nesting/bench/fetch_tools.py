"""Fetch the open-source nesters at pinned versions into .bench/tools (gitignored).

    python -m bench.fetch_tools            # everything
    python -m bench.fetch_tools svgnest    # one tool: svgnest | deepnest | sparrow

SVGnest and sparrow come from their GitHub repositories at fixed commits;
Deepnest is the official deepnest-next Windows release. sparrow is built from
source with a Rust toolchain installed locally under .bench/rust (no PATH or
profile changes). Windows x64 only, like the rest of this study's scripts.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / '.bench'
TOOLS = BENCH / 'tools'
RUST = BENCH / 'rust'

SVGNEST = {'repo': 'https://github.com/Jack000/SVGnest.git', 'commit': '1248dc21efd3'}
SPARROW = {'repo': 'https://github.com/JeroenGar/sparrow.git', 'tag': 'v0.2.0', 'commit': 'ed1c72c'}
DEEPNEST = {'version': 'v1.5.6', 'asset': 'deepnest-v1.5.6-win32-x64_signed.zip', 'size': 122017540,
            'sha256': '2ebc18d41d5b951cc6789e9dbc913de509cb28db2254611f127eaaaef3aead44',
            'url': 'https://github.com/deepnest-next/deepnest/releases/download/v1.5.6/deepnest-v1.5.6-win32-x64_signed.zip'}
RUSTUP_INIT = 'https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe'


def run(cmd, cwd=None, env=None):
    print('>', ' '.join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, check=True)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def download(url, dest, size=None, sha256=None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not (dest.is_file() and (size is None or dest.stat().st_size == size)):
        print(f'downloading {url}', flush=True)
        tmp = dest.with_suffix(dest.suffix + '.part')
        urllib.request.urlretrieve(url, tmp)
        if size is not None and tmp.stat().st_size != size:
            raise RuntimeError(f'{dest.name}: expected {size} bytes, got {tmp.stat().st_size}')
        tmp.replace(dest)
    if sha256 is not None and _sha256(dest) != sha256:
        raise RuntimeError(f'{dest.name}: SHA-256 mismatch')
    return dest


def git_checkout(repo, dest, commit=None, tag=None):
    if not (dest / '.git').is_dir():
        run(['git', 'clone', '--quiet', repo, dest])
    run(['git', '-C', dest, 'fetch', '--quiet', '--tags'])
    run(['git', '-C', dest, 'checkout', '--quiet', tag or commit])
    head = subprocess.run(['git', '-C', str(dest), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    if commit and not head.startswith(commit):
        raise RuntimeError(f'{dest.name}: HEAD {head} is not the pinned {commit}')
    return head


def fetch_svgnest():
    return git_checkout(SVGNEST['repo'], TOOLS / 'SVGnest', commit=SVGNEST['commit'])


def fetch_deepnest():
    archive = download(DEEPNEST['url'], BENCH / 'downloads' / DEEPNEST['asset'], DEEPNEST['size'], DEEPNEST['sha256'])
    target = TOOLS / 'deepnest'
    exe = next(target.rglob('deepnest.exe'), None) if target.is_dir() else None
    if exe is None:
        if target.is_dir():
            shutil.rmtree(target)
        with zipfile.ZipFile(archive) as z:
            z.extractall(target)
        exe = next(target.rglob('deepnest.exe'))
    print('deepnest executable:', exe)
    return exe


def rust_env():
    env = dict(os.environ)
    env['RUSTUP_HOME'] = str(RUST / 'rustup')
    env['CARGO_HOME'] = str(RUST / 'cargo')
    env['PATH'] = str(RUST / 'cargo' / 'bin') + os.pathsep + env['PATH']
    return env


def fetch_sparrow():
    env = rust_env()
    cargo = RUST / 'cargo' / 'bin' / 'cargo.exe'
    if not cargo.is_file():
        init = download(RUSTUP_INIT, BENCH / 'downloads' / 'rustup-init.exe')
        run([init, '-y', '--no-modify-path', '--profile', 'minimal', '--default-toolchain', 'stable',
             '--default-host', 'x86_64-pc-windows-msvc'], env=env)
    run([cargo, '--version'], env=env)
    src = TOOLS / 'sparrow'
    head = git_checkout(SPARROW['repo'], src, commit=SPARROW['commit'], tag=SPARROW['tag'])
    env['RUSTFLAGS'] = '-C target-cpu=native'
    run([cargo, 'build', '--release', '--features=only_final_svg'], cwd=src, env=env)
    exe = src / 'target' / 'release' / 'sparrow.exe'
    print('sparrow executable:', exe, 'at', head)
    return exe


def main(argv):
    wanted = argv or ['svgnest', 'deepnest', 'sparrow']
    for name in wanted:
        {'svgnest': fetch_svgnest, 'deepnest': fetch_deepnest, 'sparrow': fetch_sparrow}[name]()
    print('done:', ', '.join(wanted))


if __name__ == '__main__':
    main(sys.argv[1:])
