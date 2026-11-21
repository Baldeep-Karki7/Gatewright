# Coding Agent Harness

A small terminal coding agent. It sends your prompt to a Groq-hosted model, lets the
model call tools (read, list, write, edit, shell), and routes **every** tool call
through a permission gate that answers `allow`, `ask`, or `deny`.

The gate is deterministic and fail-closed: if the permission check crashes, the call
is refused. The model never gets to skip it.

Default mode: **`accept_edits`** — reads and edits run silently, shell commands ask.

---

## Requirements

- Python **3.9+** (the bundled venv uses 3.9.6)
- `git` on `PATH` (the harness checks for it at startup)
- A Groq API key
- Python packages: `openai`, `python-dotenv`, `pydantic`

---

## Setup after cloning

```bash
git clone <repo-url> harness
cd harness

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -U pip
pip install openai python-dotenv pydantic
```

Create a `.env` in the repo root (it is gitignored):

```dotenv
GROQ_API_KEY=your_key_here
GROQ_MODEL_NAME=openai/gpt-oss-20b
```

Both variables are required. `GROQ_MODEL_NAME` is read in `llm.py`; the API base URL
(`https://api.groq.com/openai/v1`) is set in `agent.py`.

The commands below use `./venv/bin/python`; if you activated the venv, plain
`python agent.py` is equivalent.

---

## Run

Interactive session:

```bash
./venv/bin/python agent.py
User : read the files in this repo and summarise them
```

One prompt, one turn, then exit:

```bash
./venv/bin/python agent.py "read agent.py and explain the tool loop"
```

Resume a previous session:

```bash
./venv/bin/python agent.py --continue
./venv/bin/python agent.py --resume
```

### Interactive vs batch

The harness decides interactivity with `sys.stdin.isatty()`:

- **Interactive (stdin is a terminal):** approval questions are asked in the terminal.
- **Batch (stdin is a pipe or `/dev/null`):** no `input()` is ever called; approvals
  are handled by an automatic approver (see flags below).

A positional prompt does **not** by itself make the run batch. On a terminal, this
still prompts:

```bash
./venv/bin/python agent.py "run ls"
```

To force batch:

```bash
./venv/bin/python agent.py "Call run_shell with command 'ls'." < /dev/null
```

---

## Permission modes

Select with `--mode`. The mode is fixed when the process starts.

```bash
./venv/bin/python agent.py --mode plan
./venv/bin/python agent.py --mode default "read README.md"
./venv/bin/python agent.py --mode dont_ask "list the files"
```

| Mode | `read_file`, `list_dir`, `todo_write` | `write_file`, `edit_file` | `run_shell` | Unknown tool |
|---|---|---|---|---|
| `plan` | allow | **deny** | allow only the read-only allowlist | **deny** |
| `default` | allow | ask | ask | ask |
| `accept_edits` *(default)* | allow | **allow** | ask | ask |
| `dont_ask` | allow | **deny** (ask → deny) | **deny** (ask → deny) | **deny** |
| `bypass` | allow | allow | allow | allow |

`bypass` still respects explicit deny rules. `plan` denies edits and any shell
command that is not on its read-only allowlist.

### What "ask" means

"Ask" is answered by the approver, which depends on how the process was started:

| Situation | "ask" becomes |
|---|---|
| Interactive terminal | `Allow? (y/n)` prompt; only `y`/`yes` allows |
| Batch, no flags | **denied** (`no approval available`) |
| Batch, `--yes` | allowed |
| Batch, `--allow-shell` | allowed only for `run_shell`; other asks are denied |

Consequences worth remembering:

- `--allow-shell` and `--yes` are **ignored interactively** — the terminal always asks.
- `--yes` auto-approves every ask, but **deny rules still win**, and `plan` mode still
  denies edits.
- `--allow-shell` does **not** bypass `plan` mode's shell allowlist or any deny rule.

### Plan mode shell allowlist

Only a single, plain, read-only command is allowed. The command must match one of:

