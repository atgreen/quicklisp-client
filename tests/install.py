"""Install a fresh local dist, quickload a dependency, then reload offline."""

import argparse
import functools
import gzip
import hashlib
import http.server
import io
import json
import shutil
import subprocess
import tarfile
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
    work = Path(tempfile.mkdtemp(prefix="quicklisp-install-"))
    home = work / "home"
    home.mkdir()
    web = work / "web"
    web.mkdir()
    print(f"Quicklisp install artifacts: {work}", flush=True)
    for name in ("setup.lisp", "asdf.lisp"):
        shutil.copy2(source / name, home / name)
    shutil.copytree(source / "quicklisp", home / "quicklisp")
    requests = []

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            super().do_GET()

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Handler, directory=str(web))
    )
    url = f"http://127.0.0.1:{server.server_port}"
    releases = ["# project url size md5 sha1 prefix system-files"]
    systems = ["# project system-file system dependencies"]
    for name, dependency, code in [
        ("ql-port-dependency", None,
         '(defpackage :ql-port-dependency (:use :cl) (:export :answer))\n'
         '(in-package :ql-port-dependency)\n(defun answer () 42)\n'),
        ("ql-port-example", "ql-port-dependency",
         '(defpackage :ql-port-example (:use :cl) (:export :answer))\n'
         '(in-package :ql-port-example)\n'
         '(defun answer () (+ 1 (ql-port-dependency:answer)))\n'),
    ]:
        prefix = name + "-1"
        depends = f':depends-on ("{dependency}")' if dependency else ""
        asd = f'(asdf:defsystem "{name}" {depends} :components ((:file "code")))\n'
        tar = io.BytesIO()
        with tarfile.open(fileobj=tar, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for filename, content in [(name + ".asd", asd), ("code.lisp", code)]:
                data = content.encode()
                entry = tarfile.TarInfo(prefix + "/" + filename)
                entry.size = len(data)
                entry.mode = 0o644
                archive.addfile(entry, io.BytesIO(data))
        payload = gzip.compress(tar.getvalue(), mtime=0)
        archive_name = prefix + ".tgz"
        (web / archive_name).write_bytes(payload)
        releases.append(
            f"{name} {url}/{archive_name} {len(payload)} "
            f"{hashlib.md5(payload).hexdigest()} {hashlib.sha1(tar.getvalue()).hexdigest()} "
            f"{prefix} {name}.asd"
        )
        systems.append(f"{name} {name} {name}" + (f" {dependency}" if dependency else ""))
    for name, lines in [("releases.txt", releases), ("systems.txt", systems)]:
        (web / name).write_text("\n".join(lines) + "\n")
    (web / "distinfo.txt").write_text(
        "name: quicklisp-port-test\nversion: 1\n"
        f"system-index-url: {url}/systems.txt\n"
        f"release-index-url: {url}/releases.txt\n"
        f"archive-base-url: {url}/\n"
        f"canonical-distinfo-url: {url}/distinfo.txt\n"
        f"distinfo-subscription-url: {url}/distinfo.txt\n"
    )
    load_asdf = f"(load {json.dumps(str(args.asdf.resolve()))})\n" if args.asdf else ""
    check = (
        f"(load {json.dumps(str(home / 'setup.lisp'))})\n"
        '(assert (ql-dist:find-dist "quicklisp-port-test"))\n'
        '(ql:quickload "ql-port-example" :prompt nil)\n'
        '(assert (= (ql-port-example:answer) 43))\n'
        '(assert (ql-dist:installedp (ql-dist:find-system "ql-port-dependency")))\n'
        '(write-line "QUICKLISP-INSTALL-PASS")\n'
    )
    cold = work / "cold.lisp"
    cold.write_text(
        load_asdf
        + '(defpackage :quicklisp-quickstart (:use :cl))\n'
        + f"(defparameter quicklisp-quickstart::*quickstart-parameters* "
        + f"'(:initial-dist-url \"{url}/distinfo.txt\"))\n"
        + check
    )
    cached = work / "cached.lisp"
    cached.write_text(load_asdf + check)
    options = ["--noinform", "--no-sysinit", "--no-userinit", "--non-interactive"] if args.sbcl else ["--no-init"]

    def run(driver):
        result = subprocess.run(
            [str(args.lisp.resolve()), *options, "--load", str(driver)],
            cwd=home, timeout=300, check=False,
        )
        if result.returncode:
            raise SystemExit(result.returncode)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        run(cold)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=15)
    for path in ["/distinfo.txt", "/releases.txt", "/systems.txt",
                 "/ql-port-example-1.tgz", "/ql-port-dependency-1.tgz"]:
        assert path in requests, (path, requests)
    run(cached)
    print("QUICKLISP-OFFLINE-RELOAD-PASS", flush=True)


if __name__ == "__main__":
    main()
