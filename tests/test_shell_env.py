import os
from utils import run_shell, shell_env

FAKE_KEY = "gsk-FAKE_TEST_KEY"


def test_shell_cannot_see_api_keys(monkeypatch):
    #arrange, input
    monkeypatch.setenv("GROQ_API_KEY", FAKE_KEY)

    #ACT, ask the shell to print it's whole environment
    result = run_shell("env")

    assert result.startswith("exit=0")
    assert FAKE_KEY not in result
    assert "GROQ_API_KEY" not in result


def test_normal_command_still_work():
    #Arrange
    commands = ["git --version", "python3 --version", "ls"]
    
    #Act
    for command in commands:
        result = run_shell(command)
        
        #Assert
        assert result.startswith("exit=0")
        assert result.strip()[-7:] == "stderr:"

def test_harness_keeps_its_own_keys(monkeypatch):
    #Arrange set the fake key
    monkeypatch.setenv("GROQ_API_KEY", FAKE_KEY)

    #Act:
    result = run_shell("ls")

    #assert
    print(result)
    assert os.environ["GROQ_API_KEY"] == FAKE_KEY


def test_missing_path_gets_a_default(monkeypatch):
    # Arrange: the harness itself has no PATH
    monkeypatch.delenv("PATH", raising=False)

    # Act
    env = shell_env()

    # Assert: shell commands still get a standard PATH
    assert env["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"

