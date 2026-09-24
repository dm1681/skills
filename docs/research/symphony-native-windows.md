# Symphony native Windows research

Research date: 2026-09-23. Read-only investigation; no dependencies installed,
fetched code executed, Symphony service started, or tracker changed.

`git ls-remote https://github.com/openai/symphony.git HEAD` returned
`be10a1b79df723d6d7612b5651c8522704dafb2e`, matching the revision used in the
earlier assessment. GitHub's commit API reports its committer timestamp as
2026-09-15T22:12:07Z. Thus there is no newer default-branch revision in this
check that changes the earlier assessment.
[Commit](https://github.com/openai/symphony/commit/be10a1b79df723d6d7612b5651c8522704dafb2e)

## Conclusion

Native Windows is plausible, but this investigation does **not** establish
that the OpenAI Elixir reference implementation works reliably there. Its
underlying runtimes support Windows; its launcher, hooks, packaging and CI
remain oriented toward Unix environments. A PowerShell launch command cannot
by itself remove those internal assumptions. Treat a Git Bash bridge as an
experimental compatibility route requiring validation, not an already supported
installation mode.

## Confirmed facts

| Area | Evidence and consequence |
| --- | --- |
| Language runtime | Elixir officially provides Windows installers and PowerShell installation instructions. Erlang/OTP and Elixir can run natively; Linux is not a fundamental language requirement. [Elixir installation](https://elixir-lang.org/install/) |
| Project versions | Symphony pins Erlang 28 and Elixir 1.19.5 compiled for OTP 28 in its development configuration. Match the project versions rather than blindly selecting the latest runtime. [mise.toml](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/mise.toml) |
| Worker startup | `AppServer.start_port` resolves `bash` on PATH and executes `-lc`. Absence of Bash returns `bash_not_found`. The command constructed inside Bash uses POSIX `unset` and `exec`; `codex.command` changes the inner command, not the shell used to launch it. [app_server.ex](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/codex/app_server.ex#L176) |
| Workspace hooks | Local lifecycle hooks execute through `System.cmd("sh", ["-lc", command], ...)`. PowerShell hook contents therefore need an explicit PowerShell invocation inside the hook or a source change to shell selection. [workspace.ex](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/workspace.ex#L368) |
| Packaging | Burrito targets are macOS and Linux, each ARM64 and x86-64; no Windows target is declared. `mix build` builds an escript. Building/running that source route is separate from adding Windows standalone packaging. [mix.exs](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/mix.exs) |
| CI | The complete `make all` verification job runs on Ubuntu. Release configuration builds and smoke-tests four Linux/macOS targets. Those jobs provide no native Windows compatibility evidence. [make-all](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/.github/workflows/make-all.yml), [release workflow](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/.github/workflows/burrito-release.yml) |
| Codex itself | Official Codex documentation supports native Windows operation and PowerShell workflows, including native Windows sandbox modes. That support does not automatically validate Symphony's wrapper around Codex. [Windows documentation](https://developers.openai.com/codex/windows) |
| Bash availability | Git for Windows supplies Bash emulation. That makes a Windows-hosted Bash bridge plausible without WSL, but the Git documentation does not certify Symphony. [Git for Windows](https://gitforwindows.org/) |

The runtime build uses normal Mix dependencies. The source declares `lazy_html`
as test-only, and the lockfile shows its native build/precompiler dependencies.
Therefore success building a development escript would not establish that the
full test environment builds on Windows. Burrito is production-only; its release
toolchain is a separate concern from the simplest source-running experiment.
[Dependency declaration](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/mix.exs#L66),
[locked dependencies](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/mix.lock)

## Path and process assessment

There is no confirmed path-format showstopper from static inspection.
`PathSafety` uses Elixir's `Path.expand`, `Path.split` and `Path.join`, plus
filesystem symlink resolution. Official Elixir documentation supports Windows
drive paths and normalization using these APIs. Forward-slash literals in
containment checks therefore do not alone demonstrate a bug.
[PathSafety](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/path_safety.ex),
[Elixir Path API](https://hexdocs.pm/elixir/Path.html)

Untested boundaries include case aliases, junctions/symlinks, spaces and Unicode,
long paths, Git Bash argument/environment conversion, and executable discovery.
These are compatibility tests to perform, not observed Symphony defects.

The worker stop operation closes its Erlang port. It does not establish, merely
by reading that code, how every Git Bash/Windows child-process combination will
terminate. Cancellation, timeout and restart tests must confirm no orphaned
workers and no accidental duplicated execution.
[stop_port](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/codex/app_server.ex#L897)

## Upstream support evidence

Public GitHub search API queries for `repo:openai/symphony windows`, `powershell`
and `win32` returned zero issue/PR matches during this check. The current open PR
listing did not identify a Windows port. This is a bounded negative search,
not proof no contributor has ever run it on Windows or no fork supports it.
[Upstream pull requests](https://github.com/openai/symphony/pulls)

The language-neutral specification permits hooks in an OS-appropriate shell.
Windows support would be compatible with the specification even though this
particular reference implementation uses Unix shells.
[Workspace hook contract](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/SPEC.md#94-workspace-hooks)

## Proposed native compatibility experiment

This is a future experiment, not work performed by this research:

1. Build the pinned source with its matching native Windows Elixir/Erlang pair.
2. Launch from PowerShell with an explicit process-local Git Bash tool path.
3. Verify an isolated temporary workspace can run all hooks and a Codex
   app-server handshake using a Windows-native Codex executable.
4. Verify the worker's reported working directory and sandbox write boundaries.
5. Exercise cancellation, hook timeout, retry, restart and terminal cleanup.
6. Test the dashboard on loopback, and run the relevant upstream tests on Windows.

Only after that evidence should the installer advertise native Windows as a
supported mode. Until then, choosing a Unix runtime for Symphony is the lower
uncertainty option; the user's interactive terminal can still be PowerShell.
