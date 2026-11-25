# Coding Agent Harness

[![tests](https://github.com/Baldeep-Karki7/Gatewright/actions/workflows/tests.yml/badge.svg)](https://github.com/Baldeep-Karki7/Gatewright/actions/workflows/tests.yml)

A small terminal coding agent. It sends your prompt to a Groq-hosted model, lets the
model call tools (read, list, write, edit, shell), and routes **every** tool call
through a permission gate that answers `allow`, `ask`, or `deny`.

The gate is deterministic and fail-closed: if the permission check crashes, the call
is refused. The model never gets to skip it.

Default mode: **`accept_edits`**: reads and edits run silently, shell commands ask.

> **Status: work in progress.** Built as a learning project and being hardened step by
> step toward production quality. CLI flags, permission semantics and file formats may
> still change between commits. Every bug found and fixed along the way is recorded in
> [`FIXLOG.md`](FIXLOG.md).

---

## Requirements

- Python **3.12+** (CI tests 3.12 and 3.13)
- `git` on `PATH` (the harness checks for it at startup)
- A Groq API key
- Python packages: pinned in `requirements.txt` (`openai`, `pydantic`, `python-dotenv`,
  `httpx`); test tools in `requirements-dev.txt` (`pytest`)

---

## Setup after cloning

```bash
git clone https://github.com/Baldeep-Karki7/Gatewright.git harness
cd harness

python3.12 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
pip install -r requirements-dev.txt   # only needed to run the tests
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

## Configuration

Optional settings. Put them in `.env`, or set them for one run
(`HARNESS_CONTEXT_BUDGET=4000 ./venv/bin/python agent.py`). A value set in the shell
wins over `.env`. Invalid values (e.g. `16k`) stop the harness at startup with a clear
message; values below the minimum are raised to it.

| Variable | Default | Minimum | What it controls |
|---|---|---|---|
| `HARNESS_READ_MAX_CHARS` | `16000` | `1000` | Max characters one `read_file` call returns (~4–5k tokens) |
| `HARNESS_CONTEXT_BUDGET` | `6000` | `2000` | Max estimated tokens sent per API request |
| `HARNESS_LOG_MAX_BYTES` | `5242880` (5 MiB) | `10240` | Size at which `agent.log` is rotated |
| `HARNESS_LOG_BACKUPS` | `3` | `1` | Rotated log files kept (`agent.log.1` … `.N`) |

The defaults fit Groq's on-demand tier, which allows **8,000 tokens per minute**: a
single request larger than that is rejected outright (HTTP 413). Raise
`HARNESS_CONTEXT_BUDGET` and `HARNESS_READ_MAX_CHARS` if your tier allows more.

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

The workspace is the directory you start the harness from. The harness runs `git init`
there if it is not already its own repository.

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

## Tool profiles

A profile decides which tools the model is **offered** at all. Select it with
`--profile`:

| Profile | Tools offered |
|---|---|
| `development` *(default)* | `read_file`, `list_dir`, `write_file`, `edit_file`, `run_shell`, `todo_write` |
| `readonly` | `read_file`, `list_dir` |

Profiles and permission modes are two separate layers. The profile removes tools from
the model's tool list; a call to a tool outside the profile is refused before it
reaches the gate. The permission mode then decides what happens to calls that are
offered.

```bash
./venv/bin/python agent.py --profile readonly "summarise this repo"
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

- `--allow-shell` and `--yes` are **ignored interactively**: the terminal always asks.
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
| `--profile {development,readonly}` | Which tools the model is offered (default `development`) |
| `--allow-shell` | Batch only: auto-approve `run_shell` asks |
| `--yes` | Batch only: auto-approve every ask |
| `--continue` | Continue the most recently active session |
| `--resume [ID]` | Pick a previous session or resume a given session id |

---

## Permission rules

Rules are supported by the policy engine, with this precedence (highest first):

1. **deny rules**: always win, and see through `&&`, `;`, `sudo`, `VAR=1`,
   and `$(...)`
2. **plan mode override**: can deny even when an allow rule matches
3. **ask rules**: an explicit ask outranks an allow
4. **allow rules**: deliberately narrow: a single plain command, whole-string match
5. **mode fallback**: the table above

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
| `read_file` | `file_name`, optional `offset`, `limit` | read (always allowed) |
| `list_dir` | `path` | read (always allowed) |
| `write_file` | `file_name`, `text` | edit |
| `edit_file` | `file_name`, `old`, `new` | edit |
| `run_shell` | `command` | shell |
| `todo_write` | `todos` | internal (always allowed) |

File paths are confined to the directory the harness is started from by
`utils.safe_path()` (`realpath` + prefix check).

**`read_file` is paged.** One call returns at most 2,000 lines and at most
`HARNESS_READ_MAX_CHARS` characters; lines longer than 2,000 characters (minified files)
are cut. Text is returned exactly as stored, so it can be copied into `edit_file`. When
anything was left out the result ends with a note such as
`[truncated: showing lines 1-1710 of 5000. Call read_file again with offset=1711 to see more]`.

**`run_shell`** runs with a 30-second timeout and output capped at 5,000 characters per
stream. Commands get a **minimal environment** (`PATH`, `HOME`, `USER`, `LANG`,
`LC_ALL`, `TERM`, `TMPDIR`, `SHELL`), so API keys loaded from `.env` are not visible to
them. A command that needs another variable will not see it; add it to
`SHELL_ENV_KEYS` in `utils.py` deliberately.

---

## Context and request size

Before **every** API call the harness fits the conversation into
`HARNESS_CONTEXT_BUDGET` (`context.py`):

1. The system prompt is always sent.
2. The oldest whole turns are dropped first (a turn = one user message up to the next),
   so an assistant tool call and its tool results are never separated.
3. If the current turn alone is still too big, older tool outputs inside it are replaced
   with `[old tool output removed to save space; call the tool again if you need it]`;
   the newest one is kept.
4. If it still does not fit, the turn is aborted before anything is sent.

Only the copy that is **sent** is trimmed: the in-memory history and the session
transcript stay complete. Tokens are estimated as characters ÷ 3, which errs on the
safe side; `agent.log` records the estimate next to the provider's real count
(`MODEL call: estimated = … prompt_tokens = …`) so it can be calibrated.

API errors are handled by kind:

| Error | Meaning | What the harness does |
|---|---|---|
| 413 (tokens) | One request is larger than the per-minute token limit | Aborts the turn with a clear message; no retry |
| 400 context length | Larger than the model's context window | Aborts the turn with a clear message; no retry |
| 400 other | The model produced a bad tool call | Tells the model why and lets it retry (up to 20 steps) |
| 429 | Per-minute budget used up | The SDK waits as long as the provider says and retries (4 times) |
| 401 / network | Bad key, or no connection | Aborts the turn with a clear message |

An aborted turn is rolled back: its messages are removed from the conversation and a
`turn_aborted` event is written, so the next message starts from a clean state.

---

## Sessions, data, and logs

State lives under `~/.harness/projects/<dirname>-<hash>/`, where the hash is derived
from the workspace path:

```
~/.harness/projects/harness-30bd341d393b/
├── sessions.json                 list of sessions (titles, update times)
├── sessions/<session-id>.jsonl   transcript: one file per session
└── agent.log                     diagnostic log, shared by all sessions in this workspace
    agent.log.1 … agent.log.3     older parts after rotation
```

**The transcript** (`sessions/<id>.jsonl`) holds every message, tool call and tool
result. Resume and replay are rebuilt from it. Each event has a UTC ISO 8601
`timestamp` and a `schema_version`.

**The diagnostic log** (`agent.log`) records what happened and how it went, never the
data itself:

```
2026-11-25T11:59:18.984Z INFO session=9406fa4f-… turn=482ec1f0-… llm TOOL name=read_file call_id=call_g88q ok=True result_chars=3088 ms=1
2026-11-25T11:59:18.990Z INFO session=9406fa4f-… turn=482ec1f0-… permissions.gate PERMISSION tool=run_shell action=ask source=user allowed=True reason=user approved
2026-11-25T11:59:19.120Z INFO session=9406fa4f-… turn=482ec1f0-… httpx HTTP Request: POST … "HTTP/1.1 429 Too Many Requests"
```

- Times are UTC, the same clock as the transcript.
- Every line carries `session=` and `turn=` (`-` outside a session or between turns),
  including lines from the `openai` and `httpx` libraries. `turn=` is the id of the user
  message that started the turn in the transcript.
- Tool arguments and results are **not** logged (they can contain secrets); use
  `call_id` to find the full call in the transcript.
- The file rotates at `HARNESS_LOG_MAX_BYTES`, keeping `HARNESS_LOG_BACKUPS` older parts.

Useful searches:

```bash
cd ~/.harness/projects/harness-*/
grep "session=9406fa4f" agent.log*          # one session
grep "turn=482ec1f0" agent.log*             # one turn
grep PERMISSION agent.log | tail -20        # recent permission decisions
grep call_g88q sessions/*.jsonl             # full arguments and result of one tool call
```

`source` in a `PERMISSION` line is the quickest diagnosis:

- `mode`: the mode fallback decided (read, edit in `accept_edits`, plan rules)
- `rule`: a deny/ask/allow rule matched
- `user`: the approver answered (terminal, auto-yes, or auto-deny)
- `error`: the check crashed and the call was refused (fail-closed)

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

# readonly profile: the model is only offered read_file and list_dir
./venv/bin/python agent.py --profile readonly "summarise this repo"

# interactive: you answer the prompt
./venv/bin/python agent.py
User : run ls
```

---

## Tests

Run the whole suite from the repo root:

```bash
./venv/bin/python -m pytest -v
```

One file:

```bash
./venv/bin/python -m pytest tests/test_context.py -v
```

| File | Covers |
|---|---|
| `test_rules.py`, `test_modes.py`, `test_policy.py`, `test_gate.py` | Permission rules, modes, precedence, fail-closed gate |
| `test_agent.py` | Agent loop basics |
| `test_errors.py` | 413 / 400 / 429 handling and turn rollback |
| `test_context.py`, `test_split_turns.py` | Token-budget trimming; tool call/result pairs never split |
| `test_logging.py` | No tool arguments or output (secrets) in `agent.log` |
| `test_log_context.py` | `session=` / `turn=` on every log line, including library lines |
| `test_rotation.py` | Log rotation, file count and size limits |
| `test_shell_env.py` | Shell commands cannot see API keys |

The tests never call the API: they use fake clients, so they run offline and need no
real key. `agent.py`/`llm.py` read `GROQ_API_KEY` and `GROQ_MODEL_NAME` at import, so
without a `.env` set dummy values:

```bash
GROQ_API_KEY=dummy GROQ_MODEL_NAME=dummy ./venv/bin/python -m pytest -q
```

Tracebacks printed during the run (`RuntimeError: approver crashed`,
`RuntimeError: boom`) are expected: those tests check that failures are handled.

**CI:** GitHub Actions runs the suite on every push and pull request, on Python 3.12
and 3.13, with dummy keys (`.github/workflows/tests.yml`). It can also be started by
hand from the Actions tab (**Run workflow**). CI uses a fresh clone, so a test must
only depend on files that are committed; to check that locally before pushing:

```bash
git clone . /tmp/harness-ci-check && cd /tmp/harness-ci-check
GROQ_API_KEY=dummy GROQ_MODEL_NAME=dummy ~/Desktop/harness/venv/bin/python -m pytest -q
cd - && rm -rf /tmp/harness-ci-check
```

---

## Security model (read this)

The permission layer is a **deterministic approval gate, not a sandbox.**

- `run_shell` uses `subprocess.run(..., shell=True)`. Once approved, a command can do
  anything the current user can do: read files outside the workspace (including
  `~/.ssh`), use the network, and `cd /`. It does run with a minimal environment, so
  API keys from `.env` are not in its environment variables. OS-level sandboxing is
  planned.
- The model can still **read `.env` as a file** (reads are always allowed and `.env`
  is inside the workspace). Its contents then reach the provider and the transcript.
  A deny rule for `.env*` is planned once rules can be configured.
- File tools are confined by `utils.safe_path()`, but that is a best-effort check
  (`realpath` + prefix), not a kernel sandbox. There is a small TOCTOU window between
  the path check and the file open.
- `agent.log` never contains tool arguments or results, so secrets read by the model
  are not copied into the log. The transcript (`sessions/*.jsonl`) does contain them,
  because replay needs them: treat it as sensitive.
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

**`KeyError: 'GROQ_API_KEY'` or `KeyError: 'GROQ_MODEL_NAME'`**
No `.env` in the repo root (or the variable is missing). Recreate it as shown above.
For tests only, dummy values are enough (see Tests).

**"This request is bigger than your provider's per-minute token limit"**
One request exceeded your tier's tokens-per-minute limit (HTTP 413). Ask about a
smaller part of the code, lower `HARNESS_READ_MAX_CHARS` / `HARNESS_CONTEXT_BUDGET`, or
use a higher provider tier.

**"The conversation no longer fits in the model's context window"**
Even after trimming, the current turn is larger than `HARNESS_CONTEXT_BUDGET`. Start a
new session or ask about a smaller part of the code.

**Long pauses between steps**
Usually rate limiting: `agent.log` shows `429 Too Many Requests` followed by
`Retrying request … in N seconds`. The harness waits and continues on its own.

**A shell command says a tool or variable is missing that works in your terminal**
`run_shell` only passes a minimal environment. Add the variable to `SHELL_ENV_KEYS` in
`utils.py` if the command really needs it.

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
