import os
import sys
from app.services.execution import Executor, EXECUTION_CAPABILITIES

HELLO_APP = {
    "app/main.py": "def add(a, b):\n    return a + b\n",
    "tests/test_main.py": "import sys, os\nsys.path.insert(0, 'app')\nfrom main import add\n\ndef test_add():\n    assert add(2, 3) == 5\n\ndef test_add_negative():\n    assert add(-1, 1) == 0\n",
}

def test_run_real_tests_pass():
    r = Executor().run_tests(HELLO_APP)
    assert r.exit_code == 0, r.stderr
    assert "2 passed" in r.stdout
    assert r.duration_ms > 0
    assert not r.timed_out

def test_failing_tests_reported_honestly():
    files = dict(HELLO_APP)
    files["app/main.py"] = "def add(a, b):\n    return a - b\n"
    r = Executor().run_tests(files)
    assert r.exit_code != 0
    assert "failed" in r.stdout.lower()

def test_timeout_kills_process_group():
    files = {"loop.py": "while True:\n    pass\n"}
    r = Executor(cpu_seconds=30, wall_seconds=3).run(files, [sys.executable, "loop.py"])
    assert r.timed_out

def test_path_escape_rejected():
    try:
        Executor().run({"../evil.py": "print(1)"}, ["true"])
        assert False, "should have raised"
    except ValueError as e:
        assert "escapes" in str(e)

def test_env_is_scrubbed():
    os.environ["GM_SECRET_TEST"] = "should-not-leak"
    files = {"show.py": "import os\nprint('LEAKED' if os.environ.get('GM_SECRET_TEST') else 'CLEAN')\n"}
    r = Executor().run(files, [sys.executable, "show.py"])
    assert "CLEAN" in r.stdout
    del os.environ["GM_SECRET_TEST"]

def test_package_produces_zip_with_hash(tmp_path):
    path, digest = Executor().package(HELLO_APP, str(tmp_path / "out.zip"))
    assert os.path.exists(path)
    assert len(digest) == 64

def test_capabilities_are_honest():
    assert EXECUTION_CAPABILITIES["secure_sandbox"] is False
    assert EXECUTION_CAPABILITIES["network_blocked"] is False
