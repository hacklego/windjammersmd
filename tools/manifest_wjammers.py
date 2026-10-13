"""Where things live inside the Windjammers (Neo Geo, MAME set 'wjammers') ROMs.

This file contains only offsets and indexes discovered by reverse engineering --
no graphics, palettes or code from the game. Every byte of art is read from the
user's own ROM dump at build time.
"""

# ROM files identified by CRC32 (names are only fallbacks)
FILES = {
    'p1': (0x6692C140, ('065-p1.p1', '065-p1.bin')),
    'c1': (0xC7650204, ('065-c1.c1', '065-c1.bin')),
    'c2': (0xD9F3E71D, ('065-c2.c2', '065-c2.bin')),
    'c3': (0x40986386, ('065-c3.c3', '065-c3.bin')),
    'c4': (0x715E15FF, ('065-c4.c4', '065-c4.bin')),
    's1': (0x074B5723, ('065-s1.s1', '065-s1.bin')),
    'm1': (0x52C23CFC, ('065-m1.m1', '065-m1.bin')),
    'v1': (0xCE8B3698, ('065-v1.v1', '065-v1.bin')),
    'v2': (0x659F9B96, ('065-v2.v2', '065-v2.bin')),
    'v3': (0x39F73061, ('065-v3.v3', '065-v3.bin')),
    'v4': (0x5DEE7963, ('065-v4.v4', '065-v4.bin')),
}

# Palette table: palette n (as used in sprite attributes) is 16 words at PALETTES + n*32
PALETTES = 0x30000

# Full-screen court tilemap records (format 0x20nn, 22 columns x 14 tiles).
# Column k is drawn at screen x = 16*k - 16, so columns 1..20 cover the 320px screen.
COURTS = [
    ('lawn',     0x3B0AE),
    ('beach',    0x3C72A),
    ('tiled',    0x3EC90),
    ('wood',     0x3F192),
    ('clay',     0x43A92),
    ('stadium',  0x4D19C),
]

# ---------------------------------------------------------------------------
# Characters. Animations are lists of (frame, duration_in_60Hz_ticks); a frame is
# (pointer table, index) into the game's frame-record pointer tables. Sequences were
# recorded from the real game with tools/re/capture_anims.lua + match_anims.py.
# Frames face right (the left-hand player); the engine mirrors them for the right side.
# 'palette' is the game's palette number for player 1; player 2 uses palette + 1.

def _seq(table, items):
    return [((table, f), d) for f, d in items]

def _run(table, first, n, d):
    return _seq(table, [(first + i, d) for i in range(n)])

T_MAIN, T_YOO_A, T_SCOTT_A, T_SCOTT_B, T_SCOTT_C, T_WESSEL = 0x3351C, 0x32EB0, 0x32108, 0x32170, 0x32484, 0x341B0

CHARACTERS = [
    dict(name='H.MITA', country='JAPAN', palette=0x2A, speed=4, power=2, anims=dict(
        idle=_run(T_MAIN, 2, 8, 6),
        hold=_run(T_MAIN, 18, 8, 6),
        aim=_seq(T_MAIN, [(52, 8), (54, 8), (56, 8), (58, 8)]),
        throw=_seq(T_MAIN, [(68, 4), (70, 4), (72, 4), (74, 4), (75, 8), (76, 4)]),
        run_h=_run(T_MAIN, 26, 6, 5), run_up=_run(T_MAIN, 38, 6, 5), run_down=_run(T_MAIN, 32, 6, 5),
        catch=_seq(T_MAIN, [(112, 2), (113, 2), (114, 6), (113, 2)]))),
    dict(name='B.YOO', country='KOREA', palette=0x26, speed=3, power=3, anims=dict(
        idle=_run(T_YOO_A, 10, 8, 4),
        hold=_run(T_YOO_A, 26, 8, 4),
        aim=_run(T_YOO_A, 63, 8, 4),
        throw=_seq(T_YOO_A, [(85, 4), (87, 4), (89, 4), (90, 4), (91, 8), (92, 4)]),
        run_h=_run(T_YOO_A, 40, 6, 6), run_up=_run(T_YOO_A, 34, 6, 6), run_down=_run(T_YOO_A, 46, 6, 6),
        catch=_seq(T_YOO_A, [(136, 2), (137, 2), (138, 6), (137, 2)]))),
    dict(name='J.COSTA', country='SPAIN', palette=0x22, speed=3, power=3, anims=dict(
        idle=_run(T_MAIN, 276, 6, 4),
        hold=_seq(T_MAIN, [(282, 4), (283, 4), (284, 4), (285, 4), (286, 8)]),
        aim=_seq(T_MAIN, [(312, 8), (314, 8), (316, 8), (314, 8)]),
        throw=_seq(T_MAIN, [(330, 4), (332, 4), (334, 4), (336, 4), (338, 8), (339, 4)]),
        run_h=_run(T_MAIN, 294, 6, 6), run_up=_run(T_MAIN, 300, 6, 6), run_down=_run(T_MAIN, 306, 6, 6),
        catch=_seq(T_MAIN, [(380, 2), (381, 2), (382, 6), (381, 2)]))),
    dict(name='L.BIAGGI', country='ITALY', palette=0x28, speed=2, power=4, anims=dict(
        idle=_seq(T_MAIN, [(512, 8), (513, 4), (514, 4), (515, 8), (514, 4), (513, 4)]),
        hold=_seq(T_MAIN, [(516, 8), (517, 4), (518, 4), (519, 8), (518, 4), (517, 4)]),
        aim=_seq(T_MAIN, [(544, 10), (545, 10), (544, 10), (546, 10)]),
        throw=_seq(T_MAIN, [(550, 4), (552, 4), (554, 4), (556, 4), (557, 8), (558, 4)]),
        run_h=_run(T_MAIN, 526, 6, 6), run_up=_run(T_MAIN, 520, 6, 6), run_down=_run(T_MAIN, 532, 6, 6),
        catch=_seq(T_MAIN, [(550, 6), (516, 8)]))),          # TODO: capture the real catch
    dict(name='G.SCOTT', country='U.K.', palette=0x20, speed=3, power=3, anims=dict(
        idle=_seq(T_SCOTT_A, [(0, 8), (3, 4), (4, 4), (5, 4), (3, 4), (2, 4), (1, 4)]),
        hold=_seq(T_SCOTT_A, [(6, 8), (9, 4), (10, 4), (11, 4), (9, 4), (8, 4), (7, 4)]),
        aim=_seq(T_SCOTT_B, [(18, 8), (19, 8), (20, 8), (19, 8)]),
        throw=_seq(T_SCOTT_C, [(0, 4), (1, 4), (2, 4), (4, 4), (5, 8), (6, 4)]),
        run_h=_run(T_SCOTT_B, 12, 6, 6), run_up=_run(T_SCOTT_B, 6, 6, 6), run_down=_run(T_SCOTT_B, 0, 6, 6),
        catch=_seq(T_SCOTT_C, [(0, 6)]) + _seq(T_SCOTT_A, [(6, 8)]))),   # TODO: capture the real catch
    dict(name='K.WESSEL', country='GERMANY', palette=0x24, speed=1, power=5, anims=dict(
        idle=_seq(T_WESSEL, [(43, 12), (44, 4), (45, 12), (44, 4)]),
        hold=_seq(T_WESSEL, [(46, 12), (47, 4), (48, 12), (47, 4)]),
        aim=_seq(T_WESSEL, [(75, 8), (77, 8), (79, 8), (81, 8)]),
        throw=_seq(T_WESSEL, [(91, 4), (93, 4), (95, 4), (97, 4), (98, 8), (99, 4)]),
        run_h=_run(T_WESSEL, 55, 6, 6), run_up=_run(T_WESSEL, 49, 6, 6), run_down=_run(T_WESSEL, 61, 6, 6),
        catch=_seq(T_WESSEL, [(142, 2), (143, 2), (144, 6), (143, 2)]))),
]