```
ls, ls *
cat *, head *, tail *, wc *, grep *
git status, git status *, git diff, git diff *, git log, git log *
```

and must also satisfy all of:

- no shell syntax: `;`, `&`, `|`, backtick, `<`, `>`, newline, or `$(...)`
- no argument starting with `/` or `~`, and no argument containing `..`
- no `--output`, `--ext-diff`, or `--textconv`
- exactly one simple command (no `&&`, no pipes, no wrappers)

Example, allowed:

```bash
./venv/bin/python agent.py --mode plan \
  "Call run_shell with command 'git status'. Do not use any other tool." < /dev/null
```

Example, denied:

```bash
./venv/bin/python agent.py --mode plan \
  "Call run_shell with command 'touch x'. Do not use any other tool." < /dev/null
# error: this call was refused (plan mode only allows a short list of read-only commands)
```

Note: prompts like "run ls" are often satisfied with `list_dir` (always allowed).
To exercise the shell path, explicitly ask for `run_shell` and forbid other tools.

---

## CLI reference

```bash
./venv/bin/python agent.py --help
```

| Flag / argument | Meaning |
|---|---|
| `prompt` (positional) | Run one turn with this prompt, then exit |
| `--mode {plan,default,accept_edits,dont_ask,bypass}` | Permission mode (default `accept_edits`) |
| `--allow-shell` | Batch only: auto-approve `run_shell` asks |
| `--yes` | Batch only: auto-approve every ask |
| `--continue` | Continue the most recently active session |
| `--resume [ID]` | Pick a previous session or resume a given session id |

---

## Permission rules

Rules are supported by the policy engine, with this precedence (highest first):

1. **deny rules** — always win, and see through `&&`, `;`, `sudo`, `VAR=1`,
   and `$(...)`
2. **plan mode override** — can deny even when an allow rule matches
3. **ask rules** — an explicit ask outranks an allow
4. **allow rules** — deliberately narrow: a single plain command, whole-string match
5. **mode fallback** — the table above

Rule syntax:

```
read_file
run_shell(git push*)
write_file(.env)
write_file(docs/*)
```

Paths are normalised (`./a/../.env` matches `.env`). Shell commands are
whitespace-collapsed, and deny/ask rules also test each simple command inside a
compound string.

**Current limitation:** there is no CLI or config-file source for rules yet.
`build_gate()` creates `Policy(mode=args.mode)` with empty rule lists, so only the
mode table is active. To use rules today, construct the policy in Python, e.g.:

```python
from permissions.approver import TerminalApprover
from permissions.gate import Gate
from permissions.policy import Policy

gate = Gate(
    Policy(mode="default", deny=["run_shell(git push*)"]),
    TerminalApprover(),
)
```

Tests show the full rule behaviour (`tests/test_policy.py`).

---

## Tools the model can call

| Tool | Arguments | Permission category |
|---|---|---|
| `read_file` | `file_name` | read (always allowed) |
| `list_dir` | `path` | read (always allowed) |
| `write_file` | `file_name`, `text` | edit |
| `edit_file` | `file_name`, `old`, `new` | edit |
| `run_shell` | `command` | shell |
| `todo_write` | `todos` | internal (always allowed) |

File paths are confined to the directory the harness is started from by
`utils.safe_path()` (`realpath` + prefix check).

---

## Sessions, data, and logs

State lives under `~/.harness/projects/<dirname>-<hash>/`, where the hash is derived
from the workspace path:

```
~/.harness/projects/harness-30bd341d393b/
├── agent.log
└── ... session / event files
```

Each permission decision is logged:

```bash
grep PERMISSION ~/.harness/projects/harness-*/agent.log | tail -20
```

```
PERMISSION tool=run_shell action=ask source=user allowed=False reason=no approval available (non-interactive)
PERMISSION tool=write_file action=deny source=mode allowed=False reason=plan mode is read-only
PERMISSION tool=run_shell action=allow source=mode allowed=True reason=read-only command in plan mode
```

`source` is the quickest diagnosis:

