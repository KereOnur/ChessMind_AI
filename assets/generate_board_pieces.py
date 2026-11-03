"""Original top-view board assets. Stdlib only; no service or external images."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'board'
BODY = 'M-30 118 C-23 152-21 183-31 210 L-46 240 H46 L31 210 C21 183 23 152 30 118Z'
HEADS = {
    'pawn': '<path d="M-20 116L-19 91H19L20 116Z"/><circle cy="72" r="25"/>',
    'rook': '<path d="M-29 117L-33 68H-40V33H-23V47H-9V31H9V47H23V33H40V68H33L29 117Z"/>',
    'knight': '<path d="M-35 117C-49 76-26 34 9 19L7 4L28 20L40 14L36 35L59 72L44 86L20 74L1 83Q22 98 29 117Z"/><circle cx="27" cy="49" r="3.8" fill="#0b1720" stroke="none"/><path d="M-22 98Q-21 59 3 39" fill="none" stroke-width="3"/>',
    'bishop': '<path d="M-28 115Q-32 88-19 65L0 27L21 64Q35 90 28 115Z"/><path d="M16 54L-5 83" fill="none" stroke="#111a20" stroke-width="6"/><circle cy="22" r="7"/>',
    'queen': '<path d="M-28 114L-43 52L-23 70L-13 38L0 68L18 37L29 70L45 52L29 114Z"/><circle cx="-43" cy="50" r="5"/><circle cx="-13" cy="35" r="5"/><circle cx="18" cy="34" r="5"/><circle cx="45" cy="50" r="5"/>',
    'king': '<path d="M-28 114L-31 88Q-22 65 0 66Q22 65 31 88L28 114Z"/><path d="M-8 17H8V33H23V48H8V68H-8V48H-23V33H-8Z"/>',
}
PALETTES = {
    ('classic','white'): ('#79603b','#fff5d9','#bf9d68','#6c5a41'),
    ('classic','black'): ('#060b10','#4c5962','#161e25','#b3bfc7'),
    ('wood','white'): ('#89603b','#f2d7aa','#b59163','#6e4a29'),
    ('wood','black'): ('#100a07','#855330','#332013','#d0a06c'),
    ('cyber','white'): ('#7eabc4','#f3fcff','#b5ddef','#b6f6ff'),
    ('cyber','black'): ('#071526','#43698d','#122a45','#7fe6ff'),
}


def make_piece(theme, color, kind):
    a,b,c,edge=PALETTES[theme,color]
    shapes=f'<path d="{BODY}"/><ellipse cy="118" rx="34" ry="8"/>'
    shapes+=HEADS[kind]
    shapes+='<ellipse cy="240" rx="47" ry="9"/><path d="M-47 240L-55 258Q0 277 55 258L47 240Z"/><ellipse cy="264" rx="60" ry="11"/><path d="M-60 264L-64 282Q0 304 64 282L60 264Z"/><ellipse cy="283" rx="64" ry="12"/>'
    lines='<path d="M-18 130Q-12 174-20 208" fill="none" stroke-opacity=".35" stroke-width="3"/>'
    if theme=='wood':
        for x in range(-17,18,5): lines+=f'<path d="M{x} 129Q{x+3} 175 {x-2} 225" fill="none" stroke="#482710" stroke-width="1" stroke-opacity=".28"/>'
    if theme=='cyber':
        lines+='<ellipse cy="273" rx="62" ry="11" fill="none" stroke="#19d8ff" stroke-width="3"/><path d="M-34 118Q0 128 34 118" fill="none" stroke="#51e8ff" stroke-width="2.5"/>'
    outline_width, outline_opacity = ('2.3', '.92') if (theme,color) == ('cyber','black') else ('1.5', '.65')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="180" height="310" viewBox="0 0 180 310"><title>NeuroChess {theme} {color} {kind}</title><desc>Original locally created shaded chess silhouette. No external resources.</desc><defs><linearGradient id="material"><stop stop-color="{a}"/><stop offset=".3" stop-color="{b}"/><stop offset=".58" stop-color="{c}"/><stop offset=".84" stop-color="{b}"/><stop offset="1" stop-color="{a}"/></linearGradient></defs><ellipse cx="101" cy="296" rx="72" ry="12" fill="#000" opacity=".3"/><g transform="translate(85 0)" fill="url(#material)" stroke="{edge}" stroke-width="{outline_width}" stroke-opacity="{outline_opacity}" stroke-linejoin="round">{shapes}{lines}</g></svg>'''


def texture(light):
    base='#d7b080' if light else '#735039'
    lines=''
    for i in range(20):
        y=4+i*8
        lines+=f'<path d="M0 {y}C45 {y-5} 85 {y+7} 160 {y+1}" fill="none" stroke="{chr(35)+("704522" if light else "36251b")}" stroke-width="{.7+(i%3)*.3}" opacity=".24"/>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160"><title>Original wood grain</title><rect width="160" height="160" fill="{base}"/>{lines}</svg>'


def main():
    ROOT.mkdir(exist_ok=True)
    for theme in ('classic','wood','cyber'):
        folder=ROOT/theme;folder.mkdir(exist_ok=True)
        for color in ('white','black'):
            for kind in HEADS:
                (folder/f'{color}-{kind}.svg').write_text(make_piece(theme,color,kind))
    for light in (True,False):
        (ROOT/f'wood-{"light" if light else "dark"}.svg').write_text(texture(light))
    print('Created 36 original piece SVGs and two wood textures under',ROOT)


if __name__=='__main__': main()