# The game's own character numbers (its tables are indexed by them), in CHARACTERS order
GAME_ID = [5, 3, 1, 4, 0, 2]
# Running speed in px/frame by game id (measured from the game's RAM; diagonals are /sqrt 2)
RUN_SPEED = [1.5, 1.75, 1.25, 2.25, 2.0, 2.5]
# Throw speed tables (units of 1/32 px/frame): u16 power-throw window (frames held) per game id,
# then 16 speeds per game id indexed by frames held / 4; held 64+ frames: 0x60; power: 0x120
THROW_POWER_FRAMES = 0x28D44
THROW_SPEEDS = 0x28D50
# Curve throws (stick turned through a quarter circle, then A): per game id 2 words, the second
# the curve rate; each frame the disc's angle (256 = full turn, 16.16) changes by rate * speed,
# its sign the way the stick turned; on hitting a wall it flies straight on (+-16 after the
# bounce, the game's routine at 0x25EB2)
CURVE_TABLE = 0x27C2C

# Animations from the game's own scripts (frame numbers in the master frame table FRAMES_ALL,
# ticks per frame), one dict per character in CHARACTERS order. Found with tools/re scripts.
FRAMES_ALL = 0x32020
CHAR_ANIMS = [
    dict(  # Mita
        idle=[(0x5BE, 6), (0x5BF, 6), (0x5BE, 6), (0x5C0, 6), (0x5BF, 6), (0x5C1, 6), (0x5C0, 6), (0x5C1, 6)],
        hold=[(0x551, 6), (0x552, 6), (0x553, 6), (0x554, 6), (0x555, 6), (0x556, 6), (0x557, 6), (0x558, 6)],
        throw=[(0x583, 4), (0x585, 4), (0x587, 4), (0x589, 4), (0x58A, 4), (0x58A, 4), (0x58B, 4)],
        run_h=[(0x559, 5), (0x55A, 5), (0x55B, 5), (0x55C, 5), (0x55D, 5), (0x55E, 5)],
        run_up=[(0x565, 5), (0x566, 5), (0x567, 5), (0x568, 5), (0x569, 5), (0x56A, 5)],
        run_down=[(0x55F, 5), (0x560, 5), (0x561, 5), (0x562, 5), (0x563, 5), (0x564, 5)],
        catch=[(0x56B, 8), (0x56D, 8), (0x56F, 8), (0x571, 8)],
        slide_f=[(0x592, 2), (0x593, 2), (0x593, 2), (0x594, 2), (0x594, 2)],
        slide_up=[(0x58C, 2), (0x58D, 2), (0x58D, 2), (0x58E, 2), (0x58E, 2)],
        slide_down=[(0x598, 2), (0x599, 2), (0x599, 2), (0x59A, 2), (0x59A, 2)],
        lob=[(0x5AF, 2), (0x5B0, 2), (0x5B1, 2), (0x5B1, 2), (0x5B1, 2), (0x5B0, 2)],
        cheer=[(0x626, 6), (0x627, 6), (0x628, 6), (0x628, 6), (0x628, 6), (0x628, 6), (0x629, 6), (0x62A, 6), (0x62B, 6), (0x62C, 6), (0x629, 6), (0x62A, 6), (0x62B, 6), (0x62C, 6), (0x629, 6), (0x62A, 6), (0x62B, 6), (0x62C, 6), (0x629, 6), (0x62A, 6), (0x62B, 6), (0x62C, 6), (0x629, 6), (0x62A, 6), (0x62B, 6), (0x62C, 6), (0x629, 6), (0x62A, 6), (0x62B, 6), (0x62C, 6), (0x629, 6), (0x62A, 6), (0x62B, 6), (0x62C, 6), (0x629, 6), (0x62A, 6), (0x62B, 6), (0x62C, 6), (0x629, 6), (0x62A, 6)],
        sad=[(0x62D, 30), (0x62E, 30)],
        lose=[(0x61E, 6), (0x61E, 6), (0x61F, 6), (0x61F, 6), (0x620, 6), (0x620, 6), (0x621, 6), (0x621, 6), (0x622, 6), (0x623, 6), (0x624, 6), (0x625, 6), (0x622, 6), (0x623, 6), (0x624, 6), (0x625, 6), (0x622, 6), (0x623, 6), (0x624, 6), (0x625, 6), (0x622, 6), (0x623, 6), (0x624, 6), (0x625, 6), (0x622, 6), (0x623, 6), (0x624, 6), (0x625, 6), (0x622, 6), (0x623, 6), (0x624, 6), (0x625, 6), (0x622, 6), (0x623, 6), (0x624, 6), (0x625, 6), (0x622, 6), (0x623, 6), (0x624, 6), (0x625, 6)],
    ),
    dict(  # Yoo
        idle=[(0x3AE, 4), (0x3AF, 4), (0x3B0, 4), (0x3B1, 4), (0x3B2, 4), (0x3B3, 4), (0x3B4, 4), (0x3B5, 4)],
        hold=[(0x3BE, 4), (0x3BF, 4), (0x3C0, 4), (0x3C1, 4), (0x3C2, 4), (0x3C3, 4), (0x3C4, 4), (0x3C5, 4)],
        throw=[(0x3F9, 4), (0x3FB, 4), (0x3FD, 4), (0x3FE, 4), (0x3FF, 4), (0x3FF, 4), (0x400, 4)],
        run_h=[(0x3CC, 6), (0x3CD, 6), (0x3CE, 6), (0x3CF, 6), (0x3D0, 6), (0x3D1, 6)],
        run_up=[(0x3C6, 6), (0x3C7, 6), (0x3C8, 6), (0x3C9, 6), (0x3CA, 6), (0x3CB, 6)],
        run_down=[(0x3D2, 6), (0x3D3, 6), (0x3D4, 6), (0x3D5, 6), (0x3D6, 6), (0x3D7, 6)],
        catch=[(0x3BE, 4), (0x3BF, 4), (0x3C0, 4), (0x3C1, 4), (0x3C2, 4), (0x3C3, 4), (0x3C4, 4), (0x3C5, 4)],
        slide_f=[(0x405, 2), (0x406, 2), (0x407, 2), (0x407, 2), (0x408, 2), (0x408, 2)],
        slide_up=[(0x401, 2), (0x402, 2), (0x403, 2), (0x403, 2), (0x404, 2), (0x404, 2)],
        slide_down=[(0x411, 2), (0x412, 2), (0x413, 2), (0x413, 2), (0x414, 2), (0x414, 2)],
        lob=[(0x42C, 2), (0x42D, 2), (0x42E, 2), (0x42E, 2), (0x42E, 2), (0x42D, 2)],
        cheer=[(0x49D, 6), (0x49E, 6), (0x49F, 6), (0x4A0, 6), (0x49D, 6), (0x4A1, 6), (0x4A2, 6), (0x4A3, 6), (0x49D, 6), (0x49E, 6), (0x49F, 6), (0x4A0, 6), (0x49D, 6), (0x4A1, 6), (0x4A2, 6), (0x4A3, 6), (0x49D, 6), (0x49E, 6), (0x49F, 6), (0x4A0, 6), (0x49D, 6), (0x4A1, 6), (0x4A2, 6), (0x4A3, 6), (0x49D, 6), (0x49E, 6), (0x49F, 6), (0x4A0, 6), (0x49D, 6), (0x4A1, 6), (0x4A2, 6), (0x4A3, 6), (0x49D, 6), (0x49E, 6), (0x49F, 6), (0x4A0, 6), (0x49D, 6), (0x4A1, 6), (0x4A2, 6), (0x4A3, 6)],
        sad=[(0x4A4, 30), (0x4A5, 30)],
        lose=[(0x497, 6), (0x498, 6), (0x499, 6), (0x497, 6), (0x498, 6), (0x499, 6), (0x49A, 6), (0x49C, 6), (0x49C, 6), (0x49C, 6), (0x49B, 6), (0x49B, 6), (0x49B, 6), (0x49B, 6), (0x49B, 6), (0x49C, 6), (0x49C, 6), (0x49C, 6), (0x49B, 6), (0x49B, 6), (0x49B, 6), (0x49B, 6), (0x49B, 6), (0x49C, 6), (0x49C, 6), (0x49C, 6), (0x49B, 6), (0x49B, 6), (0x49B, 6), (0x49B, 6), (0x49B, 6), (0x49C, 6), (0x49C, 6), (0x49C, 6), (0x49B, 6), (0x49B, 6), (0x49B, 6), (0x49B, 6), (0x49B, 6), (0x49C, 6)],
    ),
    dict(  # Costa
        idle=[(0x6C4, 4), (0x6C5, 4), (0x6C6, 4), (0x6C7, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4), (0x6C8, 4), (0x6C9, 4)],
        hold=[(0x659, 4), (0x65A, 4), (0x65B, 4), (0x65C, 4), (0x65D, 4), (0x65E, 4)],
        throw=[(0x689, 4), (0x68B, 4), (0x68D, 4), (0x68F, 4), (0x691, 4), (0x691, 4), (0x692, 4)],
        run_h=[(0x665, 6), (0x666, 6), (0x667, 6), (0x668, 6), (0x669, 6), (0x66A, 6)],
        run_up=[(0x66B, 6), (0x66C, 6), (0x66D, 6), (0x66E, 6), (0x66F, 6), (0x670, 6)],
        run_down=[(0x671, 6), (0x672, 6), (0x673, 6), (0x674, 6), (0x675, 6), (0x676, 6)],
        catch=[(0x67D, 8), (0x67F, 8), (0x681, 8), (0x67F, 8)],
        slide_f=[(0x69B, 2), (0x69C, 2), (0x69C, 2), (0x69D, 2), (0x69D, 2), (0x69E, 2), (0x69E, 2), (0x69E, 2)],
        slide_up=[(0x693, 2), (0x694, 2), (0x694, 2), (0x695, 2), (0x695, 2), (0x696, 2), (0x696, 2), (0x696, 2)],
        slide_down=[(0x6A3, 2), (0x6A4, 2), (0x6A4, 2), (0x6A5, 2), (0x6A5, 2), (0x6A6, 2), (0x6A6, 2), (0x6A6, 2)],
        lob=[(0x6BB, 2), (0x6BC, 2), (0x6BD, 2), (0x6BD, 2), (0x6BD, 2), (0x6BC, 2)],
        cheer=[(0x884, 8), (0x885, 8), (0x886, 8), (0x887, 8), (0x888, 8)],
        sad=[(0x870, 30), (0x871, 30)],
        lose=[(0x889, 6), (0x889, 6), (0x88A, 6), (0x88B, 6), (0x88A, 6), (0x88B, 6), (0x88A, 6), (0x88B, 6)],
    ),
    dict(  # Biaggi
        idle=[(0x7A0, 4), (0x7A1, 4), (0x7A2, 4), (0x7A3, 4), (0x7A4, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4), (0x7A5, 4), (0x7A6, 4)],
        hold=[(0x73F, 4), (0x73F, 4), (0x740, 4), (0x741, 4), (0x742, 4), (0x742, 4), (0x741, 4), (0x740, 4)],
        throw=[(0x765, 4), (0x767, 4), (0x769, 4), (0x76B, 4), (0x76C, 4), (0x76C, 4), (0x76D, 4)],
        run_h=[(0x74D, 6), (0x74E, 6), (0x74F, 6), (0x750, 6), (0x751, 6), (0x752, 6)],
        run_up=[(0x747, 6), (0x748, 6), (0x749, 6), (0x74A, 6), (0x74B, 6), (0x74C, 6)],
        run_down=[(0x753, 6), (0x754, 6), (0x755, 6), (0x756, 6), (0x757, 6), (0x758, 6)],
        catch=[(0x759, 10), (0x75B, 10), (0x759, 10), (0x75D, 10)],
        slide_f=[(0x776, 2), (0x777, 2), (0x777, 2), (0x778, 2), (0x778, 2), (0x779, 2), (0x779, 2)],
        slide_up=[(0x76E, 2), (0x76F, 2), (0x76F, 2), (0x770, 2), (0x770, 2), (0x771, 2), (0x771, 2)],
        slide_down=[(0x77E, 2), (0x77F, 2), (0x77F, 2), (0x780, 2), (0x780, 2), (0x781, 2), (0x781, 2)],
        lob=[(0x796, 2), (0x797, 2), (0x798, 2), (0x798, 2), (0x798, 2), (0x797, 2)],
        cheer=[(0x7F5, 8), (0x7F6, 8), (0x7F7, 8), (0x7F8, 8), (0x7F9, 8), (0x7FA, 8), (0x7FB, 8), (0x7FC, 8), (0x7FD, 8)],
        sad=[(0x800, 30), (0x7FF, 30)],
        lose=[(0x7F0, 6), (0x7F0, 6), (0x7F1, 6), (0x7F2, 6), (0x7F3, 6), (0x7F3, 6), (0x7F3, 6), (0x7F4, 6), (0x7F3, 6)],
    ),
    dict(  # Scott
        idle=[(0x2B6, 4), (0x2B7, 4), (0x2B6, 4), (0x2B8, 4), (0x2B7, 4), (0x2B9, 4), (0x2B8, 4), (0x2B9, 4)],
        hold=[(0x3A, 4), (0x3A, 4), (0x3D, 4), (0x3E, 4), (0x3F, 4), (0x3D, 4), (0x3C, 4), (0x3B, 4)],
        throw=[(0x119, 4), (0x11A, 4), (0x11C, 4), (0x11D, 4), (0x11E, 4), (0x11E, 4), (0x11F, 4)],
        run_h=[(0x60, 6), (0x61, 6), (0x62, 6), (0x63, 6), (0x64, 6), (0x65, 6)],
        run_up=[(0x5A, 6), (0x5B, 6), (0x5C, 6), (0x5D, 6), (0x5E, 6), (0x5F, 6)],
        run_down=[(0x54, 6), (0x55, 6), (0x56, 6), (0x57, 6), (0x58, 6), (0x59, 6)],
        catch=[(0x69, 8), (0x6A, 8), (0x6B, 8), (0x6A, 8)],
        slide_f=[(0x128, 2), (0x129, 2), (0x129, 2), (0x12A, 2), (0x12A, 2), (0x12B, 2), (0x12B, 2), (0x12B, 2)],
        slide_up=[(0x120, 2), (0x121, 2), (0x121, 2), (0x122, 2), (0x122, 2), (0x123, 2), (0x123, 2), (0x123, 2)],
        slide_down=[(0x130, 2), (0x131, 2), (0x131, 2), (0x132, 2), (0x132, 2), (0x133, 2), (0x133, 2), (0x133, 2)],
        lob=[(0x14E, 2), (0x150, 2), (0x14F, 2), (0x14F, 2), (0x14F, 2), (0x150, 2)],
        cheer=[(0x321, 6), (0x322, 6), (0x323, 6), (0x324, 6), (0x325, 6)],
        sad=[(0x326, 30), (0x327, 30)],
        lose=[(0x31A, 4), (0x31B, 4), (0x31C, 4), (0x31C, 4), (0x31D, 4), (0x31E, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4), (0x31F, 4), (0x320, 4)],
    ),
    dict(  # Wessel
        idle=[(0x8F8, 4), (0x8F9, 4), (0x8F8, 4), (0x8F9, 4), (0x8FA, 4), (0x8F9, 4), (0x8FA, 4), (0x8FB, 4)],
        hold=[(0x88F, 4), (0x890, 4), (0x891, 4), (0x891, 4), (0x891, 4), (0x890, 4), (0x88F, 4), (0x88F, 4)],
        throw=[(0x8BF, 4), (0x8C1, 4), (0x8C3, 4), (0x8C5, 4), (0x8C6, 4), (0x8C6, 4), (0x8C7, 4)],
        run_h=[(0x89B, 6), (0x89C, 6), (0x89D, 6), (0x89E, 6), (0x89F, 6), (0x8A0, 6)],
        run_up=[(0x895, 6), (0x896, 6), (0x897, 6), (0x898, 6), (0x899, 6), (0x89A, 6)],
        run_down=[(0x8A1, 6), (0x8A2, 6), (0x8A3, 6), (0x8A4, 6), (0x8A5, 6), (0x8A6, 6)],
        catch=[(0x8B7, 8), (0x8B9, 8), (0x8BB, 8), (0x8BD, 8)],
        slide_f=[(0x8D0, 2), (0x8D1, 2), (0x8D1, 2), (0x8D2, 2), (0x8D2, 2), (0x8D3, 2), (0x8D3, 2), (0x8D3, 2)],
        slide_up=[(0x8C8, 2), (0x8C9, 2), (0x8C9, 2), (0x8CA, 2), (0x8CA, 2), (0x8CB, 2), (0x8CB, 2), (0x8CB, 2)],
        slide_down=[(0x8D8, 2), (0x8D9, 2), (0x8D9, 2), (0x8DA, 2), (0x8DA, 2), (0x8DB, 2), (0x8DB, 2), (0x8DB, 2)],
        lob=[(0x8F2, 2), (0x8F3, 2), (0x8F4, 2), (0x8F4, 2), (0x8F4, 2), (0x8F3, 2)],
        cheer=[(0x959, 8), (0x95A, 8), (0x95B, 8), (0x95C, 8), (0x95C, 8), (0x95C, 8), (0x95C, 8), (0x95D, 8), (0x95E, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8), (0x960, 8), (0x95F, 8)],
        sad=[(0x968, 30), (0x969, 30)],
        lose=[(0x961, 10), (0x962, 10), (0x963, 10), (0x964, 10), (0x965, 10), (0x966, 10), (0x965, 10), (0x967, 10), (0x965, 10), (0x966, 10), (0x965, 10), (0x967, 10), (0x965, 10), (0x966, 10), (0x965, 10), (0x967, 10), (0x965, 10), (0x966, 10), (0x965, 10), (0x967, 10), (0x965, 10), (0x966, 10), (0x965, 10), (0x967, 10), (0x965, 10), (0x966, 10), (0x965, 10), (0x967, 10), (0x965, 10), (0x966, 10), (0x965, 10), (0x967, 10), (0x965, 10), (0x966, 10), (0x965, 10), (0x967, 10), (0x965, 10), (0x966, 10), (0x965, 10), (0x967, 10)],
    ),
]

