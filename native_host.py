"""Chrome Native Messaging executable. stdout is protocol-only."""
import json
import os
import struct
import sys
from autofill import extension_id
from native_bridge import MAX_MESSAGE,packet,request


def main():
    import msvcrt
    msvcrt.setmode(sys.stdin.fileno(),os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(),os.O_BINARY)
    if len(sys.argv)<2 or sys.argv[1]!='chrome-extension://'+extension_id()+'/':
        return
    raw=sys.stdin.buffer.read(4)
    if len(raw)!=4:
        return
    length=struct.unpack('<I',raw)[0]
    if not 0<length<=MAX_MESSAGE:
        return
    try:
        payload=sys.stdin.buffer.read(length)
        if len(payload)!=length:
            return
        message=json.loads(payload.decode('utf-8'))
        if not isinstance(message,dict):
            return
        result=request(message)
    except Exception:
        result=dict(ok=False,error='无法连接桌面助手，请先打开院校登录助手。')
    sys.stdout.buffer.write(packet(result))
    sys.stdout.buffer.flush()


if __name__=='__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--self-test':
        import ctypes
        from autofill import Tasks
        assert ctypes.CDLL('kernel32.dll')
        print(json.dumps(Tasks().dispatch({'op': 'hello'})))
        sys.exit(0)
    main()
