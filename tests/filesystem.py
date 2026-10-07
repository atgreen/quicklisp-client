"""Check Quicklisp directory enumeration through the implementation interface."""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lisp", type=Path)
    parser.add_argument("--asdf", type=Path)
    parser.add_argument("--sbcl", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent.parent
    work = Path(tempfile.mkdtemp(prefix="quicklisp-filesystem-"))
    print(f"Quicklisp filesystem artifacts: {work}", flush=True)
    for name in ("setup.lisp", "asdf.lisp"):
        shutil.copy2(source / name, work / name)
    shutil.copytree(source / "quicklisp", work / "quicklisp")
    (work / "dists").mkdir()
    fixture = work / "fixture"
    (fixture / "child").mkdir(parents=True)
    (fixture / "empty").mkdir()
    for name in ("plain", "example.asd", ".hidden", "child/nested.asd"):
        (fixture / name).write_text("fixture")
    expected = sorted(str(fixture / name) for name in
                      ("plain", "example.asd", ".hidden", "child/", "empty/"))
    expected = [name + "/" if Path(name).is_dir() else name for name in expected]
    load_asdf = f"(load {json.dumps(str(args.asdf.resolve()))})\n" if args.asdf else ""
    driver = work / "filesystem-driver.lisp"
    driver.write_text(
        load_asdf
        + f"(load {json.dumps(str(work / 'setup.lisp'))})\n"
        + f"(defparameter *fixture* #P{json.dumps(str(fixture) + '/')})\n"
        + "(let ((entries (ql-impl-util:directory-entries *fixture*)))\n"
        + '  (format t "~&DIRECTORY-ENTRIES ~S~%" (sort (mapcar #\'namestring entries) #\'string<))\n'
        + f"  (assert (equal (sort (mapcar #'namestring entries) #'string<) '({' '.join(json.dumps(name) for name in expected)})))\n"
        + "  (assert (= 2 (count-if #'ql-impl-util::directoryp entries))))\n"
        + '(assert (null (ql-impl-util:directory-entries (merge-pathnames "empty/" *fixture*))))\n'
        + '(write-line "QUICKLISP-FILESYSTEM-PASS")\n',
        encoding="utf-8",
    )
    options = ["--noinform", "--no-sysinit", "--no-userinit", "--non-interactive"] if args.sbcl else ["--no-init"]
    result = subprocess.run(
        [str(args.lisp.resolve()), *options, "--load", str(driver)],
        cwd=work, timeout=300, check=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
