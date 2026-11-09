#!/bin/bash
# Copy the logos and the Geist font (from the web app's build) next to the title cards,
# and make the Geist SemiBold TTF the subtitles use. Run once, after `pnpm build` in apps/web.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WEB="$HERE/../../apps/web"
cp "$WEB/public/brand/Pilao_avec_slogan.png" "$WEB/public/brand/Pilao_sans_slogan.png" "$HERE/cards/"
mkdir -p "$HERE/fonts"
uv run --no-project -q --with fonttools --with brotli python - "$WEB/.next/static/media" "$HERE" <<'PY'
import sys
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
media, here = Path(sys.argv[1]), Path(sys.argv[2])
geist = next(f for f in sorted(media.glob("*.woff2")) if TTFont(f)["name"].getDebugName(1) == "Geist" and "fvar" in TTFont(f))
(here / "cards" / "font-b.woff2").write_bytes(geist.read_bytes())
font = instancer.instantiateVariableFont(TTFont(geist), {"wght": 600})
font.flavor = None
for nid, value in ((1, "Geist SemiBold"), (2, "Regular"), (4, "Geist SemiBold"), (6, "Geist-SemiBold")):
    font["name"].setName(value, nid, 3, 1, 0x409)
font.save(here / "fonts" / "Geist-SemiBold.ttf")
print("logos et police prêts")
PY
