"""Create NeuroChess's original local SVG illustrations using only the stdlib.

No network access, image generation service, external image, or external font.
Run explicitly from any working directory; output stays beside this script.
"""
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
BODY = 'M -43 116 C -34 141 -29 167 -34 192 C -37 212 -49 226 -57 239 L 57 239 C 49 226 37 212 34 192 C 29 167 34 141 43 116 Z'


def piece(kind, x, base, height, material='dark', cyber=False, token='p'):
    scale = height / 300
    light = material == 'ivory'
    wood = material == 'wood'
    colors = ('#77644b', '#fff3d4', '#c9b792', '#fff9e9') if light else (('#3e1d10', '#cd9257', '#714022', '#e2b47b') if wood else ('#020710', '#304866', '#0b1525', '#6aa8f0'))
    a, b, c, edge = colors
    gradient = f'<linearGradient id="{token}g"><stop stop-color="{a}"/><stop offset=".34" stop-color="{b}"/><stop offset=".58" stop-color="{c}"/><stop offset=".82" stop-color="{b}"/><stop offset="1" stop-color="{a}"/></linearGradient>'
    shapes = [f'<path d="{BODY}"/>', '<ellipse cy="239" rx="59" ry="12"/>', '<path d="M-59 239 L-66 253 Q-68 262-59 267 L59 267 Q68 262 66 253 L59 239 Z"/>', '<ellipse cy="268" rx="73" ry="15"/>', '<path d="M-73 268 L-76 283 Q0 307 76 283 L73 268 Q0 289-73 268 Z"/>', '<ellipse cy="284" rx="76" ry="13"/>', '<ellipse cy="116" rx="44" ry="10"/>', '<ellipse cy="105" rx="40" ry="9"/>']
    if kind == 'king':
        shapes += ['<path d="M-31 103 L-35 81 Q-27 59 0 58 Q27 59 35 81 L31 103 Z"/>', '<ellipse cy="79" rx="35" ry="11"/>', '<path d="M-9 17 H9 V32 H26 V48 H9 V66 H-9 V48 H-26 V32 H-9 Z"/>']
    elif kind == 'queen':
        shapes += ['<path d="M-33 103 L-48 50 L-24 68 L-13 37 L0 63 L18 35 L28 67 L49 48 L34 103 Z"/>', '<ellipse cy="96" rx="37" ry="9"/>']
        shapes += [f'<circle cx="{cx}" cy="{cy}" r="6"/>' for cx, cy in [(-48, 48), (-13, 35), (18, 33), (49, 46)]]
    elif kind == 'knight':
        shapes += ['<path d="M-44 107 C-48 66-25 24 10 15 L3 0 L24 12 L37 4 L35 24 L58 63 L43 79 L20 68 L3 76 Q28 91 35 107 Z"/>']
    elif kind == 'rook':
        shapes += ['<path d="M-31 104 L-35 70 L-44 65 V30 H-24 V46 H-10 V29 H10 V46 H24 V30 H44 V65 L35 70 L31 104 Z"/>']
    else:
        shapes += ['<path d="M-26 104 Q-28 83-16 74 H16 Q28 83 26 104 Z"/>', '<circle cy="59" r="28"/>']
    shadow = f'<ellipse cx="{x + height * .08}" cy="{base + 9}" rx="{height * .31}" ry="{height * .064}" fill="#000" opacity=".52"/>'
    content = gradient + f'<g transform="translate({x} {base-height}) scale({scale})" fill="url(#{token}g)" stroke="{edge}" stroke-opacity=".36" stroke-width="1.5" stroke-linejoin="round">' + ''.join(shapes)
    content += f'<path d="M-28 126 Q-19 174-27 199" fill="none" stroke="{edge}" stroke-opacity=".32" stroke-width="4"/>'
    if kind == 'knight':
        content += '<circle cx="26" cy="40" r="3.8" fill="#07101b" stroke="none"/><path d="M-26 93 Q-21 56 4 31" fill="none" stroke-opacity=".5"/>'
    if wood:
        content += '<g fill="none" stroke="#32190e" stroke-width="1" stroke-opacity=".25">'
        for i in range(-23, 24, 6):
            content += f'<path d="M{i} 128 Q{i+4} 178 {i-2} 226"/>'
        content += '</g>'
    if cyber:
        content += '<ellipse cy="271" rx="72" ry="10" fill="none" stroke="#329aff" stroke-opacity=".85" stroke-width="3"/><path d="M-42 117 Q0 129 42 117" fill="none" stroke="#6cdfff" stroke-opacity=".85" stroke-width="2"/>'
    return shadow + content + '</g>'


def point(u, v):
    # A perspective board: back edge is narrower than the near edge.
    back_left, back_right = (396, 366), (1068, 425)
    near_left, near_right = (72, 728), (937, 866)
    lx = back_left[0] * (1-v) + near_left[0] * v
    ly = back_left[1] * (1-v) + near_left[1] * v
    rx = back_right[0] * (1-v) + near_right[0] * v
    ry = back_right[1] * (1-v) + near_right[1] * v
    return (lx * (1-u) + rx * u, ly * (1-u) + ry * u)


