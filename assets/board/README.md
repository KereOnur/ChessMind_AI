# NeuroChess board-preview artwork

These 38 SVG files are original vector resources created locally for development
phase 3. No stock images, internet pictures, paid services, or image-generation
API were used. No external images, links, or fonts are embedded. The illustrations
may be used and modified within NeuroChess; no third-party image license applies.

The complete source is `../generate_board_pieces.py`. It uses only Python's
standard library and writes to this directory when explicitly run:

```bash
.venv/bin/python -B assets/generate_board_pieces.py
```

Each of `classic/`, `wood/`, and `cyber/` contains twelve shaded piece illustrations:
white and black pawn, rook, knight, bishop, queen, and king. The bishop has its own
mitre and cut, and all six silhouettes are distinct. Material gradients, shaped
bases, and small cast shadows create depth without a real 3D engine. Cyber pieces
add cyan rim lighting. `wood-light.svg` and `wood-dark.svg` are original wood-grain
square textures. The board itself is orthographic, with square fields.

These resources are independent of the six phase-two menu illustrations, which
remain unchanged. Rendering resources contain no chess rules or game state.
