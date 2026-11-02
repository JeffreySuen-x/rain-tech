"""Private one-request transport worker. Never writes diagnostics or credentials."""
import pickle
import sys
from .agent_provider import _complete_http

def main():
    try:
        config, request, media, timeout = pickle.load(sys.stdin.buffer)
        result = _complete_http(config, request, media, timeout)
        value = {'ok': True, 'result': result}
    except BaseException:
        value = {'ok': False}
    try:
        pickle.dump(value, sys.stdout.buffer)
        sys.stdout.buffer.flush()
    except BaseException:
        pass

if __name__ == '__main__':
    main()
