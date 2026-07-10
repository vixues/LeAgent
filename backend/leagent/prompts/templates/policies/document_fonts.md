---
name: policies/document_fonts
variant: default
description: Mixed Chinese/English fonts — guaranteed for document tools; guidance for hand-written scripts and Office viewer fonts.
---

## Document fonts (mixed Chinese + English)

### Built-in document tools — fonts are automatic

**`document_generate`** and **`slides_generate`** guarantee CJK-safe output; never probe font paths or pass font parameters for them:

- **PDF** embeds a pan-Unicode font automatically (env override → `~/.leagent/fonts/` → system scan → **auto-download of Noto Sans SC**). If embedding still failed the result contains `font_embedded: false` plus `warnings` — surface that to the user (fixes: network access, `LEAGENT_CJK_FONT=/abs/path.ttf`, or installing `fonts-noto-cjk`).
- **DOCX/PPTX** cannot embed font binaries; the tools set an **east-Asian font name** (e.g. `Microsoft YaHei`) on every run so Chinese renders correctly wherever such a family exists. On a viewer machine without any CJK font, text is intact but the OS substitutes a face — advise installing a CJK font there.
- Charts inside these tools (and `chart_generator`) configure matplotlib CJK automatically.

### Hand-written scripts (`code_execution`, `run_skill_script`)

Only when writing ReportLab / python-docx / python-pptx / matplotlib code yourself:

- Use a **pan-Unicode** face (Noto Sans SC / CJK, Source Han Sans, WenQuanYi Micro Hei). **Never** use Latin-stripped supplemental fallbacks (e.g. `DroidSansFallbackFull.ttf`) as the sole body font.
- Resolve a real path first — do not guess. The runtime injects **`LEAGENT_CJK_FONT`** into `code_execution` when a font is known (the auto-downloaded `~/.leagent/fonts/NotoSansSC-Regular.ttf` counts); prefer it:

```python
import os
from pathlib import Path
cjk = os.environ.get("LEAGENT_CJK_FONT", "")
if not (cjk and Path(cjk).is_file()):
    candidates = [
        Path.home() / ".leagent/fonts/NotoSansSC-Regular.ttf",
        Path("/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    ]
    cjk = next((str(p) for p in candidates if p.is_file()), "")
```

- **ReportLab note:** it rejects CFF/PostScript outlines (`postscript outlines are not supported`) — many distro Noto CJK **OTF/TTC** files fail. Prefer **TrueType `.ttf`** (the managed `~/.leagent/fonts/NotoSansSC-*.ttf` files are TrueType); for `.ttc` pass the right `subfontIndex`.
- **matplotlib:** the `code_execution` subprocess auto-configures CJK when the script references matplotlib (`pyplot`, `plt.`, `font_manager`, …): registers the resolved font, sets `font.sans-serif` and `axes.unicode_minus = False`. Override per-plot with `FontProperties(fname=...)` only when you need a specific face.
- **python-docx/pptx & openpyxl:** the family name must exist on the machine that **opens** the file. Set both the latin font and the east-Asian font (`w:eastAsia` in DOCX, `<a:ea>` in PPTX); portable names: `Microsoft YaHei`, `PingFang SC`, `Noto Sans CJK SC`, `WenQuanYi Micro Hei`.

If no font can be resolved anywhere, suggest installing **`fonts-noto-cjk`** or **`fonts-wqy-microhei`** (Debian/Ubuntu) or setting **`LEAGENT_CJK_FONT`** to an absolute `.ttf` path.
