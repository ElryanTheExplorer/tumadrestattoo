#!/usr/bin/env python3
"""Build the web portfolio from raw media.

    python3 tools/build-portfolio.py

Reads   media/<Title>_<tag>_<tag>.../   (one folder = one tattoo, any number of photos/videos)
Writes  portfolio/<slug>/...            (web-sized WebP + MP4, all metadata/GPS stripped)
        portfolio/portfolio.js          (window.PORTFOLIO, loaded by index.html)

Folder names:  Darth-Vader_chrome_black-and-gray_realism
               └ title ┘  └──────── tags ─────────┘
Primary image: put "primary" anywhere in a file name (IMG_3237-primary.JPG). Otherwise the
               first file by name is used.
Loose files directly in media/ are skipped until they are moved into a tagged folder.

Needs ImageMagick (convert/identify) and ffmpeg. Re-running only converts new or changed files.
"""
import json, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'media'
OUT = ROOT / 'portfolio'

# Category tree. Order here is tile order on the site. Only categories with work show up.
# "cover": optional folder slug to force which piece represents the tile.
CATEGORIES = [
    {'id': 'chrome',      'n': 'Chrome',            's': []},
    {'id': 'freehand',    'n': 'Freehand',          's': [['lettering', 'Lettering'], ['gap', 'Gap fillers']]},
    {'id': 'coverup',     'n': 'Cover up / rework', 's': []},
    {'id': 'fineline',    'n': 'Fine line',         's': [['lettering', 'Lettering'], ['tiny', 'Tiny']]},
    {'id': 'sleeves',     'n': 'Sleeves',           's': []},
    {'id': 'healed',      'n': 'Healed',            's': []},
    {'id': 'color',       'n': 'Color',             's': [['stickers', 'Stickers'], ['realism', 'Realism'], ['traditional', 'Traditional'], ['cartoons', 'Cartoons']]},
    {'id': 'bng',         'n': 'Black and gray',    's': [['realism', 'Realism'], ['blackwork', 'Black work'], ['ornamental', 'Ornamental'], ['geometric', 'Geometric']]},
    {'id': 'flash',       'n': 'Flash',             's': [['matching', 'Matching']]},
    {'id': 'anime',       'n': 'Anime',             's': []},
    {'id': 'traditional', 'n': 'Traditional',       's': []},
    {'id': 'tribal',      'n': 'Tribal',            's': []},
    {'id': 'other',       'n': 'Other',             's': []},
]

# Spellings people will actually type in folder names -> ids above.
ALIASES = {
    'black-and-gray': 'bng', 'black-and-grey': 'bng', 'blackandgray': 'bng', 'black-gray': 'bng',
    'cartoon': 'cartoons', 'sticker': 'stickers', 'sleeve': 'sleeves',
    'cover-up': 'coverup', 'cover': 'coverup', 'rework': 'coverup',
    'fine-line': 'fineline', 'gap-filler': 'gap', 'gap-fillers': 'gap', 'filler': 'gap',
    'black-work': 'blackwork', 'geometry': 'geometric', 'trad': 'traditional',
}

PHOTO_EXT = {'.jpg', '.jpeg', '.png', '.heic', '.webp'}
VIDEO_EXT = {'.mp4', '.mov', '.m4v'}
THUMB_W, FULL_MAX = 720, 1600

TOPS = {c['id']: c for c in CATEGORIES}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"failed: {' '.join(map(str, cmd))}\n{r.stderr}")
    return r.stdout.strip()


def stale(src, dst):
    return not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime


def size_of(p):
    w, h = run(['identify', '-format', '%w %h', f'{p}[0]']).split()
    return int(w), int(h)


def taken_at(p):
    if p.suffix.lower() in PHOTO_EXT:
        d = run(['identify', '-format', '%[EXIF:DateTimeOriginal]', f'{p}[0]'])
    else:
        d = run(['ffprobe', '-v', 'error', '-show_entries', 'format_tags=creation_time',
                 '-of', 'default=nw=1:nk=1', str(p)])
    d = re.sub(r'[^0-9]', '', d)[:14]
    return d or str(int(p.stat().st_mtime))


def resolve(tags):
    """Folder tags -> category keys ('color', 'color/realism') + leftover keywords."""
    tops = [t for t in tags if t in TOPS]
    keys, keywords = [], []
    for t in tags:
        parents = [p for p in tops if t in (s[0] for s in TOPS[p]['s'])]
        if parents:
            keys += [f'{p}/{t}' for p in parents]
        elif t in TOPS:
            if not any(k.startswith(t + '/') for k in keys):
                keys.append(t)
        else:
            keywords.append(t)
    # a top that also got a subcategory is implied by it
    keys = [k for k in keys if '/' in k or not any(x.startswith(k + '/') for x in keys)]
    return list(dict.fromkeys(keys)), keywords