- `mode` — the mode fallback decided (read, edit in `accept_edits`, plan rules)
- `rule` — a deny/ask/allow rule matched
- `user` — the approver answered (terminal, auto-yes, or auto-deny)
- `error` — the check crashed and the call was refused (fail-closed)

---

## Examples

```bash
# default: edits ask, shell asks (batch -> refused without a flag)
./venv/bin/python agent.py --mode default "create a file notes.txt with hello" < /dev/null

# accept_edits (default): edits run silently, shell asks
./venv/bin/python agent.py "create a file notes.txt with hello" < /dev/null

# shell refused in batch with no flags
./venv/bin/python agent.py "Call run_shell with command 'ls'. Do not use list_dir." < /dev/null

# shell auto-approved in batch for this run only
./venv/bin/python agent.py --allow-shell \
  "Call run_shell with command 'ls'. Do not use list_dir." < /dev/null

# auto-approve every ask in batch (deny rules and plan mode still apply)
./venv/bin/python agent.py --yes \
  "Call run_shell with command 'pwd'. Do not use list_dir." < /dev/null

# read-only plan mode: edits are denied
./venv/bin/python agent.py --mode plan \
  "Call write_file to create plan_check.txt with hi." < /dev/null

# dont_ask: every ask becomes a denial, nothing blocks
./venv/bin/python agent.py --mode dont_ask \
  "Call run_shell with command 'ls'. Do not use list_dir." < /dev/null

# interactive: you answer the prompt
./venv/bin/python agent.py
User : run ls
```

---

## Tests

```bash
./venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

Individual suites:

```bash
./venv/bin/python -m unittest tests.test_rules tests.test_modes tests.test_policy -v
./venv/bin/python -m unittest tests.test_gate tests.test_agent -v
```

A `RuntimeError: approver crashed` traceback during the gate tests is expected: that
test verifies the gate fails closed when the approver raises.

---

## Security model (read this)

The permission layer is a **deterministic approval gate, not a sandbox.**

- `run_shell` uses `subprocess.run(..., shell=True)`. Once approved, a command can do
  anything the current user can do, including `cd /` out of the workspace.
- File tools are confined by `utils.safe_path()`, but that is a best-effort check
  (`realpath` + prefix), not a kernel sandbox. There is a small TOCTOU window between
  the path check and the file open.
- Rule matching is textual and biased toward over-matching. Known gaps:
  - `bash -c "git push"` and `sh -c 'git push'` are not seen as `git push`
  - `env -i git push` is not seen as `git push`
  - `git -C . push` is a different spelling of `git push`
  - plan mode does not reject environment expansion such as `cat $HOME/secret`
  - `fnmatch`'s `*` matches `/`, so `docs/*` also covers `docs/a/b.md`
- A deny rule is a speed bump, not a guarantee. The approver is the real control for
  shell commands. Do not run `--yes` or `bypass` against untrusted prompts.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'openai'`**
You are using the system Python. Use `./venv/bin/python` or activate the venv.

**`KeyError: 'GROQ_API_KEY'`**
No `.env` in the repo root (or the variable is missing). Recreate it as shown above.

**`NameError: name 'set_shell_policy' is not defined`**
Stale code from before the gate became the single owner of shell approvals. Remove
the `set_shell_policy(...)` calls in `agent.py`; the gate owns this now.

**`AttributeError: 'Namespace' object has no attribute 'mode'`**
`parseArgs.py` is missing the `--mode` argument. Add it (see CLI reference above).

**"run ls" showed a directory listing but never prompted**
The model used `list_dir` (a read tool), not `run_shell`. Ask explicitly:
`"Call run_shell with command 'ls'. Do not use list_dir."`.

**A batch run says the user denied a call, but nobody was asked**
That is the unattended approver refusing because no approval was possible. Use
`--allow-shell` (shell only) or `--yes` (all asks) if that is intended.

**`--allow-shell` seems to do nothing interactively**
By design: interactive runs always use the terminal approver. The flag only affects
batch runs.
