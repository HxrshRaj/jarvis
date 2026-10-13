import pytest

from app.tools.registry import ToolError
from app.tools.sandbox import resolve_in_workspace, validate_command


@pytest.mark.parametrize("p", ["../x", "a/../../x", "/etc/passwd", "C:\\Windows\\win.ini", ".env", "sub/.env",
                               ".ssh/id_rsa", ".git/config", "key.pem", ".env.local", "app.db", "a\x00b"])
def test_paths_refused(workspace, p):
    with pytest.raises(ToolError):
        resolve_in_workspace(workspace, p)


def test_allowed_paths(workspace):
    (workspace / "src").mkdir()
    (workspace / ".env.example").write_text("X=")
    assert resolve_in_workspace(workspace, "src").name == "src"
    assert resolve_in_workspace(workspace, ".env.example").name == ".env.example"


def test_symlink_escape_refused(workspace, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("s")
    try:
        (workspace / "link.txt").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(ToolError):
        resolve_in_workspace(workspace, "link.txt")


@pytest.mark.parametrize("argv", [["rm", "-rf", "/"], ["bash", "-c", "ls"], ["python", "-c", "print(1)"],
                                  ["git", "push"], ["pytest", "-p", "evil"], ["pytest", "--rootdir=/"],
                                  ["pytest", "../other"], ["pytest", "a;rm"], ["pytest", "$(x)"],
                                  ["npm", "install"], ["git", "diff", "--output=x"], []])
def test_commands_refused(argv):
    with pytest.raises(ToolError):
        validate_command(argv)


def test_command_approval_rules():
    assert validate_command(["git", "status"]) is False
    assert validate_command(["python", "-m", "pytest", "-q"]) is True
    assert validate_command(["npm", "test"]) is True
