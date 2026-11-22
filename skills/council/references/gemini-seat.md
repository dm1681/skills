# Gemini seat: sign-in and isolation

## Signing in

The Gemini seat runs Antigravity CLI (`agy`), signed in with a personal
Google account. Which account types work:

| Route | Accounts | Cost |
| --- | --- | --- |
| `agy`, Sign in with Google (this seat) | personal Google accounts on Google AI Pro or AI Ultra; a free account may not be offered Neon | the plan's own quota |
| Gemini CLI, Sign in with Google | Gemini Code Assist Standard or Enterprise licences only; personal, AI Pro and Ultra accounts are refused since 2026-06-18 | the licence |
| A Gemini API key | any account with billing; `gemini-4-neon` is not on the free tier | billed per call |

The seat never uses a key: it drops `GEMINI_API_KEY`, `GOOGLE_API_KEY`,
`GOOGLE_APPLICATION_CREDENTIALS` and `AGY_ADC_AUTH`, so a key exported for
another tool is never billed. When the seat reports that `agy` is not signed
in, the user signs in once per machine, in a terminal of their own:

    agy

They choose **Google OAuth**, sign in in the browser, leave the data-sharing
box as they wish, and quit at the folder-trust question (the seat needs no
trusted folder). On a machine without a browser, such as one reached over
SSH, `agy` prints a URL: open it on any device, sign in, and paste the code
it shows back into the terminal. To install `agy`, see
<https://antigravity.google/docs/install>; it updates itself afterwards.

## Isolation

`--cwd` may be a repository nobody vetted, so no seat runs inside it. Each
seat's working directory is a new, empty temp folder - the place every CLI
loads project settings, hooks, MCP servers and folder trust from - and the
repository is granted for reading only: `--add-dir` for Claude, which also
loads user settings alone with hooks off; Codex's read-only sandbox reads it
directly; for Gemini, a one-session `--settings` that allows `read_file` on
the repository and the commands `ls`, `grep`, `cat`, `head`, `tail` and `wc`,
and denies every file write, redirection, MCP tool and URL. `agy` is not
given `--add-dir`: an added folder joins its workspace, and it then starts
that folder's `.agents/` MCP servers and hooks. Its own sandbox does not stop
a write outside the workspace, so the permission rules are what keep the
seat read-only. `agy` saves each seat's conversation in its own history, as
it does for any session; the user's settings are never written.