# Order of animations as the engine indexes them (src/chardata.h)
ANIM_ORDER = ['idle', 'hold', 'aim', 'throw', 'run_h', 'run_up', 'run_down', 'catch',
              'slide_f', 'slide_up', 'slide_down', 'lob', 'cheer', 'sad', 'lose']
for _ch, _an in zip(CHARACTERS, CHAR_ANIMS):
    _ch['anims'] = {k: [((FRAMES_ALL, f), d) for f, d in v] for k, v in _an.items()}
    _ch['anims']['aim'] = _ch['anims']['hold']

# Character profile cards (0x20nn records, 256x224), in CHARACTERS order
CARDS = [0x50D40, 0x51DDE, 0x4FEA8, 0x5099A, 0x4FB02, 0x5024E]

# Full-screen backgrounds: list of layers (record, crop_x, crop_y, paste_x, paste_y) composited in order
SCREENS = [
    ('vs',     [(0x3A004, 0, 0, 0, 0)]),
    ('ending', [(0x517C2, 0, 0, 0, 0)]),
]

# Fix-layer font: tile = FONT_BASE + ASCII code
FONT_BASE = 0x300

# Disc: in-flight spin and super-shot fireball (the held disc is part of the character frames)
DISC_FLY = [(0x32048, i) for i in range(38, 46)]
FIREBALL = [(0x3351C, i) for i in range(121, 125)]

