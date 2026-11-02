#!/usr/bin/env python3
"""Portable product quality gate: run with the configured Python 3.11+."""
from pathlib import Path
import subprocess
import sys
import os
import shutil
ROOT=Path(__file__).resolve().parents[1]
def npm_command(*arguments):
    executable=shutil.which('npm') or shutil.which('npm.cmd')
    if not executable:raise RuntimeError('npm is required')
    if sys.platform=='win32':
        cli=Path(executable).parent/'node_modules/npm/bin/npm-cli.js'
        node=shutil.which('node')
        if not cli.is_file() or not node:raise RuntimeError('Cannot locate npm JavaScript CLI')
        return [node,str(cli),*arguments]
    return [executable,*arguments]

for command in ([sys.executable,'-m','unittest','discover','-s','server/tests','-v'],[sys.executable,'-m','unittest','discover','-s','desktop/tests','-v'],[sys.executable,'-m','unittest','discover','-s','deploy/tests','-v'],npm_command('--prefix','runtime/dsh','test'),npm_command('--prefix','web','test'),npm_command('--prefix','web','run','build')):
    subprocess.run(command,cwd=ROOT,check=True)
print('GATES PASSED')