def polygon(points):
    return ' '.join(f'{x:.1f},{y:.1f}' for x, y in points)


def scene(style):
    wood = style == 'wood'
    green = style == 'classic'
    title = {'hero': 'NeuroChess – polierte Schachfiguren im blauen Licht', 'classic': 'Traditionelle Figuren auf grün-cremefarbenem Brett', 'wood': 'Räumliche Holzfiguren auf gemasertem Schachbrett', 'cyber': 'Futuristische Figuren mit cyberblauen Lichtkanten'}[style]
    color1, color2 = ('#243f34', '#0b1916') if green else (('#342217', '#110e0c') if wood else ('#12233e', '#060c17'))
    light, dark = ('#d0c5a3', '#3d6553') if green else (('#af8052', '#51301e') if wood else ('#263a56', '#0b1423'))
    accent = '#83b99b' if green else ('#d5a46e' if wood else '#3b98ff')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="920" viewBox="0 0 1200 920"><title>{escape(title)}</title><desc>Original NeuroChess vector illustration; generated locally, without external source material.</desc><defs><radialGradient id="bg" cx=".55" cy=".3" r=".85"><stop stop-color="{color1}"/><stop offset="1" stop-color="{color2}"/></radialGradient><radialGradient id="halo"><stop stop-color="{accent}" stop-opacity=".24"/><stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient></defs><rect width="1200" height="920" fill="url(#bg)"/><ellipse cx="700" cy="385" rx="470" ry="410" fill="url(#halo)"/>'
    if style in ('hero', 'cyber'):
        for i in range(5):
            svg += f'<path d="M{120+i*195} 0 V{170+i*17} L{180+i*195} {250+i*17}" stroke="{accent}" stroke-opacity=".1" fill="none"/>'
        svg += '<circle cx="725" cy="260" r="192" fill="none" stroke="#50a9ff" stroke-opacity=".11"/><circle cx="725" cy="260" r="173" fill="none" stroke="#50a9ff" stroke-opacity=".05"/>'
    outer = [point(0, 0), point(1, 0), point(1, 1), point(0, 1)]
    svg += f'<polygon points="{polygon([(x,y+17) for x,y in outer])}" fill="#030609" stroke="{accent}" stroke-opacity=".28" stroke-width="2"/>'
    for row in range(8):
        for col in range(8):
            corners = [point(col/8,row/8), point((col+1)/8,row/8), point((col+1)/8,(row+1)/8), point(col/8,(row+1)/8)]
            svg += f'<polygon points="{polygon(corners)}" fill="{light if (row+col)%2 == 0 else dark}" stroke="#000" stroke-opacity=".14" stroke-width=".8"/>'
    svg += f'<polygon points="{polygon(outer)}" fill="none" stroke="{accent}" stroke-opacity=".5" stroke-width="3"/>'
    if wood:
        # Wood grain is drawn within each tile; no SVG clipping/filter extension.
        for row in range(8):
            for col in range(8):
                for grain in (.22, .47, .74):
                    start=point((col+.02)/8,(row+grain)/8)
                    end=point((col+.98)/8,(row+grain+.025)/8)
                    svg += f'<path d="M{start[0]:.1f} {start[1]:.1f} L{end[0]:.1f} {end[1]:.1f}" fill="none" stroke="#2d170b" stroke-opacity=".23" stroke-width="1.2"/>'
    material = 'wood' if wood else 'dark'
    svg += piece('pawn', 838, 492, 177, material, style=='cyber', 'back')
    svg += piece('rook', 1010, 578, 222, 'ivory' if green else material, style=='cyber', 'rook')
    svg += piece('queen', 490 if style=='cyber' else 677, 620 if style=='cyber' else 629, 340, 'ivory' if green else material, style in ('hero','cyber'), 'queen')
    svg += piece('king', 705 if style=='cyber' else 430, 755 if style=='cyber' else 725, 478, 'ivory' if green else material, style in ('hero','cyber'), 'king')
    svg += piece('knight', 936 if style=='cyber' else 808, 823 if style=='cyber' else 806, 318, material, style=='cyber', 'knight')
    svg += '<rect y="883" width="1200" height="37" fill="#000" opacity=".08"/></svg>'
    return svg


def main():
    for style, filename in [('hero','menu-chess.svg'),('classic','amateur.svg'),('wood','grandmaster.svg'),('cyber','adaptive.svg')]:
        (ROOT/filename).write_text(scene(style))
    for color, material in [('white','ivory'), ('black','dark')]:
        (ROOT/f'color-{color}.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="260" height="300" viewBox="0 0 260 320"><title>Spielerfarbe '+color+'</title>'+piece('king',130,305,290,material,False,'color')+'</svg>')
    print('Created six original local SVG illustrations in', ROOT)


if __name__ == '__main__':
    main()
