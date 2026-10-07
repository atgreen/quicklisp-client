"""Exercise the real Quicklisp connection protocol with a loopback peer."""

import argparse
import json
import shutil
import socket
import socketserver
import subprocess
import tempfile
import threading
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lisp", type=Path)
    parser.add_argument("--asdf", type=Path)
    parser.add_argument("--sbcl", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent.parent
    work = Path(tempfile.mkdtemp(prefix="quicklisp-network-"))
    print(f"Quicklisp network artifacts: {work}", flush=True)
    for name in ("setup.lisp", "asdf.lisp"):
        shutil.copy2(source / name, work / name)
    shutil.copytree(source / "quicklisp", work / "quicklisp")
    # This is a network contract test, not a distribution installation test.
    (work / "dists").mkdir()
    completed = []
    failures = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                self.request.settimeout(10)
                mode = self.request.recv(1)
                if mode == b"\x00":
                    payload = b""
                    while len(payload) < 5:
                        part = self.request.recv(5 - len(payload))
                        if not part:
                            raise AssertionError("Client closed before sending all octets")
                        payload += part
                    assert payload == bytes((0, 1, 127, 128, 255)), payload
                    self.request.sendall(payload)
                elif mode == b"\x01":
                    assert self.request.recv(1) == b"", "Callback failure leaked the connection"
                else:
                    raise AssertionError(f"Unexpected connection mode {mode!r}")
                completed.append(mode)
            except Exception as error:
                failures.append(repr(error))

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server, socket.socket() as refused:
        refused.bind(("127.0.0.1", 0))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        load_asdf = f"(load {json.dumps(str(args.asdf.resolve()))})" if args.asdf else ""
        driver = work / "network-driver.lisp"
        driver.write_text(
            load_asdf + "\n"
            + f"(load {json.dumps(str(work / 'setup.lisp'))})\n"
            + f"(defparameter *test-port* {server.server_address[1]})\n"
            + f"(defparameter *refused-port* {refused.getsockname()[1]})\n"
            + f"(load {json.dumps(str(source / 'tests/network.lisp'))})\n",
            encoding="utf-8",
        )
        options = ["--noinform", "--no-sysinit", "--no-userinit", "--non-interactive"] if args.sbcl else ["--no-init"]
        try:
            result = subprocess.run(
                [str(args.lisp.resolve()), *options, "--load", str(driver)],
                cwd=work, timeout=300, check=False,
            )
        finally:
            server.shutdown()
            thread.join(timeout=15)
        if result.returncode:
            raise SystemExit(result.returncode)
    assert not failures, failures
    assert sorted(completed) == [b"\x00", b"\x01"], completed
    print("QUICKLISP-NETWORK-SERVER-PASS", flush=True)


if __name__ == "__main__":
    main()
