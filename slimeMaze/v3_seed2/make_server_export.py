# make_server_export.py (Ryan 2026-08-17): assemble the exact server
# import set into server_export/ - buildALL replaces the segmented
# build/walls/lanterns/dome/floor/decor chains, and the removes are
# dropped entirely (no in-place wipe on the server). The segmented
# files STAY in slimemaze/ because the singleplayer datapack route
# still reads them. The exported .nms is filtered to declare only
# what is exported. Rerun after any re-emission (after
# make_buildall.py):  python make_server_export.py
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'slimemaze')
OUT = os.path.join(HERE, 'server_export')
DIR = os.path.join(OUT, 'slimemaze')

KEEP_CHAINS = re.compile(r'^(buildALL|grounds|slimegrounds)\d+\.msc$')
KEEP_SINGLE = {'splice.msc', 'fall.msc', '__init__.msc',
               'slimeblock.msc', 'spliceFx.msc', 'fallFx1.msc',
               'fallFx2.msc', 'scaryTitle.msc'}
DROP_DECL = re.compile(
    r'\s*(?:remove[a-zA-Z]*|build|walls|lanterns|dome|floor|decor)'
    r'\d+\(Player player\)\s*')

if os.path.isdir(OUT):
    shutil.rmtree(OUT)
os.makedirs(DIR)
n = 0
for f in sorted(os.listdir(SRC)):
    if KEEP_CHAINS.match(f) or f in KEEP_SINGLE:
        shutil.copy2(os.path.join(SRC, f), os.path.join(DIR, f))
        n += 1

nms = open(os.path.join(HERE, 'slimemaze.nms'),
           encoding='utf-8').read().splitlines()
kept = [l for l in nms
        if not (DROP_DECL.fullmatch(l) and 'buildALL' not in l)]
with open(os.path.join(OUT, 'slimemaze.nms'), 'w',
          newline='\n', encoding='utf-8') as fh:
    fh.write('\n'.join(kept) + '\n')

print('server_export: %d .msc files + slimemaze.nms '
      '(%d declarations dropped)' % (n, len(nms) - len(kept)))