def photo(src, dst_dir, stem):
    thumb, full = dst_dir / f'{stem}-{THUMB_W}.webp', dst_dir / f'{stem}-{FULL_MAX}.webp'
    if stale(src, thumb):
        run(['convert', f'{src}[0]', '-auto-orient', '-resize', f'{THUMB_W}x>', '-strip', '-quality', '74', thumb])
    if stale(src, full):
        run(['convert', f'{src}[0]', '-auto-orient', '-resize', f'{FULL_MAX}x{FULL_MAX}>', '-strip', '-quality', '80', full])
    w, h = size_of(full)
    return {'type': 'photo', 'thumb': rel(thumb), 'src': rel(full), 'w': w, 'h': h}, [thumb, full]


def video(src, dst_dir, stem):
    mp4, poster = dst_dir / f'{stem}.mp4', dst_dir / f'{stem}-poster.webp'
    if stale(src, mp4):
        run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-map', '0:v:0', '-an', '-sn', '-dn',
             '-map_metadata', '-1', '-map_chapters', '-1',
             '-vf', "scale='min(720,iw)':-2", '-c:v', 'libx264', '-preset', 'slow', '-crf', '27',
             '-pix_fmt', 'yuv420p', '-movflags', '+faststart', mp4])
    if stale(src, poster):
        run(['ffmpeg', '-v', 'error', '-y', '-ss', '1', '-i', mp4, '-frames:v', '1',
             '-vf', f"scale='min({THUMB_W},iw)':-2", '-c:v', 'libwebp', '-quality', '74', poster])
    w, h = size_of(poster)
    return {'type': 'video', 'thumb': rel(poster), 'src': rel(mp4), 'w': w, 'h': h}, [mp4, poster]


def rel(p):
    return p.relative_to(ROOT).as_posix()


def build():
    OUT.mkdir(exist_ok=True)
    pieces, produced, notes = [], set(), []
    used = set()

    for f in sorted(p for p in SRC.iterdir() if p.is_file() and not p.name.startswith('.')):
        notes.append(f'skipped loose file media/{f.name} (move it into a tagged folder)')

    for folder in sorted(p for p in SRC.iterdir() if p.is_dir()):
        title, *raw = folder.name.split('_')
        tags = [ALIASES.get(t.lower(), t.lower()) for t in raw if t]
        keys, keywords = resolve(tags)
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        while slug in used:
            slug += '-2'
        used.add(slug)

        files = sorted((f for f in folder.iterdir() if f.suffix.lower() in PHOTO_EXT | VIDEO_EXT),
                       key=lambda f: ('primary' not in f.name.lower(), f.suffix.lower() in VIDEO_EXT, f.name))
        if not files:
            notes.append(f'{folder.name}: no photos or videos, skipped')
            continue
        dst = OUT / slug
        dst.mkdir(exist_ok=True)
        media = []
        for f in files:
            stem = re.sub(r'[-_ ]*primary[-_ ]*', '', f.stem, flags=re.I) or 'primary'
            item, outs = (photo if f.suffix.lower() in PHOTO_EXT else video)(f, dst, stem)
            media.append(item)
            produced.update(outs)
            print(f'  {folder.name}/{f.name}')

        if not keys:
            notes.append(f'{folder.name}: no tag matches a category, so it only appears under "View all"')
        if keywords:
            notes.append(f'{folder.name}: extra tags {keywords} (filterable, not categories)')
        pieces.append({
            'id': slug,
            'title': title.replace('-', ' ')[:1].upper() + title.replace('-', ' ')[1:],
            'cats': keys, 'tags': keywords, 'date': taken_at(files[0]), 'media': media,
        })

    pieces.sort(key=lambda p: p['date'], reverse=True)

    # Tile covers: newest piece per category, avoiding repeats across tiles where possible.
    cats, covered = [], set()
    for c in CATEGORIES:
        inside = [p for p in pieces if any(k == c['id'] or k.startswith(c['id'] + '/') for k in p['cats'])]
        if not inside:
            continue
        pick = next((p for p in inside if p['id'] == c.get('cover')), None) \
            or next((p for p in inside if p['id'] not in covered), inside[0])
        covered.add(pick['id'])
        cats.append({'id': c['id'], 'n': c['n'], 'cover': pick['id'],
                     's': [s for s in c['s'] if any(f"{c['id']}/{s[0]}" in p['cats'] for p in inside)]})

    data = {'categories': cats, 'pieces': pieces}
    (OUT / 'portfolio.js').write_text(
        '/* Generated by tools/build-portfolio.py — do not edit by hand. */\n'
        f'window.PORTFOLIO = {json.dumps(data, indent=1, ensure_ascii=False)};\n')
    produced.add(OUT / 'portfolio.js')

    for p in sorted(OUT.rglob('*'), reverse=True):  # drop output for media that was removed
        if p.is_file() and p not in produced:
            p.unlink(); print(f'  removed {rel(p)}')
        elif p.is_dir() and not any(p.iterdir()):
            p.rmdir()

    print(f'\n{len(pieces)} pieces, {sum(len(p["media"]) for p in pieces)} files, '
          f'{len(cats)} category tiles: {", ".join(c["n"] for c in cats)}')
    for n in notes:
        print('  note:', n)


if __name__ == '__main__':
    for tool in ('convert', 'identify', 'ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            sys.exit(f'{tool} not found — install ImageMagick and ffmpeg')
    build()