# ---------------------------------------------------------------------------
# Sound. The original Z80 driver takes two-byte commands (found by disassembling its NMI
# handler and replaying the game's own command stream in tools/snd/sndsim.c):
#   17 nn  start music track nn          18 nn  play effect nn (one ADPCM-A sample)
# Which track/effect belongs to which moment was measured from MAME captures of the game;
# entries marked "guess" were not observed in context.
# name -> (command bytes, seconds to record, looping)
MUSIC = {
    'mus_eyecatch': ([0x02], 8, False),           # Neo Geo logo jingle (sent by the BIOS)
    'mus_menu':     ([0x17, 0x02], 150, True),    # menus (game sends it on its select screens)
    'mus_vs':       ([0x17, 0x03], 6, False),     # before a match
    'mus_match':    ([0x17, 0x0F], 320, True),    # match theme (same on the courts observed)
    'mus_set':      ([0x17, 0x05], 4, False),     # end of a set
    'mus_bonus':    ([0x17, 0x1C], 12, False),    # bonus game (frisbee dog)
    'mus_gameover': ([0x17, 0x0D], 8, False),     # game over / continue
}
# name -> command bytes; the first sample the driver triggers for it is used
SAMPLE_SFX = {
    'SFX_THROW':  [0x18, 0x51],   # seen with the throw animation
    'SFX_CATCH':  [0x18, 0x55],
    'SFX_BOUNCE': [0x18, 0x53],
    'SFX_GOAL':   [0x18, 0x2C],   # seen when a point is scored
    'SFX_CROWD':  [0x18, 0x54],
    'SFX_SERVE':  [0x18, 0x70],
    'SFX_LOB':    [0x18, 0x5A],   # guess
    'SFX_DASH':   [0x18, 0x67],   # guess (seen while running)
    'SFX_PANT':   [0x18, 0x6E],   # DOG DISTANCE: the dog running back
    'SFX_GOAL5':  [0x18, 0x2D],   # crowd after a 5-point goal
    'SFX_GOAL2':  [0x18, 0x2E],   # crowd after 2 points (disc dropped)
    'SFX_CALL3':  [0x18, 0x30],   # announcer after a 3-point goal
    'SFX_CALL5':  [0x18, 0x2F],   # announcer after a 5-point goal
    'SFX_CALL2':  [0x18, 0x31],   # announcer after 2 points
    'SFX_SETWIN': [0x18, 0x02],   # set over ("SET COUNTS")
    'SFX_SETEND': [0x18, 0x03],
    'SFX_TIMEUP': [0x18, 0x16],   # time up
    'SFX_POWER':  [0x18, 0x5C],   # power throw (quick return)
    'SFX_BEEP':   [0x18, 0x68],   # bonus game count down
    'SFX_GO':     [0x18, 0x1A],   # "GO!"
    'SFX_BARK':   [0x18, 0x60],   # the dog
    'SFX_FLY':    [0x18, 0x59],   # frisbee thrown
    'SFX_WHOOSH': [0x18, 0x7C],
    'SFX_MOVE':   [0x18, 0x64],   # select-screen tick
    'SFX_SELECT': [0x18, 0x66],   # select-screen confirm
    'SFX_YELP':   [0x18, 0x7D],   # DOG DISTANCE: the dog trips
    'SFX_WHINE':  [0x18, 0x5D],   # the dog sits without the disc
    'SFX_YAP':    [0x18, 0x6B],   # the dog sits with the disc
    'SFX_KYAA':   [0x18, 0x2B],   # a sunbather the dog runs into
    'SFX_OUCH':   [0x18, 0x29],   # the man in the sand
}

