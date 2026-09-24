# Symphony on Windows: WSL and PowerShell integration

Research date: September 23, 2026 (US Pacific). Research only: no Symphony
installation, worker launch, tracker change, or project configuration change.

## Recommendation

Keep PowerShell as the user's interactive shell. Use WSL2 as the first Symphony
runtime to validate, because upstream's runtime is POSIX-oriented. Treat native
Windows plus Git Bash as an experimental alternative until its startup, hooks,
process lifecycle and workspace tests pass. See the companion
[native Windows assessment](symphony-native-windows.md) for upstream evidence.

Separate shell preference from operating-system requirements. A user can operate
a Linux service from PowerShell without moving their everyday interactive work
to Bash. However, Windows-only project behavior needs Windows validation; merely
translating a pathname does not turn a Linux process into a Windows process.

This is an engineering recommendation, not a claim that a complete Symphony
deployment or sandboxed Windows interop has passed here.

## Three layouts to distinguish

| Layout | Assessment |
| --- | --- |
| Native Windows Symphony + native Windows Codex, with Git Bash for internal launches/hooks | Plausible, but upstream Windows integration/build coverage is missing; needs a bounded compatibility trial. |
| WSL Symphony + Linux Codex, Linux worker checkouts | Closest match to upstream runtime assumptions. Good default for portable projects, while the user keeps a separate Windows checkout. |
| WSL Symphony + Linux Codex, Windows-backed worker checkouts and explicit Windows PowerShell test commands | Plausible for Windows-dependent projects; basic interop verified below, full worker/sandbox/cancellation behavior untested. |

Do not assume a fourth arrangement, WSL Symphony launching native `codex.exe`,
works by changing the executable name. Symphony passes workspace paths through
the App Server protocol as well as process launch. A Windows process would need
correct Windows paths in those protocol fields and sandbox roots. A shell-only
conversion does not translate JSON messages. This is an inference from the
[Symphony launch and thread/turn code](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/codex/app_server.ex)
and the [App Server protocol](https://learn.chatgpt.com/docs/app-server).

## Path and command handling

Microsoft documents PowerShell-to-WSL execution through `wsl.exe` and Windows
executable invocation from WSL. Arguments are passed through, so explicit paths
must match the receiving program. Use path conversion in a tested launcher or
command wrapper rather than asking an agent to improvise it each time.
For Linux-heavy workloads Microsoft recommends Linux-resident files; mounted
Windows directories trade convenience for cross-filesystem overhead.
[Microsoft filesystem and interoperability guide](https://learn.microsoft.com/en-us/windows/wsl/filesystems).

The observed mapping for this repository is:

```text
Windows: C:\Users\hbar6\projects\skills
WSL:     /mnt/c/Users/hbar6/projects/skills
```

That pair represents one directory. A separate clone under `/home/...` is a
different checkout and must not be described as a path alias for this one.
Symphony worker checkouts should stay separate from the user's interactive
working tree. Preserve each issue's isolated workspace regardless of filesystem.

PowerShell also runs on Linux, but Windows-specific cmdlets and facilities are
not universally available there. Linux `pwsh` and Windows `pwsh.exe` are distinct
execution choices. [Microsoft PowerShell platform differences](https://learn.microsoft.com/en-us/powershell/scripting/whats-new/unix-support?view=powershell-7.5).

Create environments for the intended platform and workspace. In particular,
Python virtual environments contain interpreter-specific paths and platform
layouts and are not portable copies. Do not share a Windows `.venv` with Linux
Python. [Python venv documentation](https://docs.python.org/3/library/venv.html).

## Read-only probes on this machine

The following were run, not inferred from documentation:

- `wsl.exe --list --verbose`: Ubuntu is the default, running distribution,
  version 2. Docker Desktop's WSL2 distribution is stopped.
- In Ubuntu with this repository as the working directory, `pwd` returned
  `/mnt/c/Users/hbar6/projects/skills`, and `wslpath -w` returned the Windows path
  above.
- Ubuntu launched `/mnt/c/Program Files (x86)/PowerShell/7/pwsh.exe` with
  `-NoLogo -NoProfile -NonInteractive`. It reported PowerShell `7.6.4`, OS platform
  `Win32NT`, and working directory `C:\Users\hbar6\projects\skills`.
- A deliberate `exit 7` from that Windows PowerShell process was returned through
  WSL as `$LASTEXITCODE = 7`. The first outer tool command normalized failure to
  exit 1; a second probe explicitly captured and verified the inner exit code.
- The probed non-login Ubuntu PATH found `/usr/bin/git`, `/usr/bin/bwrap`, and
  Windows `pwsh.exe`. It did not find `codex`, Linux `pwsh`, `elixir`, `mix`, or
  `erl`. This is a PATH observation, not proof those programs exist nowhere.
- Windows PATH found native Codex, PowerShell, Git and Scoop Bash/sh shims. The
  shim metadata points to Git's Bash/sh binaries. Elixir/Mix/Erlang were not
  found on that PATH.

WSL enumeration initially failed within the current Codex sandbox. The successful
read-only WSL probes used approved host execution. They therefore do not prove
interop works inside a future Symphony Codex worker's sandbox. No sandbox
configuration was weakened or changed. No profiles, credentials, SSH keys or
tokens were copied.

Historical memory about a Herdr WSL/PowerShell bridge suggested testing this
arrangement; the claims above are fresh probes, not assertions that the earlier
bridge is still configured or reliable.

## What remains to validate before selecting this deployment

1. Start the selected Symphony runtime and a Codex App Server session in a
   disposable issue workspace, with normal configured sandbox restrictions.
2. Run a representative project check and a deliberately failing check through
   the intended shell; verify working directory, arguments with spaces and exit
   codes. For Windows projects, exercise the actual Windows-dependent behavior.
3. Verify cancellation and timeout handling leave no task-owned processes behind,
   and that cleanup preserves sibling and interactive workspaces.
4. Verify tracker/Git authentication, skill loading and the dashboard from the
   target runtime. Do not assume the desktop session's connections are inherited.
5. Confirm the setup-issue readiness gate before enabling live dispatch. Keep
   installation, configuration and starting queued work separate.

Codex supports native Windows execution and WSL2 execution, but that does not
establish support for every mixed process arrangement. Current official guidance
describes a Linux sandbox for WSL2 and a separate native Windows sandbox.
[Native Windows](https://learn.chatgpt.com/docs/windows/windows-sandbox),
[WSL](https://learn.chatgpt.com/docs/windows/wsl).

Windows can normally access a WSL-hosted web application through localhost;
the dashboard still needs a local check in the eventual launch configuration.
[Microsoft WSL networking](https://learn.microsoft.com/en-us/windows/wsl/networking).

## Fit for this skills repository

`install.ps1` is a small wrapper selecting uv or Python and forwarding to
`install.py`. The core package describes itself as a cross-platform installer.
That makes shell preference alone a poor reason to require all workers to be
native Windows. Windows installation behavior still needs actual Windows checks.
No package installs or repository test suites were run during this research.

This research does not resume the planned Symphony/skill implementation or change
the earlier agreement to update the Linear templates at the end of that work.
