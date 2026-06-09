---
name: policies/document_fonts
variant: default
description: Mixed Chinese/English fonts for scripts and document tools (PDF, DOCX, PPTX, Excel) across Windows, macOS, and Linux.
---

## Document fonts (mixed Chinese + English)

When generating files with **`code_execution`**, **`run_skill_script`**, or hand-written ReportLab / Office code, the **runtime host** supplies fonts. Paths and family names differ by OS; do not hardcode only one platform.

### ReportLab (PDF)

- Register a **pan-Unicode** font with `pdfmetrics.registerFont(TTFont(...))` from a real **`.otf` / `.ttf`** (or **`.ttc`** with the correct `subfontIndex` / name for the desired face).
- **Do not** use **`DroidSansFallbackFull.ttf`** (or similar Latin-stripped **supplemental** fallbacks) as the **sole** body font: Latin and digits can disappear. Prefer **Noto Sans SC / Noto Sans CJK**, **Source Han Sans**, **WenQuanYi Micro Hei** (typical on Linux), **Microsoft YaHei** (Windows), **PingFang SC** or **Heiti SC** (macOS UI families when installed).
- **Discovery pattern:** try an ordered list of `Path` candidates; use the first that `exists()`. On **Linux (LeAgent server)**, check `~/.local/share/fonts` and `/usr/share/fonts/...` for `NotoSansSC-Regular.otf`, `NotoSansCJK-Regular.ttc`, `wqy-microhei.ttc` (align with `pdf_generator` / `LEAGENT_CJK_FONT` if set). On **macOS:** `/Library/Fonts`, `/System/Library/Fonts/Supplemental`, `/System/Library/Fonts`. On **Windows:** `Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"` (e.g. `msyh.ttc`).

#### Probe the host first (Linux — generate reliable code)

Do **not** guess paths blindly. Prefer one quick probe (via **`code_execution`** or a shell step), then pass the **existing** file path to **`pdf_generator`** as **`cjk_font_path`** or use it in ReportLab `TTFont`.

Example shell checks (paths must exist before embedding):

```bash
ls /usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf \
   /usr/share/fonts/truetype/wqy/wqy-microhei.ttc 2>/dev/null
fc-list :lang=zh file 2>/dev/null | head -20
```

Pick a **pan-Unicode** line from `fc-list` (Noto Sans/Serif CJK, WenQuanYi, Source Han — avoid supplement-only fallbacks). Example Python guard:

```python
from pathlib import Path
candidates = [
    Path("/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf"),
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
]
cjk_path = next((str(p) for p in candidates if p.is_file()), None)
# Then pass cjk_path to pdf_generator["cjk_font_path"] or registerFont(TTFont(..., cjk_path)).
```

If probe finds nothing, suggest installing **`fonts-noto-cjk`** or **`fonts-wqy-microhei`** (Debian/Ubuntu) or set **`LEAGENT_CJK_FONT`** to an absolute path.

### python-docx / python-pptx

- `font_name` / `run.font.name` must match a **locally installed** family. Office **substitutes** if the name is missing; mixed scripts may look wrong.
- **Portable options:** omit custom `font_name` for body text and rely on the document default; or use `platform.system()` and pick a **short list** of OS-appropriate names (`"Microsoft YaHei"`, `"PingFang SC"`, `"WenQuanYi Micro Hei"`, `"Noto Sans CJK SC"`) only when you document the assumption; never assume a Windows-only name on Linux.

### openpyxl (Excel)

- `Font(name=...)` follows the same rule: the name must exist on the machine that **opens** the `.xlsx`.

### Matplotlib

- **`code_execution` subprocess** (`leagent.code.runner`) auto-configures matplotlib when the user script references matplotlib/pyplot (`matplotlib`, `pyplot`, `plt.`, `font_manager`, `mpl.`, `pylab`): it registers a pan-Unicode font from **`LEAGENT_CJK_FONT`** (if the file exists) or the same **system scan** as PDF (`Noto Sans SC`, Noto CJK TTC, WenQuanYi, `msyh.ttc` under `%WINDIR%/Fonts` on Windows, etc.), sets **`font.sans-serif`** and **`axes.unicode_minus = False`**. **`chart_generator`** injects the same hook into generated scripts.
- If Chinese still renders as boxes, install **`fonts-noto-cjk`** or **`fonts-wqy-microhei`** (Debian/Ubuntu) or set **`LEAGENT_CJK_FONT`** to an absolute path to a **`.otf` / `.ttf`** (preferred over ambiguous TTC subfaces for matplotlib).
- You may still override per-plot with `FontProperties(fname=...)` when you need a specific face.