# ---------------------------------------------------------------------------
# Recordings. At build time tools/ngrec runs the original game (68000 + Z80 + video chip,
# with the MVS BIOS) and records what it shows; tools/mkmovies.py turns scenes of those
# recordings into Mega Drive movies. Only frame numbers and markers live here.
BIOS_FILES = {
    'bios': (0x9036D879, ('sp-s2.sp1',)),       # MVS BIOS (Europe, MAME's default)
    'sfix': (0xC2EA0CFD, ('sfix.sfix',)),       # BIOS fix-layer font
    'lo':   (0x5A86CFF2, ('000-lo.lo',)),       # sprite shrink table
}
# Arcade texts swapped for home-console ones while recording ('?' matches any character)
TEXT_SUBST = ['INSERT COIN=PRESS START', 'CREDIT ??=', 'LEVEL-?=', 'P2 WAIT=']

# name -> frames to emulate, input script lines ("first last key[,key]", see tools/ngrec)
RECORDINGS = {
    'attract': dict(frames=24000, inputs=[]),
    # VS COMPUTER and a character: the court roulette follows
    'court': dict(frames=2100, inputs=['1300 1305 coin1', '1400 1405 start1', '1500 1504 a', '1620 1624 a',
                                       '1740 1744 a']),
    # two credits, start, skip the tutorial, 1P VS 2P: both players' cursors on the select screen
    'select': dict(frames=1702, inputs=['1300 1305 coin1', '1320 1325 coin1', '1400 1405 start1', '1500 1504 a',
                                        '1600 1603 down', '1640 1644 a']),
}

# 2P games with player 1 on character k and player 2 on k+1 (select grid order = CHARACTERS order;
# the cursors start on characters 0 and 1): their VS screens give every portrait on both sides
def _vs_inputs(k):
    t = (k + 1) % 6
    L = ['1300 1305 coin1', '1320 1325 coin1', '1400 1405 start1', '1500 1504 a', '1600 1603 down', '1640 1644 a']
    f = 1700
    if k & 1: L.append('%d %d right' % (f, f + 3)); f += 12
    for _ in range(k >> 1): L.append('%d %d down' % (f, f + 3)); f += 12
    L.append('1760 1764 a')
    f = 1700
    if not t & 1: L.append('%d %d p2.left' % (f, f + 3)); f += 12
    for _ in range(t >> 1): L.append('%d %d p2.down' % (f, f + 3)); f += 12
    L.append('1770 1774 p2.a')
    return L
for _k in range(6):
    RECORDINGS['vs%d' % _k] = dict(frames=2941, inputs=_vs_inputs(_k))
VS_FRAME = 2940

# A 2P match on each court (the court list is BEACH, LAWN, TILED, CONCRETE, CLAY, STADIUM; the
# cursor starts on BEACH): COURT_LIST_ROW[i] is the row of our COURTS[i]
COURT_LIST_ROW = [1, 0, 2, 3, 4, 5]
def _court_inputs(row, k=0):
    L = [l for l in _vs_inputs(k)]
    L += ['%d %d down' % (2000 + 30 * i, 2003 + 30 * i) for i in range(row)]
    return L + ['2200 2204 a', '2210 2214 p2.a']
for _i, _row in enumerate(COURT_LIST_ROW):
    RECORDINGS['court%d' % _i] = dict(frames=2900, inputs=_court_inputs(_row))
COURT_FRAME = 2880
COURT_HIDE_PALETTES = [(0x10, 0x2F)]                   # scoreboard digits, players, effects
COURT_HIDE_TILES = [(0x2D80, 0x2DFF), (0x5B00, 0x5DFF), (0x7BF0, 0x7BFF)]   # disc, shadows
COURT_BLANK_FIX = '0-39,2-5'                           # names, flags and scores at the top
FENCE_VRAM = [1920, 1920]                              # tile slots for a shaking fence (src/vram.h)
COURT_COLORS = [15, 7]                                 # palette 1: 8-15 are the HUD, disc, black, white

# Match HUD tiles: big score digits (C-ROM 0x30C4 + digit), TIME boxes (0x3090 + 30 - seconds),
# both in sprite palette 0x10; the fix-layer font (palette 0x0C) and flags (2x2 fix tiles,
# palette 0x0B) by character in CHARACTERS order. HUD_COLOR_ENTRIES: the two colours kept for it.
HUD_DIGIT_TILE, HUD_TIME_TILE, HUD_SPRITE_PAL = 0x30C4, 0x3090, 0x10
HUD_TIME_UP_TILE = 0x30BE                              # the TIME box once time is up
HUD_SET_BAR_TILES = (0x30C1, 0x30C0)                   # lit bar over a score: the player has a set
# last seconds of a set: TIME box on the fix layer (palette 0x0E), cells 18-21 x 3-6; halves of
# 2x4 tiles (by column): tens '0' '1' '3' 'U', units '0'-'9' 'P' (TIME UP)
HUD_BOX_PAL = 0x0E
HUD_BOX_TENS = [0x700, 0x708, 0x710, 0x718]
HUD_BOX_UNITS = [0x720 + 8 * d for d in range(11)]
HUD_FONT_PAL, HUD_FLAG_PAL = 0x0C, 0x0B
HUD_FLAG_TILES = [0x3A0, 0x3B8, 0x3B0, 0x3A4, 0x3A8, 0x3AC]
HUD_COLOR_ENTRIES = [0x10 * 16 + 3, 0x0C * 16 + 3]
_VS_NAME_L, _VS_NAME_R = dict(rect=(0, 148, 150, 156)), dict(rect=(160, 148, 320, 156))
_VS_PORT_L, _VS_PORT_R = dict(rect=(0, 58, 150, 66)), dict(rect=(160, 58, 320, 66))

