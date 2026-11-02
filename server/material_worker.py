"""Private bounded document parser; no database or network credentials."""
import sys

def main():
    if sys.platform != 'win32':
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        if sys.platform.startswith('linux'):
            resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))
    from .agriculture_materials import _extract_local, _validate_extracted, MATERIAL_OUTPUT_LIMIT
    import json
    header = json.loads(sys.stdin.buffer.readline(65536))
    suffix, directory = header['suffix'], header['directory']
    if suffix not in {'.txt', '.md', '.csv', '.docx', '.pptx', '.pdf'}: raise ValueError()
    if not isinstance(directory, str): raise ValueError()
    raw = sys.stdin.buffer.read(20*1024*1024+1)
    if not raw or len(raw) > 20*1024*1024:
        raise ValueError()
    value = _validate_extracted(list(_extract_local(raw, 'material'+suffix, directory)))
    result = json.dumps(value, ensure_ascii=False).encode()
    if len(result) > MATERIAL_OUTPUT_LIMIT: raise ValueError()
    sys.stdout.buffer.write(result)
    sys.stdout.buffer.flush()

if __name__ == '__main__':
    try: main()
    except BaseException: sys.exit(1)
