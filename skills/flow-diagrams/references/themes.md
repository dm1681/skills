# Colour themes

The visual language names colours by **role** — `green`, `blue`, `peach`,
`text`, `base`, … — and every node, edge and container kind points at a role,
never at a value. A theme assigns values to the 26 roles, so a light theme or
a custom palette changes how the page looks without changing what anything
means: a teal arrow is still asynchronous, red is still failure.

## Built-in themes

| Name | Look |
|---|---|
| `mocha` | Catppuccin Mocha — the default, darkest |
| `macchiato` | Catppuccin Macchiato — dark |
| `frappe` | Catppuccin Frappé — mid-dark |
| `latte` | Catppuccin Latte — light |

They live in `assets/diagram-themes.json`, shared with every skill that draws
this look.

## Choosing themes when building

```bash
python3 <skill-dir>/scripts/build_diagram.py model.json                     # all four, picker shown, opens in mocha
python3 <skill-dir>/scripts/build_diagram.py model.json --theme latte       # all four, opens in latte
python3 <skill-dir>/scripts/build_diagram.py model.json --themes latte      # locked to latte, no picker
python3 <skill-dir>/scripts/build_diagram.py model.json --themes mocha,latte --theme latte
python3 <skill-dir>/scripts/build_diagram.py model.json --theme-file my-theme.json   # adds it, opens in it
```

- `--themes` lists what the viewer may pick (`all` by default). One theme
  locks the page and hides the picker.
- `--theme` is the theme the page opens in. Without it, a custom theme you
  passed opens first; otherwise the first offered theme does.
- The viewer's choice is remembered in their browser, like the panel state.

`codebase-onboarding`'s builder takes the same flags. A skill may also lock
its pages to one theme by never offering others.

## Writing a custom theme

```json
{
  "name": "paper",
  "label": "Paper (custom)",
  "extends": "latte",
  "colors": {
    "base": "#f6f1e7", "mantle": "#efe8da", "crust": "#e6dccb",
    "text": "#3b3226", "subtext1": "#4f4535", "subtext0": "#62584a"
  }
}
```

- `name` — `[A-Za-z0-9_-]+`, not one of the built-in names.
- `label` — what the picker shows (default: the name).
- `extends` — optional built-in to start from; list only the roles that
  differ. Without it, all 26 roles are required.
- `dark` — optional; worked out from `base` when omitted. It sets the
  browser's `color-scheme`, so scrollbars and inputs match.
- `colors` — `#rrggbb` per role. The roles:
  `rosewater flamingo pink mauve red maroon peach yellow green teal sky
  sapphire blue lavender text subtext1 subtext0 overlay2 overlay1 overlay0
  surface2 surface1 surface0 base mantle crust`.

`examples/themes/paper.json` is a working example.

### What a custom theme must keep

The build rejects a theme that would break the language, with every reason
at once:

| Check | Minimum | Why |
|---|---|---|
| Kind colours apart | ΔE 8 (CIE76) between any two of `green blue yellow peach mauve teal lavender pink red sapphire` | Two kinds that look alike stop meaning different things. The built-ins keep at least 10. |
| `text` on `base` | 4.5 : 1 | WCAG AA body text. |
| `subtext0` on `base` | 3 : 1 | Secondary text: legend definitions, summaries. |
| Kind colours on `mantle` | 1.8 : 1 | A shape's outline must show against its container. |

Roles no kind uses — `rosewater`, `flamingo`, `maroon`, `sky` — are free for
extensions, and still keep red for failure: if an extension claims a role,
check it reads against both a light and a dark theme.

## For a skill with its own builder

```python
import diagram_core as core

themes = core.load_themes(skill_root / "assets" / "diagram-themes.json")
core.apply_themes(built, themes, default="mocha", offer=["mocha", "latte"])
# or, with the shared flags on your parser:
core.add_theme_arguments(parser)
core.themes_from_args(args, built, themes, kinds)
```

`core.custom_theme(raw, themes, kinds)` validates one custom theme;
`core.theme_problems(name, theme, kinds)` returns the reasons a palette would
not carry the language. A page built without `apply_themes` keeps the
template's own Mocha palette and shows no picker.