# Still screens: one recorded frame (sprites in 'hide' left out, fix-layer cells in 'blank_fix'
# "c0-c1,r0-r1" emptied) plus sprite groups cut out of that frame (first-last Neo Geo sprite)
SCREEN_SHOTS = {
    'scr_select': dict(rec='select', frame=1700, hide=['73-76'], blank_fix=['34-35,4-5'],
                       sprites={'spr_1p': (73, 74), 'spr_2p': (75, 76)}),
    # VS screen: background and panels; portraits (own palettes 2 and 3) and country names per character
    'scr_vs': dict(rec='vs0', frame=VS_FRAME, npal=2, hide=[_VS_NAME_L, _VS_NAME_R, _VS_PORT_L, _VS_PORT_R]),
}
for _k in range(6):
    _t = (_k + 1) % 6
    SCREEN_SHOTS['vs_parts%d' % _k] = dict(rec='vs%d' % _k, frame=VS_FRAME, image=False, cram_from='scr_vs', sprites={
        'spr_vsport_l%d' % _k: dict(sel=_VS_PORT_L, own_palette=2), 'spr_vsport_r%d' % _t: dict(sel=_VS_PORT_R, own_palette=3),
        'spr_vsname_l%d' % _k: _VS_NAME_L, 'spr_vsname_r%d' % _t: _VS_NAME_R})

# Scenes are delimited by the sound commands the game sends, which keeps them right whatever
# the timing: a marker is (command bytes, occurrence, frame offset); occurrence counts from 0.
MOVIES = {
    'mv_neogeo':   dict(rec='attract', start=([0x02], 0, 0), end=([0x02], 0, 467)),
    'mv_dataeast': dict(rec='attract', start=([0x02], 0, 468), end=([0x02], 0, 607)),
    'mv_title':    dict(rec='attract', start=([0x02], 0, 608), end=([0x02], 0, 907), opts=dict(step=2)),  # 30 fps: ROM
}
# Court roulette, one full turn: labels give the court shown (our COURTS index) and whether the
# highlight bar is lit in each frame (it flashes)
MOVIES['mv_courtroll'] = dict(rec='court', start=2039, end=2086, loop=2039, labels=dict(
    court={(2039, 2046): 0, (2047, 2054): 2, (2055, 2062): 3, (2063, 2070): 4, (2071, 2078): 5, (2079, 2086): 1},
    lit={(f, f): 1 for f in range(2040, 2087, 2)}))
for _i in range(6):      # GO FOR BROKE! and one profile card per attract cycle
    MOVIES['mv_profile%d' % _i] = dict(rec='attract', start=([0x15], 2 * _i, 4), end=([0x17, 0x1C], _i, -2),
                                       opts=dict(step=2))      # 30 fps: ROM

# Sound commands heard in recordings -> Mega Drive sound (a MUSIC / SAMPLE_SFX name, or 'stop')
MOVIE_SOUND = {
    (0x02,): 'mus_eyecatch',
    (0x15,): 'stop',
}

# Character voices: the game picks them from a table in the P-ROM, [category][character]
# (8 bytes per category, characters in CHARACTERS order), each byte an effect number (18 nn).
VOICE_TABLE = 0x1B03E
VOICE_CATEGORIES = {        # what the game uses each category for (seen in recordings)
    'VOICE_SETWIN': 1,      # winning a set
    'VOICE_POWERCATCH': 3,  # catching a power shot
    'VOICE_SUPER': 4,       # super throw
    'VOICE_CHARGE': 6,      # power charge (catching a high disc)
    'VOICE_FIRE1': 7,       # holding a charged disc
    'VOICE_FIRE2': 8,
    'VOICE_CHARGE2': 9,
}

# A long 1P game with pseudo-random inputs (fixed seed, so the recording is always the same)
def _random_play():
    import random
    rnd = random.Random(7)
    L = ['1300 1305 coin1', '1400 1405 start1'] + ['%d %d a' % (f, f + 4) for f in range(1500, 3000, 120)]
    f = 3000
    dirs = ['up', 'down', 'left', 'right', 'up,left', 'down,left', 'up,right', 'down,right', None]
    while f < 20000:
        d = rnd.choice(dirs); n = rnd.randint(8, 40)
        if d: L.append('%d %d %s' % (f, f + n, d))
        if rnd.random() < 0.6:
            g = f + rnd.randint(0, n); L.append('%d %d %s' % (g, g + 3, rnd.choice(['a', 'a', 'a', 'b'])))
        f += n
    return L
RECORDINGS['play'] = dict(frames=27000, inputs=_random_play())

# Super shots seen in that game: character (CHARACTERS order) -> (first frame of the shot, thrower
# side). The disc path and the effects around the disc are recorded from there (tools/mkmovies.py).
SUPER_SHOTS = {
    0: (26269, 0),   # H.MITA   (disc state 0x2C)
    1: (19760, 0),   # B.YOO    (0x2A)
    2: (13131, 0),   # J.COSTA  (0x2E)
    3: (23040, 0),   # L.BIAGGI (0x30)
    4: (9874, 0),    # G.SCOTT  (0x24)
    5: (3131, 1),    # K.WESSEL (0x32)
}
SUPER_FX_PALETTES = '11-1f'      # sprite palettes the effects use
SUPER_FX_BOX = (-32, -56, 32, 8) # effect window around the disc position (x0, y0, x1, y1)

# Score banner shown after each point ("00-03"): the purple bar as the game draws it (12 sprite
# columns of 4 tiles at x = 64 + 16k, y = 88), the big digits (2 columns of 5 tiles: left column
# tile BANNER_DIGIT + 5 + 10d, right BANNER_DIGIT + 10d, at y = 72).
BANNER_PAL = 0x17
BANNER_BAR = [0x796D, 0x7979, 0x7979, 0x7979, 0x7979, 0x7975, 0x7971, 0x7979, 0x7979, 0x7979, 0x7979, 0x7979]
BANNER_DIGIT = 0x7905

# Frisbee dog bonus game as the attract mode shows it (first attract cycle): the beach is one
# 32-column sprite chain that repeats every 512 px; everything else is replayed from the
# recording (positions, animation frames, sound) by tools/mkmovies.py make_bonus.
BONUS_DEMO = dict(rec='attract', start=([0x17, 0x1C], 0, 0), end=([0x15], 1, -1), step=2)

# 2P matches on court 0 (cursor row 1) past set 1: in 'win' player 2 stays at the top while
# player 1 keeps throwing, so player 1 wins 2-0; in 'tie<k>' (player 1 on character k, player 2
# on k+1) both just throw and every set ends 0-0 (both get the set), then SET FINAL, SUDDEN
# DEATH and DRAW GAME (shown from about frame 8700 to 9130). 'lose1p': VS COMPUTER without
# touching the pad, the computer wins 2-0.
RECORDINGS['win'] = dict(frames=7300, inputs=_court_inputs(1) + ['2900 7000 p2.up'] +
                         ['%d %d a' % (f, f + 3) for f in range(2900, 7000, 40)])
for _k in range(6):
    _every = 50 if _k == 3 else 40          # (40 lets someone score in this pairing)
    RECORDINGS['tie%d' % _k] = dict(frames=8801, inputs=_court_inputs(1, _k) +
                                    ['%d %d a' % (f, f + 3) for f in range(2900, 9000, _every)])
RECORDINGS['lose1p'] = dict(frames=7081, inputs=RECORDINGS['court']['inputs'] + ['1900 1904 a'])

# Set start overlay: sprite chains as the game draws them, (first sprite x, y, palette) at the
# shot (recording, frame) of each group. Set 1 shows the "SET 1" panel, the goal value markers
# ("POINTS 3", "POINTS 5") and the "12 POINTS / 30 SEC" line; later sets only their panel:
# SET 2, SET FINAL (sets 1-1) or SUDDEN DEATH (2-2). Each group gets its own 4 colours.
SET_START = {
    'set1': (('court0', 2700), {'panel_set1': (80, 72, 0x1D), 'rules': (80, 168, 0xA3),
                                'l3': (15, 22, 0x19), 'l5': (15, 86, 0x19), 'r3': (243, 22, 0x19), 'r5': (243, 86, 0x19)}),
    'set2': (('win', 4640), {'panel_set2': (80, 72, 0x1D)}),
    'final': (('court0', 4850), {'panel_final': (80, 72, 0x1D)}),
    'sudden': (('tie0', 7120), {'panel_sudden': (23, 94, 0x05)}),
}

