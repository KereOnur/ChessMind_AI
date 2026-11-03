# Original NeuroChess artwork

All six SVG illustrations are original procedural vector drawings created for
this project. They use custom piece silhouettes, perspective geometry, gradients,
and (for the grandmaster preview) hand-defined wood-grain curves. They contain no
internet images, stock assets, external fonts, embedded remote links, or assets
from an image-generation API. No third-party image attribution or license is
required. These original illustrations may be used and modified in NeuroChess.

`generate_artwork.py` is their complete source. It uses only Python's standard
library, makes no network calls, and writes beside itself when run explicitly:

```bash
.venv/bin/python -B assets/generate_artwork.py
```

- `menu-chess.svg`: large dark scene with blue lighting
- `amateur.svg`: green/cream board with traditional ivory/dark pieces
- `grandmaster.svg`: warm wood grain and shaded wooden pieces
- `adaptive.svg`: dark cyber-blue board and luminous blue accents
- `color-white.svg`, `color-black.svg`: player-color selection artwork

The scenes are decorative illustrations. No scene is a playable chessboard and
no chess position, move, or rule is evaluated by the drawing code.
