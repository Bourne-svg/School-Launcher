"""Length-framed local IPC restricted to the current Windows SID."""
import json
import struct
import threading
import win32api
import win32con
import win32file
import win32pipe
import win32security
import pywintypes

MAX_MESSAGE = 65536


def user_sid():
    token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY)
    try:
        return win32security.GetTokenInformation(token,win32security.TokenUser)[0]
    finally:
        token.Close()


def pipe_name():
    return r'\\.\pipe\SchoolLauncher.Autofill.' + win32security.ConvertSidToStringSid(user_sid())


def packet(value):
    data=json.dumps(value,ensure_ascii=False).encode('utf-8')
    if len(data)>MAX_MESSAGE:
        raise ValueError('Message too large')
    return struct.pack('<I',len(data))+data


def read_exact(handle, size):
    result=b''
    while len(result)<size:
        part=win32file.ReadFile(handle,size-len(result))[1]
        if not part:
            raise EOFError()
        result+=part
    return result


def receive(handle):
    size=struct.unpack('<I',read_exact(handle,4))[0]
    if not 0<size<=MAX_MESSAGE:
        raise ValueError('Invalid message length')
    value=json.loads(read_exact(handle,size).decode('utf-8'))
    if not isinstance(value,dict):
        raise ValueError('Invalid message')
    return value


def request(message):
    win32pipe.WaitNamedPipe(pipe_name(),3000)
    handle=win32file.CreateFile(pipe_name(),win32con.GENERIC_READ|win32con.GENERIC_WRITE,0,None,win32con.OPEN_EXISTING,0,None)
    try:
        win32file.WriteFile(handle,packet(message))
        return receive(handle)
    finally:
        handle.Close()


class Server:
    def __init__(self,dispatch):
        self.dispatch=dispatch
        self.ready=threading.Event()
        self.error=None

    def start(self):
        threading.Thread(target=self.run,daemon=True).start()
        self.ready.wait(3)

    def run(self):
        try:
            sid=win32security.ConvertSidToStringSid(user_sid())
            descriptor=win32security.ConvertStringSecurityDescriptorToSecurityDescriptor('D:P(A;;GA;;;'+sid+')',1)
            attributes=pywintypes.SECURITY_ATTRIBUTES()
            attributes.SECURITY_DESCRIPTOR=descriptor
            first=True
            while True:
                access=win32pipe.PIPE_ACCESS_DUPLEX | (0x00080000 if first else 0)
                handle=win32pipe.CreateNamedPipe(pipe_name(),access,win32pipe.PIPE_TYPE_BYTE|win32pipe.PIPE_READMODE_BYTE|win32pipe.PIPE_WAIT|0x8,16,MAX_MESSAGE,MAX_MESSAGE,3000,attributes)
                first=False
                self.ready.set()
                try:
                    win32pipe.ConnectNamedPipe(handle,None)
                except pywintypes.error as error:
                    if error.winerror!=535:
                        handle.Close()
                        raise
                threading.Thread(target=self.serve,args=(handle,),daemon=True).start()
        except Exception:
            self.error='本机浏览器连接服务未启动，请退出重复进程后重试。'
            self.ready.set()

    def serve(self,handle):
        try:
            data=receive(handle)
            result=self.dispatch(data)
            win32file.WriteFile(handle,packet(result))
            win32file.FlushFileBuffers(handle)
        except Exception:
            pass
        finally:
            try:
                win32pipe.DisconnectNamedPipe(handle)
            except Exception:
                pass
            handle.Close()