# 1P mode panel "ROUND r / SET s" (palette 0x1D, at 80,40 in 'lose1p' at 2640, where the goal
# markers and rules line are drawn as in 2P): one 10 x 7 tile picture for ROUND 1 SET 1 (column c
# from tile base + 7 * ROUND_COLS[c]) whose last 3 columns, the digit boxes, are swapped for a
# triple (tiles triples + 21 * ROUND_TRIPLES[(r, s)], columns descending) for the others. Split
# at y = 56 into the words, the round box (rounds 1-5, FINAL = 6) and the set box (1, 2, FINAL = 3).
ROUND_PANEL = dict(shot=('lose1p', 2640), pal=0x1D, pos=(80, 40), base=0x7567, triples=0x75AD,
                   cols=[6, 5, 4, 3, 2, 1, 0, 9, 8, 7],
                   triple_index={(1, 2): 0, (1, 3): 1, (2, 1): 2, (2, 2): 3, (2, 3): 4, (3, 1): 5, (3, 2): 6,
                                 (3, 3): 7, (4, 1): 8, (4, 2): 9, (4, 3): 10, (5, 1): 11, (5, 2): 12, (5, 3): 13,
                                 (6, 1): 14, (6, 2): 15, (6, 3): 16},
                   rules=(80, 168, 0xA3))

# Set end: the score banner plus "SET COUNTS" and each side's sets, chains (x, y, palette) at
# a shot: 1-0 in 'win' at 4360, 2-2 in 'tie0' at 7040, 3-3 at 8720.
SET_COUNTS = dict(label=(('win', 4360), (120, 124, 0x16)),
                  digits={0: (('win', 4360), (216, 124, 0x16)), 1: (('win', 4360), (56, 124, 0x16)),
                          2: (('tie0', 7040), (56, 124, 0x16)), 3: (('tie0', 8720), (56, 124, 0x16))})

# "n POINTS GOAL" ribbon that slides out of the goal after a score: 4 sprite columns of 3 tiles,
# column k from tile base - 3k (palette 0x19). Order: right goal 3, 5, left goal 3, 5.
GOAL_RIBBONS = [0x74FE, 0x7516, 0x752E, 0x7546]

# Match result over the court: the two portrait frames and WIN!/LOSE (or DRAW GAME) as the game
# draws them, (x, y, palette) of each chain at a shot; composed per layout into one plane A image
# (origin, size in px). The portraits are sprites at frame + RESULT_PORTRAIT_OFFSET: the winner's
# is the VS screen one, the loser's (and both in a draw) the 'tie<k>' ones at RESULT_TIE_FRAME.
RESULT_PARTS = {
    'frame_l': (('win', 7240), (43, 68, 0xA0)), 'frame_r': (('win', 7240), (149, 68, 0xA0)),
    'win_l': (('win', 7240), (26, 48, 0x15)), 'lose_r': (('win', 7240), (175, 51, 0x15)),
    'lose_l': (('lose1p', 7080), (33, 51, 0x15)), 'win_r': (('lose1p', 7080), (176, 48, 0x15)),
    'draw': (('tie0', 8720), (47, 34, 0x15)),
}
RESULT_LAYOUTS = {      # name: frame positions (left, right), texts at their own positions
    'p1win': (((43, 68), (149, 68)), ['win_l', 'lose_r']),
    'p2win': (((43, 68), (149, 68)), ['lose_l', 'win_r']),
    'draw': (((33, 58), (159, 58)), ['draw']),
}
RESULT_ORIGIN, RESULT_SIZE = (24, 32), (272, 128)
RESULT_PORTRAIT_OFFSET = ((18, 9), (14, 9))
RESULT_TIE_FRAME = 8800
for _k in range(6):
    SCREEN_SHOTS['res_parts%d' % _k] = dict(rec='tie%d' % _k, frame=RESULT_TIE_FRAME, image=False, cram_from='scr_vs', sprites={
        'spr_resport_l%d' % _k: dict(sel=dict(rect=(40, 60, 60, 75)), own_palette=2),
        'spr_resport_r%d' % ((_k + 1) % 6): dict(sel=dict(rect=(165, 60, 185, 75)), own_palette=3)})

# DOG DISTANCE, the bonus round after round 2 in 1P mode (recording 'dog': VS COMPUTER with player
# 1's score poked to 11 and the computer's to 0 every 20 frames so player 1 wins each round, then
# A pressed over and over in the bonus round: a power throw, 205 m). The game logic is ours
# (src/bonus.c, measured from the game's RAM); its sprites are cut from this recording:
# (palette, first tile) of each sprite chain, in sequences where they move or animate.
RECORDINGS['dog'] = dict(frames=14700, inputs=RECORDINGS['court']['inputs'] + ['1900 1904 a'] +
                         ['%d %d a' % (f, f + 2) for f in range(13500, 14600, 6)],
                         pokes=['2700-12900/20:100873=0b', '2700-12900/20:1008f3=00'])
DOG_GAME = dict(
    rec='dog', frames=(13440, 14700),
    dog=0xFD, disc=0x4F, shadow=(0x3F, 0x5BC8), flag=0x13, pole=(0x2E, 13440), girl=(0x4E, 13440, 13640),
    logo=(0x05, 13470),
    wag=(13440, 13600),             # the dog sitting by the thrower, wagging (sprites at 40,120)
    shadow_tile=0x2D8E, roll=[0x2D90 + k for k in range(8)],
    flags=[0x5FB7 + 6 * k for k in range(10)],      # 20, 40 .. 200 m
)

# DOG DISTANCE as played: the dog, the disc and the beach obstacles as the game draws them (scaled
# by height), cut per animation frame from passes of these recordings that each draw one kind of
# object (ngrec -O palettes, -K tiles), placed by the objects' RAM positions (dog 0x100C00, disc
# 0x100A00, obstacle 0x100C78). 'dogcut': a slow throw, the dog steered (runs, jumps, runs back,
# trips over the first sunbather), then held under the disc (ngrec -C) so that it catches it as
# it lands; 'dogpow': a power throw, the dog held on each obstacle in turn (they react), then
# under the disc, where it jumps and catches it in the air. 'dog' gives the dog sitting without
# the disc and the obstacles that were not touched.
_DOG_IN = RECORDINGS['court']['inputs'] + ['1900 1904 a']
_DOG_POKES = RECORDINGS['dog']['pokes']
RECORDINGS['dogcut'] = dict(frames=14600, pokes=_DOG_POKES, inputs=_DOG_IN + [
    '13720 13900 right', '13730 13732 a', '13800 13802 a', '13910 13912 a', '13960 14010 right', '14030 14090 left',
    '14100 14102 a', '14110 14130 up', '14140 14160 down', '14170 14250 right', '14180 14182 a', '14260 14262 a'],
    extra=['-C', '14300-14900:A06=C06', '-C', '14300-14900:A0A=C0A,16'])
RECORDINGS['dogpow'] = dict(frames=14560, pokes=_DOG_POKES, inputs=_DOG_IN + [
    '%d %d a' % (f, f + 2) for f in range(13630, 13661, 6)] + ['14344 14346 a', '14344 14420 right'],
    extra=['-C', '13700-14250:C7E=C06', '-C', '13700-14250:C82=C0A,12', '-C', '14250-14560:A06=C06',
           '-C', '14250-14560:A0A=C0A,16'])
