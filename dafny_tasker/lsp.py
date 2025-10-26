from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import json, os, subprocess, threading, queue, sys, uuid, time

@dataclass
class LspMessage:
    id: Optional[str]
    method: Optional[str]
    params: Any
    result: Any
    error: Any

class LspClient:
    def __init__(self, cmd: Optional[list[str]] = None, *, verbose: bool = False) -> None:
        self.verbose = verbose
        if cmd is None:
            env_cmd = os.environ.get("DAFNY_LSP_CMD")
            cmd = env_cmd.split() if env_cmd else ["dafny", "server"]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False)
        assert self.proc.stdin and self.proc.stdout
        self._in = self.proc.stdin; self._out = self.proc.stdout; self._err = self.proc.stderr
        self._rx: "queue.Queue[dict]" = queue.Queue(); self._notif: "queue.Queue[dict]" = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True); self._reader.start()

    def _read_loop(self) -> None:
        while True:
            header=b""
            while b"\r\n\r\n" not in header:
                line=self._out.readline()
                if not line: return
                header+=line
            clen=0
            for h in header.decode(errors="replace").split("\r\n"):
                if h.lower().startswith("content-length:"):
                    try: clen=int(h.split(":")[1].strip())
                    except: pass
            body=self._out.read(clen)
            if not body: return
            try: msg=json.loads(body.decode("utf-8",errors="replace"))
            except Exception as e: print("[LSP parse error]", e, file=sys.stderr); continue
            if isinstance(msg, dict) and msg.get("method") and "id" not in msg: self._notif.put(msg)
            else: self._rx.put(msg)

    def _send(self, payload: dict)->None:
        data=json.dumps(payload).encode("utf-8"); header=f"Content-Length: {len(data)}\r\n\r\n".encode("utf-8")
        self._in.write(header+data); self._in.flush()

    def request(self, method:str, params:Any, *, timeout:float=5.0)->Any:
        req_id=str(uuid.uuid4()); self._send({"jsonrpc":"2.0","id":req_id,"method":method,"params":params})
        end=time.time()+timeout
        while True:
            rem=end-time.time()
            if rem<=0: 
                tail=b""
                if self._err:
                    try: tail=self._err.read() or b""
                    except: pass
                raise TimeoutError(f"LSP request timeout: {method}\nStderr:\n"+tail.decode("utf-8",errors="replace"))
            try: msg=self._rx.get(timeout=min(0.5,rem))
            except queue.Empty: continue
            if msg.get("id")==req_id:
                if "result" in msg: return msg["result"]
                raise RuntimeError(msg.get("error"))

    def notify(self, method:str, params:Any)->None: self._send({"jsonrpc":"2.0","method":method,"params":params})
    def initialize(self, root_uri:str)->Any: return self.request("initialize", {"processId":None,"rootUri":root_uri,"capabilities":{},"trace":"off"})
    def initialized(self)->None: self.notify("initialized", {})
    def pop_notifications(self)->list[dict]:
        out=[]; 
        try:
            while True: out.append(self._notif.get_nowait())
        except: pass
        return out
    def shutdown(self)->None:
        try: self.request("shutdown", None, timeout=2.0)
        except: pass
        try: self.notify("exit", None)
        except: pass