DOG_PLAY = dict(
    recs={'dogcut': (13640, 14600), 'dogpow': (13640, 14560), 'dog': (13640, 14700)},
    passes={'dog': ['-O', 'FD-FD'], 'fly': ['-O', '4F-4F', '-K', '2DD0-2E4F'],
            'held': ['-O', '4F-4F', '-K', '0-2D7F', '-K', '2F00-FFFFF'], 'obst': ['-O', 'F2-F5'],
            'shadow': ['-O', '3F-3F']},     # the dog's shadow (frame 0xA00 here), smaller as it jumps
    fly_sizes=[5, 7, 9, 11, 13, 15],    # disc sizes kept (zoom e: width 4 (e + 1)); all 8 turns at 15, 4 below
)

# Ending (after ROUND FINAL in 1P; recording 'ending': the 'dog' pokes up to there): the picture
# above the staff pages, recorded with the text rows blanked, for plane B; each page's text as
# the fix layer shows it at the frames below (rows ENDING_ROWS); tune 17 1B plays.
RECORDINGS['ending'] = dict(frames=41601, inputs=RECORDINGS['court']['inputs'] + ['1900 1904 a'],
                            pokes=['2700-40000/20:100873=0b', '2700-40000/20:1008f3=00'])
ENDING = dict(rec='ending', picture=41330, blank='0-39,16-27', rows=(16, 27),
              pages=[40300, 40450, 40600, 40750, 40900, 41050, 41200, 41330], page_frames=152)
MUSIC['mus_ending'] = ([0x17, 0x1B], 25, False)

# RANKING TOP5 (attract, after the demo; our live table src/ranking.c): the arcade keeps it in
# work RAM (scores 0x100208, 4-byte BCD; names 0x100230, 4 bytes: big-font codes, tile 0x400 + code;
# faces 0x100258, words 0x9B6 + game character id), five 'D.E' entries 100000..60000 at power on.
# 'rankfaces' pokes the faces so that the two ranking screens of the attract show all six:
# characters 0-4 down the first one, 5 at the top of the second. The screen is the backdrop with
# the title (still, fix rows of the table blanked) plus, per entry, the big rank digit, the face
# (48 x 32 sprites at RANK_FACE_X, RANK_ROW_Y + 32 k), the score (2-row font, palette 0x0C, tiles
# 0xE00 / 0xF00 + ASCII) and the name (big font). New entries are made in the HUD ("NAME" and three
# big letters, P1's corner, 30 s) after a lost 1P match, or over the DATA EAST screen after the
# ending (scr_deend); letters cycle with left / right (RANK_LETTERS), A enters one, 'ED' ends.
RECORDINGS['rankfaces'] = dict(frames=6801, inputs=[], pokes=
    ['3300-3600/10:%x=%x' % (0x100259 + 2 * k, 0xB6 + k) for k in range(5)] + ['6500-6800/10:100259=bb'])
RANK_SHOTS = [('rankfaces', 3600, [0, 1, 2, 3, 4]), ('rankfaces', 6800, [5])]   # faces by game character id
RANK_FACE_X, RANK_ROW_Y = 84, 48
RANK_DEFAULT = [(100000, 'D.E', 0), (90000, 'D.E', 4), (80000, 'D.E', 1), (70000, 'D.E', 2), (60000, 'D.E', 3)]
RANK_LETTERS = [0x40 + 4 * k for k in range(26)] + [0xA8, 0xAC, 0xB0, 0xB4, 0x28, 0x2C, 0x30, 0x34, 0x38, 0xC0, 0xBC, 0xB8]
RANK_BLANK, RANK_END = 0x3C, 0xB8                       # an empty letter, 'ED'
SCREEN_SHOTS['scr_ranking'] = dict(rec='rankfaces', frame=3600, npal=2, hide=[dict(rect=(80, 40, 100, 200))],
                                   blank_fix=['0-39,6-28'])
SCREEN_SHOTS['scr_deend'] = dict(rec='ending', frame=41600, npal=2, blank_fix=['0-39,2-5'])

# GAME MODE SELECT as the original draws it ('select' recording at MENU_FRAME, cursor on VS
# COMPUTER): the screen for plane B with the arrow, the countdown digit and the credit line
# blanked; the arrow and the big digits (fix tiles, 2 x 2 each) drawn by us on plane A.
MENU_FRAME = 1560
MENU_BLANK = ['8-9,12-13', '8-9,16-17', '19-20,26-27', '0-39,28-29']
MENU_ARROW, MENU_DIGITS, MENU_FIX_PAL = 0x4CC, 0x400, 0x0A    # digit d: tiles MENU_DIGITS + 4d (TL, BL, TR, BR)
MENU_ARROW_ROWS, MENU_ARROW_COL, MENU_TIMER_CELL = (12, 16), 8, (19, 26)

# FLYING DISC BOWLING, the bonus round after round 4 in 1P mode (recording 'bowl': the 'dog' run
# continued). Our own game logic (src/bonus.c), with the original's numbers measured from RAM: the
# pins (objects 0x100C28 + 0x28 k: x +6, y +0xA) stand on a 16 px grid from (240, 168); the throw
# is the match's; the disc stops on the first pin it hits. Pictures: the lane and score sheet
# (BOWL_FRAME, everything that moves hidden by palette, the fix layer's texts blanked), the pin
# (standing, its shadow, tumbling), the pinsetter, the title, the sheet's marks (fix tiles, two
# rows each: spare, strike, G, -, /, 0-9) and the timer's big digits.
RECORDINGS['bowl'] = dict(frames=28900, inputs=RECORDINGS['court']['inputs'] + ['1900 1904 a'],
                          pokes=['2700-30000/20:100873=0b', '2700-30000/20:1008f3=00'])
BOWL = dict(rec='bowl', frame=26400, hide_palettes=[0xB6, 0x2A, 0x3F, 0xB0, 0x11, 0x4F, 0x05],
            blank=['0-39,3-9', '0-39,29-29'],
            pin_pal=0xB6, pin_tiles=dict(stand=0x2D6E, shadow=0x2D6F, tumble=[0x2D73, 0x2D75, 0x2D77]),
            machine=(26400, 0xB0), logo=(26280, 0x05),
            marks=(0x380, 16, 0x00), digits=0x400, digit_pal=0x0A,
            pins=[(240, 168), (256, 176), (256, 160), (272, 168), (272, 184), (272, 152),
                  (288, 176), (288, 160), (288, 192), (288, 144)])

# HOW TO PLAY: the original's instructions after Start (recording 'tut'): MOVEMENT, SLIDING &
# RECEIVING, STRAIGHT SHOT, CURVE SHOT, each a demonstration; the titles kept, the fix layer's
# other texts dropped (ours, for the Mega Drive's buttons, are printed over it). Labels: the page.
RECORDINGS['tut'] = dict(frames=3220, inputs=['1300 1305 coin1', '1400 1405 start1'],
                        extra=['-H', '1-50'])      # without its scrolling background (sprites 1-50)
MOVIES['mv_howto'] = dict(rec='tut', start=1414, end=3219,      # over a still copy, plane B
                          opts=dict(step=4, npal=2, pal_base=1, drop_fix=[(0, 0, 320, 16), (0, 32, 320, 224)]),
                          labels=dict(page={(1414, 1764): 0, (1765, 2443): 1, (2444, 2995): 2, (2996, 3219): 3}))
MENU_LETTERS = 0x440                        # the big font: letter c at 0x440 + 4 (c - 'A')
