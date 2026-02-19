"""
RPG / Roguelike terminal 
"""

import os, sys, time, random, re, ctypes, math
from collections import namedtuple, deque

if os.name == 'nt':
    import msvcrt

def _getch_timeout(timeout_sec=0.18):
    """Lit une touche avec timeout; retourne None si aucune touche."""
    timeout_sec = max(0.0, float(timeout_sec))
    if os.name == 'nt':
        end = time.time() + timeout_sec
        while time.time() < end:
            if msvcrt.kbhit():
                return msvcrt.getwch()
            time.sleep(0.01)
        return None
    import select
    r, _, _ = select.select([sys.stdin], [], [], timeout_sec)
    if r:
        return _getch_blocking()
    return None

def _getch_blocking():
    """Lit une touche immédiatement (Windows: msvcrt, Unix: termios)."""
    if os.name == 'nt':
        ch = msvcrt.getwch()  # unicode (gère z,q,s,d)
        return ch
    else:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return ch

def read_command(repeat_last_dir):
    """
    Retourne toujours un 2-tuple :
      ('move', (n, (dx,dy)))  ou  ('action', 'e'|'i'|'j'|'c'|'m'|'x'|None)
      ou ('quick_spell', index_1_based)
    """
    digits = ''
    buffered_ch = None
    while True:
        if buffered_ch is not None:
            ch = buffered_ch.lower()
            buffered_ch = None
        else:
            ch = _getch_blocking().lower()

        # ignorer retours chariot/escapes
        if ch in ('\r', '\n', '\x1b'):
            digits = ''
            continue

        # Raccourcis sorts (AZERTY rangée 1 sans passer par le grimoire)
        if ch in QUICK_SPELL_KEYS:
            return ('quick_spell', QUICK_SPELL_KEYS[ch])

        if ch.isdigit():
            # 1..0 en raccourcis sort (si touche seule), sinon nombre+direction pour déplacement.
            if not digits:
                peek = _getch_timeout(0.18)
                if peek is None:
                    slot = 10 if ch == '0' else int(ch)
                    return ('quick_spell', slot)
                digits = ch
                buffered_ch = peek
                continue
            digits += ch
            continue

        if ch == '.':
            if repeat_last_dir != (0,0):
                n = int(digits) if digits else 1
                return ('move', (n, repeat_last_dir))
            return ('action', None)

        if ch in DIR_KEYS:  # z/w, q/a, s, d
            n = int(digits) if digits else 1
            return ('move', (n, DIR_KEYS[ch]))

        if ch in ('e','i','j','c','m','x'):
            return ('action', ch)

        # (optionnel) support flèches/pavé numérique sous Windows
        if os.name == 'nt' and ch in ('\xe0', '\x00'):
            k = _getch_blocking()
            arrow_map = {'H':'z','P':'s','K':'q','M':'d'}  # ↑ ↓ ← →
            numpad_spell_map = {'O':1, 'Q':3, 'G':7, 'I':9, 'R':10}
            if k in arrow_map:
                n = int(digits) if digits else 1
                return ('move', (n, DIR_KEYS[arrow_map[k]]))
            if k in numpad_spell_map:
                return ('quick_spell', numpad_spell_map[k])
            continue

        # touche non gérée → on ignore et on ré-écoute
        digits = ''
        
# ========================== COULEURS ANSI ==========================
class Ansi:
    RESET = "\x1b[0m"; BOLD = "\x1b[1m"; DIM = "\x1b[2m"
    BLACK = "\x1b[30m"; RED = "\x1b[31m"; GREEN = "\x1b[32m"; YELLOW = "\x1b[33m"
    BLUE = "\x1b[34m"; MAGENTA = "\x1b[35m"; CYAN = "\x1b[36m"; WHITE = "\x1b[37m"
    BRIGHT_BLACK = "\x1b[90m"; BRIGHT_RED = "\x1b[91m"; BRIGHT_GREEN = "\x1b[92m"; BRIGHT_YELLOW = "\x1b[93m"
    BRIGHT_BLUE = "\x1b[94m"; BRIGHT_MAGENTA = "\x1b[95m"; BRIGHT_CYAN = "\x1b[96m"; BRIGHT_WHITE = "\x1b[97m"

SUPPORTS_ANSI = True
SHOW_SIDE_SPRITE = True
MAP_FRAME_ACTIVE = False

# Truecolor (RGB) — pour de vrais pastels si le terminal le supporte
USE_TRUECOLOR = True  # passe à False si rendu bizarre

def rgb(r,g,b): return f"\x1b[38;2;{r};{g};{b}m"
PASTEL = lambda r,g,b: rgb(r,g,b) if (SUPPORTS_ANSI and USE_TRUECOLOR) else Ansi.WHITE

THEMES = [
    # Classique
    {
        'name':'stone',
        'border': Ansi.BRIGHT_WHITE,
        'title':  Ansi.BRIGHT_YELLOW,
        'floor':  Ansi.DIM,             # points de sol
        'wall':   Ansi.BRIGHT_BLACK,
        'npc':    Ansi.BRIGHT_CYAN,
        'shop':   Ansi.BRIGHT_YELLOW,
        'up':     Ansi.BRIGHT_CYAN,
        'down':   Ansi.BRIGHT_MAGENTA,
        'elite':  Ansi.BRIGHT_RED,
        'item':   Ansi.BRIGHT_YELLOW,
        'player': Ansi.BRIGHT_GREEN,
    },
    # Pastel “mousse”
    {
        'name':'moss',
        'border': PASTEL(220,230,220),
        'title':  PASTEL(170,200,170),
        'floor':  PASTEL(150,170,150),
        'wall':   PASTEL(90,110,90),
        'npc':    PASTEL(120,190,210),
        'shop':   PASTEL(230,210,140),
        'up':     PASTEL(150,210,230),
        'down':   PASTEL(210,150,230),
        'elite':  PASTEL(230,120,120),
        'item':   PASTEL(230,210,140),
        'player': PASTEL(160,230,160),
    },
    # Pastel “ardoise”
    {
        'name':'slate',
        'border': PASTEL(220,220,235),
        'title':  PASTEL(180,180,220),
        'floor':  PASTEL(160,165,185),
        'wall':   PASTEL(100,105,125),
        'npc':    PASTEL(160,200,230),
        'shop':   PASTEL(230,200,150),
        'up':     PASTEL(150,200,230),
        'down':   PASTEL(210,160,230),
        'elite':  PASTEL(230,140,140),
        'item':   PASTEL(230,200,150),
        'player': PASTEL(170,220,190),
    },
    # Pastel “sable”
    {
        'name':'sand',
        'border': PASTEL(235,230,220),
        'title':  PASTEL(210,190,140),
        'floor':  PASTEL(210,200,185),
        'wall':   PASTEL(160,150,130),
        'npc':    PASTEL(160,200,210),
        'shop':   PASTEL(230,190,120),
        'up':     PASTEL(150,190,220),
        'down':   PASTEL(210,150,220),
        'elite':  PASTEL(220,110,110),
        'item':   PASTEL(230,190,120),
        'player': PASTEL(180,210,170),
    },
]

def enable_windows_ansi():
    """Active l'affichage ANSI sous Windows 10+"""
    global SUPPORTS_ANSI
    if os.name != 'nt':
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        SUPPORTS_ANSI = False

def c(text, *styles):
    if not SUPPORTS_ANSI:
        return str(text)
    return ''.join(styles) + str(text) + Ansi.RESET

# ========================== WIDGET D'ENCADREMENT ==========================
_ansi_re = re.compile(r"\x1b\[[0-9;]*m")

def visible_len(s: str) -> int:
    return len(_ansi_re.sub("", s))

def _cut_ansi_visible(s: str, max_visible: int):
    """Découpe s en (left, right) avec left contenant au plus max_visible chars visibles."""
    if max_visible <= 0:
        return "", s
    i = 0
    vis = 0
    while i < len(s) and vis < max_visible:
        m = _ansi_re.match(s, i)
        if m:
            i = m.end()
            continue
        if s[i] in ("\r", "\n"):
            break
        vis += 1
        i += 1
    return s[:i], s[i:]

def _pad_ansi_right(s: str, width: int) -> str:
    """Pad à droite en se basant sur la largeur visible (ignore les codes ANSI)."""
    return s + (' ' * max(0, int(width) - visible_len(s)))

def wrap_ansi(s: str, width: int) -> list[str]:
    # Wrap robuste: respecte \n et évite de couper les séquences ANSI.
    width = max(1, int(width))
    out = []
    cur = ""
    cur_vis = 0
    last_space_idx = -1
    i = 0
    while i < len(s):
        m = _ansi_re.match(s, i)
        if m:
            cur += m.group(0)
            i = m.end()
            continue
        ch = s[i]
        i += 1
        if ch == '\r':
            continue
        if ch == '\n':
            out.append(cur)
            cur = ""
            cur_vis = 0
            last_space_idx = -1
            continue
        cur += ch
        cur_vis += 1
        if ch.isspace():
            last_space_idx = len(cur)
        if cur_vis > width:
            if last_space_idx > 0:
                left = cur[:last_space_idx].rstrip()
                right = cur[last_space_idx:].lstrip()
                out.append(left)
                cur = right
            else:
                left, right = _cut_ansi_visible(cur, width)
                out.append(left)
                cur = right.lstrip()
            cur_vis = visible_len(cur)
            last_space_idx = -1
    if cur or not out:
        out.append(cur)
    return out

def draw_box(title: str, lines, width: int | None = None, border_style=None, title_style=None):
    if isinstance(lines, (str, bytes)):
        lines = [str(lines)]
    normalized_lines = []
    for x in lines:
        txt = str(x).replace('\r\n', '\n').replace('\r', '\n')
        normalized_lines.extend(txt.split('\n'))
    lines = normalized_lines

    # largeur mini/maxi + calcul auto selon contenu visible
    content_w = max((visible_len(l) for l in lines), default=0)
    title_text = f" {title} "
    target = max(60, content_w, visible_len(title_text), 100)
    width = max(60, min(200, width or target))  # ← max 200

    border_style = border_style or Ansi.BRIGHT_WHITE
    title_style = title_style or Ansi.BRIGHT_YELLOW

    top = '┌' + '─'*width + '┐'
    mid = '├' + '─'*width + '┤'
    bot = '└' + '─'*width + '┘'
    print(c(top, border_style))
    pad = max(0, width - visible_len(title_text))
    print(c('│', border_style) + c(title_text + ' '*pad, title_style) + c('│', border_style))
    print(c(mid, border_style))
    for ln in lines:
        for part in wrap_ansi(ln, width):
            pad = max(0, width - visible_len(part))
            print(c('│', border_style) + part + ' '*pad + c('│', border_style))
    print(c(bot, border_style))

# ========================== RENDU DU PERSONNAGE ==========================
def _tint_line_red(line: str, strong=False):
    # teinte toute la ligne ; strong = plus vif
    color = Ansi.BRIGHT_RED if strong else Ansi.RED
    return c(line, color)

def colorize_sprite_by_hp(sprite_lines, hp, max_hp):
    """
    Colore le sprite du BAS vers le HAUT en rouge selon la proportion de PV perdus.
    Plus on a peu de PV, plus de lignes en bas deviennent rouges (et les plus basses en BRIGHT_RED).
    """
    if max_hp <= 0:
        frac_lost = 1.0
    else:
        frac_lost = max(0.0, min(1.0, 1.0 - (hp / max_hp)))

    h = len(sprite_lines)
    # nb de lignes à teinter depuis le BAS (>= 0)
    red_rows = int(math.ceil(frac_lost * h))

    out = []
    for i, raw in enumerate(sprite_lines):
        # i = 0 en haut, h-1 en bas -> on teinte si i >= h - red_rows
        if i >= h - red_rows and red_rows > 0:
            # intensité : les 1/3 lignes les plus basses = bright
            # calcule la "profondeur" dans la zone rouge (0 en haut de la zone rouge, 1 tout en bas)
            depth = (i - (h - red_rows)) / max(1, red_rows - 1)
            strong = depth > 0.66
            out.append(_tint_line_red(raw, strong=strong))
        else:
            out.append(raw)  # pas de teinte
    return out

# ========================== PARAMÈTRES ==========================
MAP_W, MAP_H = 48, 20
FLOOR, WALL = '·', '#'
PLAYER_ICON, NPC_ICON, MON_ICON, ITEM_ICON, SHOP_ICON = '@','N','M','*','$'
STAIR_DOWN, STAIR_UP = '>', '<'
TREASURE_ICON = 'T'
TREASURE_BOSS_ICON = 'T'
ELITE_ICON = 'Ω'
CASINO_ICON = 'C'
ALTAR_ICON = '+'
LOCKED_DOOR_ICON = 'D'
SAGE_ICON = 'S'
HUD_CONTROLS = '[ZQSD/WASD] déplacer • E interagir • I inventaire • C stats • J journal • M grimoire • X quitter'
MENU_CONTROLS = "Commandes : ZQSD/WASD se déplacer • E interagir • I inventaire • C stats • J journal • M grimoire • X quitter"
QUICK_SPELL_KEYS = {
    '&': 1, 'é': 2, '"': 3, "'": 4, '(': 5, '-': 6,
    'è': 7, '_': 8, 'ç': 9, 'à': 10,
}

# ========================== BALANCE ==========================
BALANCE = {
    # COMBAT
    'combat_xp_mult':   0.60,   # % de l'XP habituelle
    'combat_gold_mult': 0.70,   # % de l'or habituel

    # LOOT après combat
    'loot_item_chance': 0.28,
    'loot_cons_chance': 0.30,

    # CARTE
    'map_items_per_floor': 2,
    'locked_rooms_per_floor': 1,
    'boss_locked_room_chance': 0.18,
    'normal_key_drop_chance': 0.06,
    'normal_key_shop_price': 70,
    'altar_spawn_chance': 0.14,
    'altar_on_boss_floor_chance': 0.68,

    # PNJ par étage (peut être 0)
    'npcs_min': 0,
    'npcs_max': 1,              # anciennement 2 fixes

    # NIVEAUX
    'level_xp_threshold': 40,   # au lieu de 30 (plus lent)
    'level_hp_gain': 3,         # au lieu de 6
    'level_atk_gain': 1,        # au lieu de 2
    'level_def_gain': 0.5,        # au lieu de 1

    # QUÊTES (récompenses)
    'quest_xp_mult':   0.70,
    'quest_gold_mult': 0.70,

    # Scaling par NIVEAU du joueur et par PROFONDEUR (étage)
    'mon_per_level':  {'hp': 0.11, 'atk': 0.09, 'def': 0.05},
    'mon_per_depth':  {'hp': 0.14, 'atk': 0.12, 'def': 0.07},

    # Soft cap : au-delà d’un certain niveau, la progression ennemie ralentit
    'mon_softcap_level': 8,
    'mon_softcap_mult':  0.45,  # après le softcap, les % sont multipliés par 0.45

    # Bonus des élites (en plus du scaling de base)
    'elite_bonus': {'hp': 0.40, 'atk': 0.25, 'def': 0.20},
    # Ajustements boss (légère baisse globale)
    'boss_stat_mult': {'hp': 0.90, 'atk': 0.92, 'def': 0.92},
    # Nerf léger des premiers boss (s'atténue avec la profondeur)
    'early_boss_nerf_until_depth': 10,
    'early_boss_nerf': {'hp': 0.18, 'atk': 0.14, 'def': 0.12},
    # Diable/dragon hors boss: plus rares
    'nonboss_diable_dragon_chance': 0.04,

    # Garde-fous de jouabilité (post-ajustement)
    'mon_max_atk_vs_player_hp': 0.45,  # ATK monstre ≤ 45% des PV max du joueur
    'mon_max_def_vs_player_atk': 0.85, # DEF monstre ≤ 85% de l’ATK du joueur (sinon combats trop longs)

    # Soin de 40% des PV max à chaque montée de niveau
    'level_heal_ratio': 0.40,
    
    # Régénération de PV par tour
    'regen_cap_flat': 5,      # plafond dur par tour (ex: 5 PV)
    'regen_cap_frac': 0.05,   # plafond % PV max par tour (ex: 5%)
    'regen_on_hit_mult': 0.5, # si on a pris des dégâts ce tour : regen × 0.5
    'regen_every_n_turns': 1, # 1 = chaque tour, 2 = un tour sur deux, etc.

    # Casino
    'casino_gamble_cost_base': 10,
    'casino_upgrade_cost_base': 30,
    'casino_upgrade_break_chance': 0.04,

    # Rareté (hors coffre boss): courbe plus lente pour que les communs restent utiles tôt.
    'rarity_base_weights': {'Commun': 88, 'Rare': 8, 'Épique': 0, 'Légendaire': 0, 'Étrange': 0},
    'rarity_depth_gain': {'Rare': 1.5, 'Épique': 0.8, 'Légendaire': 0.35, 'Étrange': 0.0},
    'rarity_min_depth': {'Rare': 1, 'Épique': 4, 'Légendaire': 9, 'Étrange': 999},

    # Coffres de boss: surtout Rare au début, puis montée progressive.
    'boss_rarity_base_weights': {'Rare': 78, 'Épique': 18, 'Légendaire': 0},
    'boss_rarity_depth_gain': {'Épique': 1.6, 'Légendaire': 1.0},
    'boss_rarity_min_depth': {'Épique': 5, 'Légendaire': 10},

    # Magie / Grimoire
    'spell_sage_start_depth': 3,
    'spell_sage_every': 5,
    'spell_drop_base_chance': 0.012,     # très rare
    'spell_drop_depth_bonus': 0.0012,
    'spell_shop_min_depth': 8,
    'spell_shop_offer_chance': 0.65,
    'mage_spell_shop_offer_bonus': 0.22,
    'mage_spell_shop_offer_cap': 0.92,
    'spell_shop_price_mult': 1.0,
    'summon_spell_cooldown_floors': 5,
    'sage_reroll_cost_base': 240,
    'sage_reroll_cost_depth_mult': 20,

    # Classe Mage
    'mage_magic_drop_chance_base': 0.14,
    'mage_magic_drop_chance_depth': 0.009,
    'mage_magic_drop_chance_cap': 0.34,
    'mage_magic_item_mult': 1.35,
    'mage_pouv_stat_pct': 0.055,
    'mage_pouv_per_level': 0.60,
    'mage_level_hp_mult': 0.90,
    'mage_level_atk_mult': 0.65,
    'mage_level_def_mult': 0.65,
    'mage_start_spell_slots': 3,
    'mage_spell_slot_every_levels': 2,
    'mage_level_pouv_gain': 1,
    'mage_pouv_gain_every_levels': 2,
    'mage_spell_drop_mult': 1.55,
    'mage_spell_drop_cap': 0.12,
    'mage_special_pouv_coeff': 0.010,
    'mage_special_damage_mult': 0.62,

    # Nerfs magie / invocation (scaling POUV)
    'spell_damage_base_lvl_coeff': 0.24,
    'spell_damage_base_pouv_coeff': 0.62,
    'spell_damage_mult_pouv_coeff': 0.020,
    'spell_heal_base_lvl_coeff': 0.30,
    'spell_heal_base_pouv_coeff': 0.55,
    'spell_heal_mult_pouv_coeff': 0.015,
    'spell_heal_softcap_start': 8,
    'spell_heal_softcap_per_pouv': 0.045,
    'spell_heal_softcap_min': 0.40,
    'summon_softcap_start': 8,
    'summon_softcap_per_pouv': 0.035,
    'summon_softcap_min': 0.45,
    'horde_member_pouv_hp': 1.10,
    'horde_member_pouv_atk': 0.26,
    'horde_member_pouv_def': 0.12,
    'summon_afterimage_pouv_hp': 1.20,
    'summon_afterimage_pouv_def': 0.10,
    'summon_pouv_hp': 1.30,
    'summon_pouv_atk': 0.24,
    'summon_pouv_def': 0.14,
    'horde_conversion_base': 0.42,
    'horde_conversion_pouv_coeff': 0.007,
    'horde_conversion_size_penalty': 0.03,
    'horde_conversion_cap': 0.60,
}

# Déplacements: ZQSD/WASD seulement
DIR_KEYS = {
    'z': (0,-1), 'w': (0,-1),
    's': (0,1),
    'q': (-1,0), 'a': (-1,0),
    'd': (1,0)
}

# ========================== SPRITES (COMBAT) ==========================
SPRITES = {
    'knight': [
        "       !",
        "      .-.",
        "    __|=|__",
        "   (_/`-`\_)",
        "   //\___/\\",
        "   <>/   \<>",
        "    \|_._|/",
        "     <_I_>",
        "      |||",
        "     /_|_\\",
    ],
    'sorcier': [
        "                        .",
        "             /^\     .",
        "       /\    \ /",
        "      /__\    I      O  o",
        "     //..\\   I     .",
        "     \].`[/   I",
        "     /l\/j\  (]    .  O",
        "    /. ~~ ,\/ I          .",
        "    \\L__j^\/ I       o",
        "     \/--v}   I     o   .",
        "     |    |   I,  _________",
        "     |    |   I c(`       ')o,",
        "     |    l   I   \.     ,/,",
        "   _/j  L l\_ !  _//^---^\\_",   
    ],
    'mage': [
        "       /)   <(o)>",
        "      /~\     8",
        "     /._.\    I",
        "   ~_\ _ /_~  I",
        "   (_/-V-\_) (]",
        "   //\___/j\/ |",
        "   <>/   \ v  |",
        "    \|_._||   |",
        "    |<_I_>|   |",
        "    | ||| |   |",
        "  _/ /_|_\ \_ !",
    ],
    'slime': [
    "       __",
    "     (o o  )",
    "    (       )",
    ],
    'goblin':[
        "  ,_, ",
        " (0_0)",
        " /|_|\\",
        "  | | ",
        " /   \\",
        "  | | ",
        "      "
    ],
    'bat':[
        "    =/\                 /\=",
        "    /  \'._  (\_/)   _.'/ \\",
        "   / .''._'--(o.o)--'_.''. \\",
        "  /.' _/ |`'=/   \\='`| \_`.\\",
        " /` .' `\;-,'\___/',-;/` '. '\\",
        "/.-'       `\(-V-)/`       `-.\\",
    ],
    'skeleton':[
        "      .-.",
        "     (o.o)",
        "      |=|",
        "     __|__",
        "   //.=|=.\\",
        "  // .=|=. \\",

    ],
    'esprit':   [
        " .-.",
        "(o o) boo!",
        "| O \\",
        " \   \\",
        "  `~~~'",
    ],
    'diable': [
        "   , ,, ,                              ",
        "   | || |    ,/  _____  \.             ",
        "   \_||_/    ||_/     \_||             ",
        "     ||       \_| . . |_/              ",
        "     ||         |  L  |                ",
        "    ,||         |`==='|                ",
        "    |>|      ___`>  -<'___             ",
        "    |>|\    /             \            ",
        "    \>| \  /  ,    .    .  |           ",
    ],
    'dragon':[
        " <>=======()",
        "(/\___   /|\          ()==========<>_",
        "      \_/ | \        //|\   ______/ \)",
        "        \_|  \       // | \_/",
        "          \|\/|\_   //  /\/",
        "           (oo)\ \_//  /",
        "          / _/\_\/ /  |",
        "         @@/  |=\  \  |",
        "              \_=\_ \ |",
        "                \==\ \|\_",
        "              __(\===\(  )\\",
        "            (((~) __(_/   |",
        "                 (((~) \  /",
        "                 ______/ /",
        "                 '------'",
],
}

# ========================== TYPES & ITEMS ==========================
Item = namedtuple('Item',[ 'name','slot','hp_bonus','atk_bonus','def_bonus','crit_bonus','rarity','description','special' ])
Consumable = namedtuple('Consumable',['name','effect','power','rarity','description'])
Quest = namedtuple('Quest', ['qid','type','target','amount','progress','giver_floor','giver_pos','giver_name','reward_xp','reward_gold','status'])
Spell = namedtuple('Spell', ['sid', 'name', 'rarity', 'kind', 'description', 'power'])

SPELL_BOOK_NPC = {'name': 'S', 'title': 'Sorcier'}
SPELLS = [
    Spell('pulse', 'Impulsion', 'Commun', 'combat', 'Cantrip simple et stable.', 4),
    Spell('clairvoyance', 'Clairvoyance', 'Commun', 'explore', 'Vision accrue sur l’étage courant.', 1),
    Spell('warding_mist', 'Brume de garde', 'Commun', 'explore', 'Petit voile de protection magique.', 1),
    Spell('mending', 'Soin léger', 'Commun', 'combat', 'Restaure une petite quantité de PV.', 12),
    Spell('spark', 'Étincelle', 'Rare', 'combat', 'Projectile arcanique fiable.', 6),
    Spell('frostbind', 'Lien de givre', 'Rare', 'combat', 'Dégâts + affaiblit l’attaque ennemie.', 4),
    Spell('withering_hex', 'Maléfice d’usure', 'Rare', 'combat', 'Dégâts légers + baisse l’ATK ennemie.', 3),
    Spell('sunder_ward', 'Brèche runique', 'Rare', 'combat', 'Dégâts légers + baisse la DEF ennemie.', 3),
    Spell('arcbolt', 'Arc voltaïque', 'Rare', 'combat', 'Décharge instable à gros écart.', 6),
    Spell('arcane_skin', 'Peau arcanique', 'Rare', 'explore', 'Bouclier magique temporaire.', 1),
    Spell('gild_touch', 'Toucher doré', 'Rare', 'explore', 'Transmute un peu de mana en or.', 18),
    Spell('summon_slime', 'Invocation: Slime', 'Rare', 'combat', 'Invoque un slime gardien persistant.', 1),
    Spell('greater_mending', 'Soin moyen', 'Rare', 'combat', 'Restaure une quantité moyenne de PV.', 24),
    Spell('siphon', 'Siphon nocturne', 'Épique', 'combat', 'Dégâts modérés + soin partiel.', 6),
    Spell('rift', 'Faille courte', 'Épique', 'combat', 'Impact précis sur une faille arcanique.', 8),
    Spell('summon_skeleton', 'Invocation: Squelette', 'Épique', 'combat', 'Invoque un squelette combattant persistant.', 2),
    Spell('summon_afterimage', 'Invocation: Image rémanante', 'Épique', 'combat', 'Clone défensif: n’attaque pas, intercepte 80% des dégâts.', 1),
    Spell('call_of_dead', 'Invocation: Appel des morts', 'Épique', 'combat', 'Tente de convertir un squelette ennemi dans votre horde.', 0),
    Spell('prospection', 'Prospection', 'Épique', 'explore', 'Transmute du mana en or.', 24),
    Spell('focus_sigil', 'Sceau de focalisation', 'Épique', 'explore', 'Focus arcanique pour l’étage courant.', 1),
    Spell('teleport', 'Translocation', 'Épique', 'explore', 'Téléporte près de l’escalier de descente.', 0),
    Spell('nova', 'Nova runique', 'Légendaire', 'combat', 'Explosion puissante.', 12),
    Spell('comet', 'Comète astrale', 'Légendaire', 'combat', 'Impact lourd aux dégâts volatils.', 10),
    Spell('summon_dragon', 'Invocation: Dragonnet', 'Légendaire', 'combat', 'Invoque un dragonnet ancestral persistant.', 4),
]
SPELLS_BY_ID = {sp.sid: sp for sp in SPELLS}

COMMON_ITEMS = [
    Item('Épée rouillée','weapon',0,2,0,0.00,'Commun','Vieille lame.',None),
    Item('Bouclier bois','armor',4,0,2,0.0,'Commun','Bouclier simple.',None),
    Item('Anneau terne','accessory',3,1,0,0.00,'Commun','Petit boost.',None),
    Item('Couteau émoussé','weapon',0,1,0,0.00,'Commun','Mieux que rien.',None),
    Item('Massette légère','weapon',0,2,0,0.00,'Commun','Cogne un peu.',None),
    Item('Bâton fendu','weapon',0,2,0,0.01,'Commun','Une once de magie.',None),
    Item('Plastron de tissu','armor',3,0,1,0.00,'Commun','Protection minimale.',None),
    Item('Armature de cuir','armor',5,0,1,0.00,'Commun','Souple et discret.',None),
    Item('Gants rêches','accessory',2,1,0,0.00,'Commun','Mieux saisir l’arme.',None),
    Item('Bottes usées','accessory',3,0,0,0.00,'Commun','Un peu de confort.',None),
    Item('Broche terne','accessory',2,0,0,0.01,'Commun','Légère chance.',None),
    Item('Bouclier cabossé','armor',6,0,2,0.00,'Commun','A déjà servi.',None),
    Item('Pavois court','armor',4,0,2,0.00,'Commun','Facile à manier.',None),
    Item('Lame courte','weapon',0,2,0,0.02,'Commun','Rapide.',None),
    Item('Épieu paysan','weapon',0,3,0,0.00,'Commun','Long et rustique.',None),
    Item('Chapeau feutre','accessory',1,0,0,0.01,'Commun','Un peu de panache.',None),
    Item('Bracelet de corde','accessory',2,0,0,0.00,'Commun','Sans propriétés.',None),
    Item('Ceinture épaisse','accessory',4,0,0,0.00,'Commun','Maintient le torse.',None),
]
RARE_ITEMS = [
    Item('Épée équilibrée','weapon',0,5,0,0.02,'Rare','Bon compromis.',None),
    Item('Cuirasse cloutée','armor',8,0,3,0.0,'Rare','Solide.',None),
    Item('Anneau de force','accessory',0,3,0,0.00,'Rare','+ATK.',None),
    Item("Cape d'ombre",'armor',0,0,1,0.20,'Rare','+Critique.',None),
    Item('Hache équilibrée','weapon',0,6,0,0.00,'Rare','Bonne prise en main.',None),
    Item('Rapière fine','weapon',0,5,0,0.03,'Rare','Perce les failles.',None),
    Item('Massue cloutée','weapon',0,6,0,0.00,'Rare','Écrase bien.',None),
    Item('Cotte rivetée','armor',9,0,3,0.00,'Rare','Robuste.',None),
    Item('Bouclier rond','armor',10,0,3,0.00,'Rare','Compact.',None),
    Item('Brassards d’acier','armor',6,0,2,0.00,'Rare','Protègent les avants-bras.',None),
    Item('Amulette d’adresse','accessory',0,2,0,0.04,'Rare','Aiguise la précision.',None),
    Item('Anneau d’onguent','accessory',6,0,0,0.00,'Rare','Des soins plus sûrs.',None),
    Item('Bottes renforcées','accessory',5,0,1,0.00,'Rare','Bien assises.',None),
    Item('Targe nervurée','armor',8,0,4,0.00,'Rare','Dévie les coups.',None),
    Item('Épée large','weapon',0,6,0,0.01,'Rare','Tranche en arc.',None),
    Item('Bâton runique','weapon',0,5,0,0.04,'Rare','Canalise la magie.',None),
    Item('Cape à capuche','armor',4,0,2,0.03,'Rare','Se fond dans l’ombre.',None),
    Item('Ceinturon solide','accessory',8,0,0,0.00,'Rare','Bon maintien.',None),
    Item('Médaillon poli','accessory',4,1,0,0.02,'Rare','Brille légèrement.',None),
    Item('Bâton de flux','weapon',0,3,0,0.01,'Rare','Conduit mieux le mana.',{'pouv':3,'spell_power':0.12}),
    Item('Talisman prismatique','accessory',3,0,1,0.01,'Rare','Réfraction arcanique stable.',{'pouv':2,'spell_crit':0.02}),
    Item('Voile d’enchanteur','armor',5,0,2,0.00,'Rare','Filaments de protection magique.',{'pouv':2,'spell_defense':2}),
    Item('Anneau des étincelles','accessory',1,1,0,0.01,'Rare','Surcharge les cantrips.',{'pouv':2,'spell_damage':2}),
]
EPIC_ITEMS = [
    Item('Épée du vent','weapon',0,7,0,0.06,'Épique','Légère, précise.',{'dodge':0.05}),
    Item('Armure runique','armor',16,0,6,0.02,'Épique','Absorbe un peu.',{'regen':5}),
    Item('Griffe du destin','accessory',0,0,0,0.10,'Épique','Chance critique élevée.',None),
    Item('Lame vampirique','weapon',0,6,0,0.00,'Épique','Draine la vie.',{'lifesteal':0.20}),
    Item('Épée tempête','weapon',0,8,0,0.06,'Épique','Déchaîne les cieux.',{'dodge':0.03}),
    Item('Lame des sables','weapon',0,7,0,0.08,'Épique','Coupe en tourbillon.',None),
    Item('Marteau tellurique','weapon',0,9,0,0.00,'Épique','Vibre à l’impact.',None),
    Item('Armure écailleuse','armor',14,0,7,0.01,'Épique','Écailles imbriquées.',None),
    Item('Haubert béni','armor',18,0,5,0.02,'Épique','Chants gravés.',{'regen':3}),
    Item('Bouclier solaire','armor',10,0,8,0.00,'Épique','Renvoie l’éclat.',{'thorns':2}),
    Item('Anneau d’éclair','accessory',0,4,0,0.06,'Épique','Nerfs en éveil.',None),
    Item('Amulette de vigueur','accessory',14,0,0,0.02,'Épique','Force vitale accrue.',None),
    Item('Gants de prédateur','accessory',0,5,0,0.00,'Épique','Prise mortelle.',None),
    Item('Épée polaire','weapon',0,7,0,0.05,'Épique','Froid mordant.',None),
    Item('Cuissots de granite','armor',12,0,6,0.00,'Épique','Base inébranlable.',None),
    Item('Cape de traque','armor',8,0,4,0.05,'Épique','Trajets silencieux.',{'dodge':0.04}),
    Item('Griffe d’obsidienne','accessory',0,0,0,0.12,'Épique','Tranchant absolu.',None),
    Item('Pendentif vital','accessory',18,0,0,0.00,'Épique','Courage du cœur.',{'regen':2}),
    Item('Bottes du vent','accessory',6,0,3,0.00,'Épique','Foulée vive.',{'dodge':0.03}),
    Item('Sceptre astral','weapon',0,4,0,0.03,'Épique','Amplifie les pics de puissance.',{'pouv':4,'spell_power':0.18,'spell_damage':2}),
    Item('Manteau des comètes','armor',8,0,3,0.01,'Épique','Traînées de mana défensif.',{'pouv':3,'spell_defense':3,'spell_slots':1}),
    Item('Sigil du thaumaturge','accessory',6,0,1,0.03,'Épique','Concentration difficile à rompre.',{'pouv':4,'spell_crit':0.03,'spell_power':0.12}),
    Item('Orbe résonante','accessory',2,0,1,0.02,'Épique','Réverbère l’impact des sorts.',{'pouv':3,'spell_damage':3}),
]
LEGENDARY_ITEMS = [
    Item('Couronne ancienne','accessory',20,2,2,0.05,'Légendaire','Attire les ennuis.',{'unlucky':0.10}),
    Item('Cuirasse de verre','armor',-10,0,10,-0.05,'Légendaire','Incroyable mais fragile.',{'glass':True}),
    Item('Épée de chaos','weapon',0,10,0,0.0,'Légendaire','Imprévisible.',{'chaos':True}),
    Item('Bouclier à pointes','armor',8,0,6,0.0,'Légendaire','Ça pique.',{'thorns':3}),
    Item('Bottes de plomb','accessory',12,0,4,-0.06,'Légendaire','Très lourdes.',{'heavy':True}),
    Item('Épée maîtresse','weapon',0,11,0,0.05,'Légendaire','Domine le duel.',None),
    Item('Tranche-soleil','weapon',0,12,0,0.02,'Légendaire','Arc aveuglant.',None),
    Item('Marteau des rois','weapon',0,13,0,0.00,'Légendaire','Poids de l’histoire.',None),
    Item('Heaume de l’aube','armor',16,0,8,0.02,'Légendaire','Protège l’esprit.',None),
    Item('Cuirasse sanctifiée','armor',20,0,9,0.01,'Légendaire','Bénédiction antique.',{'regen':4}),
    Item('Égide écarlate','armor',14,0,10,0.00,'Légendaire','Mur vivant.',{'thorns':4}),
    Item('Anneau du phénix','accessory',10,3,2,0.06,'Légendaire','Cendre et renouveau.',None),
    Item('Sceau royal','accessory',15,2,3,0.05,'Légendaire','Autorité gravée.',None),
    Item('Bottes astrales','accessory',10,0,5,0.02,'Légendaire','Pas irréels.',{'dodge':0.05}),
    Item('Lame hurlante','weapon',0,10,0,0.08,'Légendaire','Cri dans l’acier.',None),
    Item('Plastron du colosse','armor',24,0,10,0.00,'Légendaire','Titan d’acier.',None),
    Item('Bouclier des épines','armor',12,0,9,0.00,'Légendaire','Impossible à enlacer.',{'thorns':5}),
    Item('Amulette du destin','accessory',8,0,0,0.12,'Légendaire','Faveur capricieuse.',None),
    Item('Couronne du zénith','accessory',22,3,3,0.05,'Légendaire','Apogée du pouvoir.',None),
    Item('Épée des millénaires','weapon',0,14,0,0.04,'Légendaire','A vu des empires naître.',None),
    Item('Bâton archonte','weapon',0,5,0,0.04,'Légendaire','Autorité absolue sur le flux.',{'pouv':6,'spell_power':0.25,'spell_damage':4}),
    Item('Égide des runes vives','armor',12,0,5,0.02,'Légendaire','Les glyphes absorbent l’impact.',{'pouv':5,'spell_defense':4,'spell_slots':1}),
    Item('Couronne de l’érudit noir','accessory',8,1,1,0.05,'Légendaire','Savoir dangereux et fertile.',{'pouv':7,'spell_crit':0.05,'spell_power':0.20}),
]
CURSED_ODDITIES = [
    Item('Sceau d’apprenti','accessory',3,0,1,0.01,'Rare','Canalisation de base.',{'pouv':1,'spell_power':0.10}),
    Item('Bâton de veille','weapon',0,3,0,0.01,'Rare','Amplifie les cantrips.',{'pouv':2,'spell_damage':1}),
    Item('Manteau des runes','armor',6,0,2,0.00,'Rare','Fils de mana tissés.',{'pouv':1,'spell_defense':1}),
    Item('Anneau de concentration','accessory',4,1,0,0.01,'Rare','Réduit les pertes de focus.',{'pouv':2,'spell_power':0.12}),
    Item('Orbe des veilleurs','accessory',2,0,1,0.02,'Rare','Un emplacement de sort supplémentaire.',{'pouv':1,'spell_slots':1}),
    Item('Codex fragmenté','accessory',3,0,1,0.01,'Rare','Fragments d’incantations.',{'pouv':2,'spell_slots':1,'spell_power':0.08}),
    Item('Grimoire ferré','armor',7,0,3,0.00,'Rare','Plaques gravées de glyphes.',{'pouv':2,'spell_defense':1,'spell_slots':1}),
    Item('Bague du pyromant','accessory',0,2,0,0.02,'Rare','Renforce les sorts offensifs.',{'pouv':3,'spell_damage':2,'spell_power':0.06}),
    Item('Opale du ritualiste','accessory',2,0,1,0.02,'Étrange','Le flux fluctue et mord.',{'pouv':5,'spell_power':0.20,'unlucky':0.05,'cursed':True}),
    Item('Manteau de cendre froide','armor',9,0,3,0.00,'Étrange','Excellent canal, mauvais présage.',{'pouv':4,'spell_defense':3,'cursed':True}),
    Item('Relique de l’oubli','weapon',0,4,0,0.03,'Étrange','Plus elle brille, plus le sort vacille.',{'pouv':5,'spell_damage':3,'spell_crit':0.03,'cursed':True}),
]

def _rebalance_item_pool(items):
    """Lissage medium des stats d'items pour une progression plus lisible par rareté."""
    rarity_stat_mult = {
        'Commun': 1.05,
        'Rare': 0.94,
        'Épique': 0.82,
        'Légendaire': 0.74,
        'Étrange': 0.90,
    }
    rarity_caps = {
        'Commun': {'hp': 6, 'atk': 3, 'def': 2, 'crit': 0.03},
        'Rare': {'hp': 10, 'atk': 6, 'def': 4, 'crit': 0.06},
        'Épique': {'hp': 16, 'atk': 9, 'def': 7, 'crit': 0.09},
        'Légendaire': {'hp': 21, 'atk': 11, 'def': 9, 'crit': 0.11},
        'Étrange': {'hp': 18, 'atk': 9, 'def': 7, 'crit': 0.10},
    }
    special_caps = {
        'regen': {'Rare': 2, 'Épique': 3, 'Légendaire': 4, 'Étrange': 3},
        'thorns': {'Épique': 2, 'Légendaire': 4, 'Étrange': 4},
        'lifesteal': {'Épique': 0.14, 'Légendaire': 0.16, 'Étrange': 0.14},
        'dodge': {'Rare': 0.04, 'Épique': 0.05, 'Légendaire': 0.06, 'Étrange': 0.05},
        'poison_on_hit': {'Étrange': 2},
        'pouv': {'Rare': 3, 'Épique': 5, 'Légendaire': 7, 'Étrange': 6},
        'spell_power': {'Rare': 0.12, 'Épique': 0.18, 'Légendaire': 0.25, 'Étrange': 0.22},
        'spell_damage': {'Rare': 2, 'Épique': 3, 'Légendaire': 4, 'Étrange': 3},
        'spell_defense': {'Rare': 2, 'Épique': 3, 'Légendaire': 4, 'Étrange': 3},
        'spell_slots': {'Rare': 1, 'Épique': 1, 'Légendaire': 2, 'Étrange': 1},
        'spell_crit': {'Rare': 0.02, 'Épique': 0.03, 'Légendaire': 0.05, 'Étrange': 0.04},
    }

    out = []
    for it in items:
        if not isinstance(it, Item):
            out.append(it)
            continue

        rar = it.rarity
        caps = rarity_caps.get(rar, rarity_caps['Commun'])
        mult = rarity_stat_mult.get(rar, 1.0)

        def _scale_int(v, cap):
            if v <= 0:
                return int(v)
            return int(min(cap, max(1, round(v * mult))))

        hp = _scale_int(it.hp_bonus, caps['hp'])
        atk = _scale_int(it.atk_bonus, caps['atk'])
        dfn = _scale_int(it.def_bonus, caps['def'])
        crit = it.crit_bonus
        if crit > 0:
            crit = min(caps['crit'], round(crit * mult, 2))
        elif crit < 0:
            crit = max(-caps['crit'], round(crit, 2))

        # Les communs doivent rester utiles tôt.
        if rar == 'Commun':
            if it.slot == 'weapon':
                atk = max(2, atk)
            elif it.slot == 'armor':
                hp = max(4, hp)
                dfn = max(1, dfn)
            elif it.slot == 'accessory' and (hp + atk + dfn) < 3 and crit <= 0:
                hp = max(hp, 2)
                atk = max(atk, 1)

        spec = dict(it.special) if it.special else None
        if spec:
            for k, rules in special_caps.items():
                if k in spec and rar in rules:
                    val = spec[k]
                    if isinstance(val, (int, float)):
                        spec[k] = min(rules[rar], val)
            if not spec:
                spec = None

        out.append(it._replace(
            hp_bonus=hp,
            atk_bonus=atk,
            def_bonus=dfn,
            crit_bonus=crit,
            special=spec
        ))
    return out

COMMON_ITEMS = _rebalance_item_pool(COMMON_ITEMS)
RARE_ITEMS = _rebalance_item_pool(RARE_ITEMS)
EPIC_ITEMS = _rebalance_item_pool(EPIC_ITEMS)
LEGENDARY_ITEMS = _rebalance_item_pool(LEGENDARY_ITEMS)
CURSED_ODDITIES = _rebalance_item_pool(CURSED_ODDITIES)

ALL_ITEMS = COMMON_ITEMS + RARE_ITEMS + EPIC_ITEMS + LEGENDARY_ITEMS + CURSED_ODDITIES

# --- Assainissement du pool global ---
def _validate_item_pool():
    bad = []
    good = []
    for it in ALL_ITEMS:
        if isinstance(it, Item) and hasattr(it, 'rarity') and hasattr(it, 'slot'):
            good.append(it)
        else:
            bad.append(it)
    if bad:
        print(c(f"[WARN] ALL_ITEMS contenait {len(bad)} entrée(s) invalides. Elles sont ignorées.", Ansi.BRIGHT_YELLOW))
    return good

ALL_ITEMS = _validate_item_pool()


CONSUMABLE_POOL = [
    Consumable('Potion de soin','heal',24,'Commun','Rend 24 PV.'),
    Consumable('Élixir majeur','heal',65,'Rare','Rend beaucoup de PV.'),
    Consumable('Potion de rage','buff_atk',4,'Rare','ATK +4 (3 tours).'),
    Consumable('Pierre de rappel','flee','0', 'Rare', 'Permet de fuir un combat.'),
]
HIGH_TIER_POTIONS = [
    Consumable('Panacée souveraine', 'heal_ultra', 120, 'Épique', 'Rend 120 PV. Très coûteuse.'),
    Consumable('Tonique du colosse', 'buff_atk_ultra', 8, 'Légendaire', 'ATK +8 (4 tours). Très rare.'),
    Consumable('Poudre philosophale', 'summon_full_heal', 1, 'Légendaire', 'Rend tous les PV de votre invocation active.'),
]
GEM_FRAGMENT_POOL = [
    Consumable('Éclat de grenat', 'frag_atk_pct', (0.06, 2), 'Commun', '+6% ATK pour les 2 prochains combats.'),
    Consumable('Éclat de quartz', 'frag_def_pct', (0.06, 2), 'Commun', '-6% dégâts subis pour les 2 prochains combats.'),
    Consumable('Éclat d\'opale', 'frag_spell_pct', (0.08, 2), 'Commun', '+8% dégâts de sorts pour les 2 prochains combats.'),
    Consumable('Éclat de perle', 'frag_crit_flat', (0.01, 1), 'Commun', '+0.01 CRIT pour le prochain combat.'),
    Consumable('Fragment de rubis', 'frag_atk_pct', (0.12, 3), 'Rare', '+12% ATK pour les 3 prochains combats.'),
    Consumable('Fragment de saphir', 'frag_def_pct', (0.12, 3), 'Rare', '-12% dégâts subis pour les 3 prochains combats.'),
    Consumable('Fragment d\'améthyste', 'frag_spell_pct', (0.15, 3), 'Épique', '+15% dégâts de sorts pour les 3 prochains combats.'),
    Consumable('Fragment de diamant', 'frag_crit_flat', (0.03, 2), 'Épique', '+0.03 CRIT pour les 2 prochains combats.'),
]

RARITY_WEIGHTS_BASE = BALANCE.get('rarity_base_weights', {'Commun':72,'Rare':10,'Épique':4,'Légendaire':0.5,'Étrange':8}).copy()
RARITY_ORDER = ['Commun','Rare','Épique','Légendaire','Étrange']

# === Couleurs pour les stats ===
STAT_COLORS = {
    'HP':   Ansi.BRIGHT_GREEN,
    'ATK':  Ansi.BRIGHT_RED,
    'DEF':  Ansi.BRIGHT_CYAN,
    'CRIT': Ansi.BRIGHT_MAGENTA,
    'POUV': Ansi.BRIGHT_BLUE,
    'XP':   Ansi.BRIGHT_YELLOW,
    'OR':   Ansi.YELLOW,
}

def color_label(name):
    return c(name, STAT_COLORS.get(name, Ansi.WHITE))

def color_val(name, text):
    return c(str(text), STAT_COLORS.get(name, Ansi.WHITE))

def is_magic_item(it):
    return isinstance(it, Item) and bool(getattr(it, 'special', None)) and any(str(k).startswith('spell_') or k == 'pouv' for k in it.special.keys())

def item_pouv(it):
    if not isinstance(it, Item) or not getattr(it, 'special', None):
        return 0
    return int(it.special.get('pouv', 0))

def consumable_display_color(cns):
    if not isinstance(cns, Consumable):
        return Ansi.WHITE
    eff = str(getattr(cns, 'effect', ''))
    if not eff.startswith('frag_'):
        return Ansi.WHITE
    name = str(getattr(cns, 'name', '')).lower()
    if ('rubis' in name) or ('grenat' in name):
        return Ansi.BRIGHT_RED
    if ('saphir' in name) or ('quartz' in name):
        return Ansi.BRIGHT_CYAN
    if 'améthyste' in name:
        return Ansi.BRIGHT_MAGENTA
    if 'opale' in name:
        return Ansi.BRIGHT_YELLOW
    if ('diamant' in name) or ('perle' in name):
        return Ansi.BRIGHT_WHITE
    return Ansi.BRIGHT_BLUE

def color_delta(n):
    """+X en vert, -X en rouge, 0 en gris"""
    if n > 0:  return c(f"+{n}", Ansi.BRIGHT_GREEN)
    if n < 0:  return c(f"{n}", Ansi.BRIGHT_RED)
    return c("±0", Ansi.BRIGHT_BLACK)

def color_delta_crit(x):
    """delta critique en %, même logique"""
    if x > 0:  return c(f"+{x:.2f}", Ansi.BRIGHT_GREEN)
    if x < 0:  return c(f"{x:.2f}", Ansi.BRIGHT_RED)
    return c("±0.00", Ansi.BRIGHT_BLACK)

def hp_gauge_text(cur, mx):
    """Affiche 'cur/mx PV' coloré (vert/jaune/rouge selon pourcentage)"""
    ratio = 0 if mx<=0 else cur / mx
    if   ratio >= 0.66: col = Ansi.BRIGHT_GREEN
    elif ratio >= 0.33: col = Ansi.BRIGHT_YELLOW
    else:               col = Ansi.BRIGHT_RED
    return c(f"{cur}/{mx} PV", col)

def _fmt_num(v):
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else f"{v:.2f}"
    return str(v)

# ========================== PERSONNAGES & MONSTRES ==========================
class Character:
    def __init__(self,name,hp,atk,defense,crit=0.05):
        self.name=name; self.max_hp=hp; self.hp=hp
        self.atk=atk; self.defense=defense; self.crit=crit
    def is_alive(self): return self.hp>0
    def take_damage(self,d): self.hp=max(0,self.hp-d)
    def heal(self,a): self.hp=min(self.max_hp,self.hp+a)

class Player(Character):
    def __init__(self,name,klass='Chevalier'):
        k = (klass or 'Chevalier').strip().lower()
        if k == 'mage':
            base = dict(name=name,hp=24,atk=6,defense=2,crit=0.08)
            self.map_icon = '&'
            self.sprite = SPRITES.get('mage', SPRITES.get('knight', []))
            self.level_gain_mult = {
                'hp': float(BALANCE.get('mage_level_hp_mult', 0.90)),
                'atk': float(BALANCE.get('mage_level_atk_mult', 0.65)),
                'def': float(BALANCE.get('mage_level_def_mult', 0.65)),
            }
            self.mage_core = True
            klass = 'Mage'
        else:
            # PV de base réduits pour une difficulté plus élevée
            base = dict(name=name,hp=36,atk=10,defense=5,crit=0.06)
            self.map_icon = PLAYER_ICON
            self.sprite = SPRITES.get('knight', [])
            self.level_gain_mult = {'hp': 1.0, 'atk': 1.0, 'def': 1.0}
            self.mage_core = False
        super().__init__(**base)
        self.klass=klass
        self.level=1; self.xp=0; self.gold=40
        self.inventory=[]; self.inventory_limit=14
        self.consumables = []          # ← sac dédié aux potions/consommables
        self.consumables_limit = 10
        self.equipment={'weapon':None,'armor':None,'accessory':None}
        self.temp_buffs={'atk':0,'turns':0}
        self.last_move=(0,0)
        self.quests_active=[]; self.quests_done=[]
        # Boutique: 1 accès gratuit par étage + 1 accès bonus possible (payant)
        self.shop_access_count={}
        self.sage_access_count={}
        self.blessings_count = 0
        self.curses_count = 0
        self.normal_keys = 1
        self.boss_keys = 0
        self.altar_history = []
        self.passive_specials = {}
        self.floor_specials = {}
        self.next_combat_buffs = {'atk_pct': 0.0, 'def_pct': 0.0, 'spell_pct': 0.0, 'crit_flat': 0.0, 'fights_left': 0}
        self.summon = None
        self.summon_spell_cds = {}
        self.active_explore_spells = {}
        self.teleport_spell_cd = 0
        self.spellbook_unlocked = False
        self.spell_scrolls = []
        self.spells_cast_this_floor = 0
        self.sage_depths_visited = set()
        self.altar_dynamic_effects = []
        if self.mage_core:
            self.spellbook_unlocked = True
            starter = _pick_spell_ids(0, set(), count=1, source='loot')
            self.spell_scrolls = starter[:] if starter else ['pulse']
            self.passive_specials['pouv'] = max(3, int(self.passive_specials.get('pouv', 0)))

    def equip(self,item):
        slot=item.slot; old=self.equipment.get(slot)
        if old: self._apply_modifiers(old,remove=True); self.inventory.append(old)
        self.equipment[slot]=item; self._apply_modifiers(item,remove=False)
    def _apply_modifiers(self,item,remove=False):
        sign=-1 if remove else 1
        self.max_hp=max(1,self.max_hp+sign*item.hp_bonus)
        self.hp=min(self.max_hp,max(1,self.hp+sign*item.hp_bonus))
        self.atk=max(0,self.atk+sign*item.atk_bonus)
        self.defense=max(0,self.defense+sign*item.def_bonus)
        self.crit=max(0.0,min(0.9,self.crit+sign*item.crit_bonus))
        self.recompute_altar_dynamic_effects()

    def _altar_effects_for_attr(self, attr):
        return [e for e in self.altar_dynamic_effects if e.get('attr') == attr]

    def _altar_dynamic_base(self, attr):
        effects = self._altar_effects_for_attr(attr)
        current = getattr(self, attr)
        applied = sum(float(e.get('applied', 0.0)) for e in effects)
        return float(current) - applied

    def recompute_altar_dynamic_effects(self):
        if not self.altar_dynamic_effects:
            return
        for attr in ('max_hp', 'atk', 'defense', 'crit'):
            effects = self._altar_effects_for_attr(attr)
            if not effects:
                continue
            current = float(getattr(self, attr))
            prev_total = sum(float(e.get('applied', 0.0)) for e in effects)
            base = current - prev_total
            target_parts = []
            attr_floor = 0.0
            for e in effects:
                pct = float(e.get('pct', 0.0))
                min_delta = float(e.get('min_delta', 0.0))
                floor_value = float(e.get('floor_value', 0.0))
                attr_floor = max(attr_floor, floor_value)
                calc_base = max(floor_value, base)
                delta = max(min_delta, calc_base * pct)
                if not bool(e.get('is_float', False)):
                    delta = float(int(round(delta)))
                sign = 1.0 if e.get('kind') == 'gain' else -1.0
                target_parts.append(sign * delta)
            target_total = sum(target_parts)
            new_value = base + target_total
            if attr == 'crit':
                new_value = max(0.0, min(0.9, round(new_value, 3)))
            else:
                new_value = max(attr_floor, float(int(round(new_value))))
            setattr(self, attr, new_value if attr == 'crit' else int(new_value))
            realized_total = float(getattr(self, attr)) - base
            if abs(target_total) < 1e-9:
                for e in effects:
                    e['applied'] = 0.0
                continue
            ratio = realized_total / target_total
            if attr == 'crit':
                for i, e in enumerate(effects):
                    val = target_parts[i] * ratio
                    e['applied'] = round(val, 3)
            else:
                scaled = [int(round(v * ratio)) for v in target_parts]
                drift = int(round(realized_total)) - sum(scaled)
                if scaled and drift != 0:
                    scaled[-1] += drift
                for i, e in enumerate(effects):
                    e['applied'] = float(scaled[i])
        self.hp = min(self.hp, int(self.max_hp))

    def add_altar_dynamic_effect(self, attr, pct, kind='gain', min_delta=1, floor_value=0, is_float=False):
        effect = {
            'attr': attr,
            'pct': float(pct),
            'kind': 'gain' if kind == 'gain' else 'loss',
            'min_delta': float(min_delta),
            'floor_value': float(floor_value),
            'is_float': bool(is_float),
            'applied': 0.0,
        }
        self.altar_dynamic_effects.append(effect)
        self.recompute_altar_dynamic_effects()
        return float(effect.get('applied', 0.0))
    def all_specials(self):
        specs={}
        for k,v in self.passive_specials.items():
            specs[k] = specs.get(k, 0) + v if isinstance(v, (int, float)) else v
        for k,v in self.floor_specials.items():
            specs[k] = specs.get(k, 0) + v if isinstance(v, (int, float)) else v
        mage_magic_mult = float(BALANCE.get('mage_magic_item_mult', 1.35)) if self.klass == 'Mage' else 1.0
        # Le Mage ne doit pas avoir de multiplicateur de dégâts de sorts propre à la classe.
        # On conserve le bonus de classe sur POUV et l'utilitaire magique, mais pas sur spell_power/spell_damage.
        mage_magic_keys = {'pouv', 'spell_defense', 'spell_slots', 'spell_crit'}
        for it in self.equipment.values():
            if it and it.special:
                is_magic = is_magic_item(it)
                for k,v in it.special.items():
                    if isinstance(v,(int,float)):
                        add_v = v
                        if self.klass == 'Mage' and is_magic and k in mage_magic_keys:
                            add_v = v * mage_magic_mult
                            if isinstance(v, int):
                                add_v = int(round(add_v))
                            else:
                                add_v = round(add_v, 3)
                        specs[k]=specs.get(k,0)+add_v
                    else: specs[k]=True
        return specs

    def reset_floor_magic(self):
        self.spells_cast_this_floor = 0
        if self.teleport_spell_cd > 0:
            self.teleport_spell_cd -= 1
        if self.summon_spell_cds:
            for sid in list(self.summon_spell_cds.keys()):
                rem = int(self.summon_spell_cds.get(sid, 0)) - 1
                if rem > 0:
                    self.summon_spell_cds[sid] = rem
                else:
                    self.summon_spell_cds.pop(sid, None)
        if self.active_explore_spells:
            for sid in list(self.active_explore_spells.keys()):
                rem = int(self.active_explore_spells.get(sid, 0)) - 1
                if rem > 0:
                    self.active_explore_spells[sid] = rem
                else:
                    self.active_explore_spells.pop(sid, None)
        _rebuild_floor_magic_from_active_spells(self)

    def can_cast_spell(self):
        if not self.spellbook_unlocked:
            return False
        if _spell_casts_left(self) > 0:
            return True
        return any(_spell_slot_cost(_spell_by_id(sid)) == 0 for sid in self.spell_scrolls)
    
    def stats_summary(self):
        sm = _active_summon(self)
        summon_txt = "Invocation:—"
        if sm:
            summon_txt = f"Invocation:{sm.get('name','?')} {sm.get('hp',0)}/{sm.get('max_hp',0)}"
        parts = [
            f"Classe:{self.klass}",
            f"Niv:{self.level}",
            f"{color_label('HP')}:{hp_gauge_text(self.hp, self.max_hp)}",
            f"{color_label('ATK')}:{color_val('ATK', self.atk + self.temp_buffs['atk'])}",
            f"{color_label('DEF')}:{color_val('DEF', _fmt_num(self.defense))}",
            f"{color_label('CRIT')}:{color_val('CRIT', f'{self.crit:.2f}')}",
            f"{color_label('POUV')}:{color_val('POUV', _spell_pouv(self))}",
            f"{color_label('OR')}:{color_val('OR', self.gold)}",
            f"{color_label('XP')}:{color_val('XP', f'{self.xp}/30')}",
            f"Clés N/B:{self.normal_keys}/{self.boss_keys}",
            f"Sorts étage:{_spell_casts_left(self)}/{_spell_cast_limit(self)}",
            summon_txt,
        ]
        line1 = "  ".join(parts)
        return line1
        
    def gain_xp(self, amount):
        self.xp += amount
        while self.xp >= BALANCE['level_xp_threshold']:
            self.xp -= BALANCE['level_xp_threshold']
            self.level += 1
            if self.klass == 'Mage':
                hp_gain = 1
                atk_gain = 1
                def_gain = 0.20
                pouv_gain = 0
                pouv_every = max(1, int(BALANCE.get('mage_pouv_gain_every_levels', 2)))
                if self.level % pouv_every == 0:
                    pouv_gain = int(BALANCE.get('mage_level_pouv_gain', 1))
                    self.passive_specials['pouv'] = int(self.passive_specials.get('pouv', 0)) + pouv_gain
            else:
                hp_gain = max(1, int(round(BALANCE['level_hp_gain'] * float(self.level_gain_mult.get('hp', 1.0)))))
                atk_gain = max(1, int(round(BALANCE['level_atk_gain'] * float(self.level_gain_mult.get('atk', 1.0)))))
                def_gain = max(0.2, float(BALANCE['level_def_gain']) * float(self.level_gain_mult.get('def', 1.0)))
                pouv_gain = 0
            self.max_hp += hp_gain
            self.atk    += atk_gain
            self.defense+= def_gain
            self.recompute_altar_dynamic_effects()

            # Soin partiel à chaque montée de niveau
            heal = int(self.max_hp * BALANCE.get('level_heal_ratio', 0.50))
            self.hp = min(self.max_hp, self.hp + heal)

            pouv_txt = f" +POUV:{pouv_gain}" if pouv_gain > 0 else ""
            print(c(f"*** Niveau {self.level}! +HP:{hp_gain} +ATK:{atk_gain} +DEF:{def_gain:.2f}{pouv_txt}(+{heal} PV) ***", Ansi.BRIGHT_YELLOW))
            time.sleep(0.6)

CONSUMABLE_STACK_MAX = 3
FRAGMENT_STACK_MAX = 5

def _stack_max_for_consumable(cns):
    if isinstance(cns, Consumable) and str(getattr(cns, 'effect', '')).startswith('frag_'):
        return FRAGMENT_STACK_MAX
    return CONSUMABLE_STACK_MAX

def _grant_fragment_permanent(player, cns):
    if not isinstance(cns, Consumable):
        return False
    eff = str(getattr(cns, 'effect', ''))
    power = getattr(cns, 'power', 0)
    if isinstance(power, (tuple, list)) and len(power) >= 1:
        amount = float(power[0])
    else:
        amount = float(power) if isinstance(power, (int, float)) else 0.0
    key_map = {
        'frag_atk_pct': 'perm_frag_atk_pct',
        'frag_def_pct': 'perm_frag_def_pct',
        'frag_spell_pct': 'perm_frag_spell_pct',
        'frag_crit_flat': 'perm_frag_crit_flat',
    }
    pkey = key_map.get(eff)
    if not pkey or amount <= 0:
        return False
    cur = float(player.passive_specials.get(pkey, 0.0))
    player.passive_specials[pkey] = round(cur + amount, 4)
    return True

def _try_convert_full_fragment_stack_to_permanent(player, cns):
    if not isinstance(cns, Consumable):
        return False
    if not str(getattr(cns, 'effect', '')).startswith('frag_'):
        return False
    stacks = _consumable_stacks(player)
    max_stack = _stack_max_for_consumable(cns)
    for i, st in enumerate(list(stacks)):
        if st.get('item') == cns and int(st.get('qty', 0)) >= max_stack:
            # Conversion: le stack plein est consommé pour un bonus permanent (valeur d'un fragment).
            st['qty'] -= max_stack
            if st['qty'] <= 0:
                stacks.pop(i)
            _grant_fragment_permanent(player, cns)
            return True
    return False

def _normalize_consumables(player):
    """
    Normalise le sac consommables au format:
      [{'item': Consumable, 'qty': int}, ...]
    Gère aussi l'ancien format (liste plate de Consumable).
    """
    raw = getattr(player, 'consumables', [])
    if not isinstance(raw, list):
        player.consumables = []
        return player.consumables

    normalized = []

    def _push_one(cns):
        for st in normalized:
            if st['item'] == cns and st['qty'] < _stack_max_for_consumable(cns):
                st['qty'] += 1
                return
        normalized.append({'item': cns, 'qty': 1})

    for entry in raw:
        if isinstance(entry, Consumable):
            _push_one(entry)
            continue

        if isinstance(entry, dict):
            cns = entry.get('item')
            qty = entry.get('qty', 1)
            if isinstance(cns, Consumable):
                try:
                    q = max(1, int(qty))
                except Exception:
                    q = 1
                for _ in range(q):
                    _push_one(cns)
                continue

        if isinstance(entry, (tuple, list)) and len(entry) == 2 and isinstance(entry[0], Consumable):
            cns, qty = entry
            try:
                q = max(1, int(qty))
            except Exception:
                q = 1
            for _ in range(q):
                _push_one(cns)

    player.consumables = normalized
    return player.consumables

def _consumable_stacks(player):
    return _normalize_consumables(player)

def _consumable_slots_used(player):
    return len(_consumable_stacks(player))

def _consumable_total_count(player):
    return sum(st['qty'] for st in _consumable_stacks(player))

def _add_consumable(player, cns, qty=1):
    """
    Ajoute jusqu'à qty unités en respectant:
    - slots max: player.consumables_limit
    - stack max: CONSUMABLE_STACK_MAX
    Retourne le nombre d'unités réellement ajoutées.
    """
    stacks = _consumable_stacks(player)
    limit = int(getattr(player, 'consumables_limit', 0))
    added = 0
    for _ in range(max(0, int(qty))):
        placed = False
        for st in stacks:
            if st['item'] == cns and st['qty'] < _stack_max_for_consumable(cns):
                st['qty'] += 1
                placed = True
                break
        if not placed:
            if len(stacks) >= limit:
                break
            stacks.append({'item': cns, 'qty': 1})
            placed = True
        if placed:
            added += 1
            _try_convert_full_fragment_stack_to_permanent(player, cns)
    return added

def _consume_consumable_at(player, idx):
    """
    Consomme 1 unité du stack idx et retourne le consommable.
    Retourne None si idx invalide.
    """
    stacks = _consumable_stacks(player)
    if not (0 <= idx < len(stacks)):
        return None
    st = stacks[idx]
    cns = st['item']
    st['qty'] -= 1
    if st['qty'] <= 0:
        stacks.pop(idx)
    return cns

def _discard_consumable_at(player, idx, qty=1):
    """
    Jette qty unités depuis le stack idx.
    Retourne le nombre d'unités jetées.
    """
    stacks = _consumable_stacks(player)
    if not (0 <= idx < len(stacks)):
        return 0
    st = stacks[idx]
    to_drop = max(1, int(qty))
    dropped = min(st['qty'], to_drop)
    st['qty'] -= dropped
    if st['qty'] <= 0:
        stacks.pop(idx)
    return dropped

MONSTER_DEFS = [
    {'id':'slime','name':'Slime','hp':12,'atk':3,'def':1,'crit':0.02,'xp':6,'gold':3,'sprite':SPRITES['slime']},
    {'id':'goblin','name':'Gobelin','hp':18,'atk':6,'def':2,'crit':0.04,'xp':10,'gold':6,'sprite':SPRITES['goblin']},
    {'id':'bat','name':'Chauve-souris','hp':10,'atk':4,'def':0,'crit':0.03,'xp':5,'gold':2,'sprite':SPRITES['bat']},
    {'id':'skeleton','name':'Squelette','hp':22,'atk':7,'def':2,'crit':0.05,'xp':12,'gold':8,'sprite':SPRITES['skeleton']},
    {'id':'esprit','name':'Esprit','hp':28,'atk':9,'def':3,'crit':0.06,'xp':18,'gold':12,'sprite':SPRITES['esprit']},
    {'id':'diable','name':'Diable','hp':40,'atk':12,'def':5,'crit':0.06,'xp':28,'gold':22,'sprite':SPRITES['diable']},
    {'id':'dragon','name':'Dragonnet','hp':60,'atk':16,'def':6,'crit':0.08,'xp':45,'gold':40,'sprite':SPRITES['dragon']},
]

# ========================== UTILITAIRES ==========================
def clear_screen():
    # Évite le clipping/flicker causé par `cls`/`clear` en sous-processus.
    # Toute vue non-map invalide le mode repaint incrémental de la map.
    global MAP_FRAME_ACTIVE
    MAP_FRAME_ACTIVE = False
    # Avec ANSI, on repositionne le curseur puis on efface le buffer écran.
    if SUPPORTS_ANSI:
        sys.stdout.write("\x1b[H\x1b[2J\x1b[3J")
        sys.stdout.flush()
        return
    os.system('cls' if os.name=='nt' else 'clear')

def pause(msg='Appuyez sur Entrée pour continuer...'): input(msg)

def begin_frame_redraw():
    """
    Redessine une frame en évitant l'effacement total (réduit flicker/clipping).
    """
    if SUPPORTS_ANSI:
        # Repaint map->map: curseur en haut sans full clear (réduit le flicker).
        sys.stdout.write("\x1b[H")
        sys.stdout.flush()
    else:
        clear_screen()

def rarity_color(r):
    return {
        'Commun': Ansi.BRIGHT_WHITE,
        'Rare': Ansi.BRIGHT_CYAN,
        'Épique': Ansi.BRIGHT_MAGENTA,
        'Légendaire': Ansi.BRIGHT_YELLOW,
        'Étrange': Ansi.BRIGHT_GREEN,
    }.get(r, Ansi.WHITE)

def item_display_color(it):
    if is_magic_item(it):
        return Ansi.BRIGHT_BLUE
    return rarity_color(getattr(it, 'rarity', 'Commun'))

# ========================== SCALING ==========================
def _scaled_fraction(base, lvl, per_lvl, softcap_lvl, soft_mult):
    """Calcule 1 + bonus de scaling avec soft cap."""
    l1 = min(lvl, softcap_lvl)
    l2 = max(0, lvl - softcap_lvl)
    return 1.0 + l1 * per_lvl + l2 * per_lvl * soft_mult

def scale_monster(mdef: dict, player, depth: int, elite: bool=False) -> dict:
    """Retourne une copie mdef avec hp/atk/def scalés par niveau joueur + profondeur, avec garde-fous."""
    m = mdef.copy()
    L = max(0, player.level - 1)  # le niveau 1 = base

    # Coeffs
    pl = BALANCE['mon_per_level']
    pd = BALANCE['mon_per_depth']
    capL = BALANCE['mon_softcap_level']
    softM = BALANCE['mon_softcap_mult']

    # Multiplicateurs séparés par stat.
    # "depth_ramp" retarde une partie du scaling: les communs restent pertinents au début.
    depth_ramp = min(1.0, 0.35 + depth * 0.09)
    mult_hp  = _scaled_fraction(1.0, L, pl['hp'],  capL, softM) * (1.0 + depth * pd['hp'] * depth_ramp)
    mult_atk = _scaled_fraction(1.0, L, pl['atk'], capL, softM) * (1.0 + depth * pd['atk'] * depth_ramp)
    mult_def = _scaled_fraction(1.0, L, pl['def'], capL, softM) * (1.0 + depth * pd['def'] * depth_ramp)

    if elite:
        eb = BALANCE['elite_bonus']
        mult_hp  *= (1.0 + eb['hp'])
        mult_atk *= (1.0 + eb['atk'])
        mult_def *= (1.0 + eb['def'])

    # Application
    m['hp']  = max(1, int(round(m['hp']  * mult_hp)))
    m['atk'] = max(1, int(round(m['atk'] * mult_atk)))
    m['def'] = max(0, int(round(m['def'] * mult_def)))

    # ── Garde-fous de jouabilité ──
    # 1) ATK du monstre ne doit pas dépasser X% des PV max du joueur (pics one-shot)
    atk_cap = int(player.max_hp * BALANCE['mon_max_atk_vs_player_hp'])
    if m['atk'] > atk_cap:
        m['atk'] = atk_cap

    # 2) DEF du monstre ne doit pas annuler quasi tous les dégâts du joueur
    def_cap = int(max(0, (player.atk + player.temp_buffs.get('atk', 0)) * BALANCE['mon_max_def_vs_player_atk']))
    if m['def'] > def_cap:
        m['def'] = def_cap

    return m

# ========================== LOOT & SHOP HELPERS ==========================
class DummyPlayer:
    def __init__(self):
        self.equipment={'weapon':None,'armor':None,'accessory':None}
        self.klass='Chevalier'
    def all_specials(self): return {}

def _tiered_value(depth, tiers):
    """Retourne la valeur associée au palier le plus élevé <= depth."""
    for min_depth, value in reversed(tiers):
        if depth >= min_depth:
            return value
    return tiers[0][1]

def _scaled_rarity_weights(depth, base_weights, depth_gain, min_depths):
    w = {k: float(v) for k, v in base_weights.items()}
    for rar, gain in depth_gain.items():
        w[rar] = max(0.0, w.get(rar, 0.0) + max(0, depth) * float(gain))
    for rar, dmin in min_depths.items():
        if depth < dmin:
            w[rar] = 0.0
    return w

def _spell_by_id(sid):
    return SPELLS_BY_ID.get(sid)

def _is_summon_spell_sid(sid):
    return sid in ('summon_slime', 'summon_skeleton', 'summon_dragon', 'summon_afterimage')

def _summon_spell_cooldown_total():
    return max(1, int(BALANCE.get('summon_spell_cooldown_floors', 5)))

def _summon_spell_cooldown_for_sid(sid):
    if sid == 'summon_afterimage':
        return 2
    return _summon_spell_cooldown_total()

def _summon_spell_cd_left(player, sid):
    if not _is_summon_spell_sid(sid):
        return 0
    return max(0, int(getattr(player, 'summon_spell_cds', {}).get(sid, 0)))

def _spell_cast_limit(player):
    specs = player.all_specials()
    if getattr(player, 'klass', '') == 'Mage':
        base = max(1, int(BALANCE.get('mage_start_spell_slots', 3)))
        every = max(1, int(BALANCE.get('mage_spell_slot_every_levels', 5)))
        base += max(0, (player.level - 1) // every)
    else:
        base = 1 + player.level // 4
    bonus = int(specs.get('spell_slots', 0))
    return max(1, base + bonus)

def _spell_casts_left(player):
    return max(0, _spell_cast_limit(player) - player.spells_cast_this_floor)

SPELL_CANTRIP_SIDS = {'pulse'}

def _spell_slot_cost(spell_or_sid):
    if isinstance(spell_or_sid, str):
        sp = _spell_by_id(spell_or_sid)
    else:
        sp = spell_or_sid
    if not sp:
        return 1
    if sp.sid in SPELL_CANTRIP_SIDS:
        return 0
    return {'Rare': 1, 'Épique': 2, 'Légendaire': 3}.get(sp.rarity, 1)

def _spell_can_pay(player, spell_or_sid):
    cost = _spell_slot_cost(spell_or_sid)
    return cost <= 0 or _spell_casts_left(player) >= cost

def _spend_spell_slots(player, spell_or_sid):
    cost = max(0, int(_spell_slot_cost(spell_or_sid)))
    if cost > 0:
        player.spells_cast_this_floor += cost
    return cost

def _spell_softcap_mult_from_pouv(pouv, start, per_pouv, floor_mult):
    excess = max(0.0, float(pouv) - max(0.0, float(start)))
    mult = 1.0 / (1.0 + excess * max(0.0, float(per_pouv)))
    return max(float(floor_mult), min(1.0, mult))

def _spell_heal_softcap_mult(player):
    return _spell_softcap_mult_from_pouv(
        _spell_pouv(player),
        BALANCE.get('spell_heal_softcap_start', 8),
        BALANCE.get('spell_heal_softcap_per_pouv', 0.045),
        BALANCE.get('spell_heal_softcap_min', 0.40),
    )

def _summon_softcap_mult(player):
    return _spell_softcap_mult_from_pouv(
        _spell_pouv(player),
        BALANCE.get('summon_softcap_start', 8),
        BALANCE.get('summon_softcap_per_pouv', 0.035),
        BALANCE.get('summon_softcap_min', 0.45),
    )

def _spell_pouv_breakdown(player):
    specs_pouv = max(0.0, float(player.all_specials().get('pouv', 0)))
    passive_floor_pouv = max(0.0, float(getattr(player, 'passive_specials', {}).get('pouv', 0))) + max(0.0, float(getattr(player, 'floor_specials', {}).get('pouv', 0)))
    equip_pouv = max(0.0, specs_pouv - passive_floor_pouv)
    class_bonus = 0.0
    if getattr(player, 'klass', '') == 'Mage':
        stat_pct = float(BALANCE.get('mage_pouv_stat_pct', 0.055))
        per_lvl = float(BALANCE.get('mage_pouv_per_level', 0.60))
        stats_global = float(max(0, player.max_hp) + max(0, player.atk) + max(0, player.defense))
        class_bonus = max(1.0, stats_global * stat_pct) + max(0.0, (player.level - 1) * per_lvl)
    total = max(0, int(round(specs_pouv + class_bonus)))
    return {
        'total': total,
        'specs': specs_pouv,
        'passive_floor': passive_floor_pouv,
        'equipment': equip_pouv,
        'class_bonus': class_bonus,
    }

def _spell_pouv(player):
    return int(_spell_pouv_breakdown(player).get('total', 0))

def _explore_spell_duration(player):
    # Base 1 étage, puis +1 tous les 2 points de POUV (cap pour éviter l'abus).
    return max(1, min(5, 1 + (_spell_pouv(player) // 2)))

def _teleport_cooldown_duration(player):
    # Base 3 étages, réduit par la POUV (min 1).
    return max(1, 3 - (_spell_pouv(player) // 3))

def _pick_teleport_destination(floor, player_pos):
    if not floor or not getattr(floor, 'down', None):
        return None
    sx, sy = floor.down
    candidates = []
    blocked = set(getattr(floor, 'monsters', set()))
    for dx, dy in ((1,0), (-1,0), (0,1), (0,-1)):
        nx, ny = sx + dx, sy + dy
        if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
            continue
        if floor.grid[ny][nx] != FLOOR:
            continue
        if (nx, ny) in blocked:
            continue
        candidates.append((nx, ny))
    if not candidates:
        return None
    candidates.sort(key=lambda p: abs(p[0] - player_pos[0]) + abs(p[1] - player_pos[1]))
    return candidates[0]

def _explore_stat_spell_values(player, sid):
    """
    Valeurs effectives des sorts d'amélioration de stats en exploration.
    Scalées par POUV (donc naturellement plus fortes pour le Mage).
    """
    sp = _spell_by_id(sid)
    if not sp:
        return {}
    pouv = max(0, _spell_pouv(player))
    if sid in ('arcane_skin', 'warding_mist'):
        pouv_mult = 1.0 + min(0.50, pouv * 0.015)
        bonus = max(1, int(round(sp.power * _spell_power_mult(player) * pouv_mult)))
        return {'spell_defense': bonus}
    if sid == 'focus_sigil':
        crit_gain = round(0.01 + min(0.05, pouv * 0.0015), 3)
        power_gain = round(0.10 + min(0.30, pouv * 0.01), 3)
        return {'spell_crit': crit_gain, 'spell_power': power_gain}
    return {}

def _apply_explore_spell_specials(player, sid):
    sp = _spell_by_id(sid)
    if not sp or sp.kind != 'explore':
        return
    if sid == 'clairvoyance':
        bonus = int(round(sp.power * _spell_power_mult(player)))
        player.floor_specials['fov_bonus'] = max(player.floor_specials.get('fov_bonus', 0), max(0, bonus))
    elif sid in ('arcane_skin', 'warding_mist'):
        bonus = int(_explore_stat_spell_values(player, sid).get('spell_defense', 1))
        player.floor_specials['spell_defense'] = max(player.floor_specials.get('spell_defense', 0), max(0, bonus))
    elif sid == 'focus_sigil':
        vals = _explore_stat_spell_values(player, sid)
        player.floor_specials['spell_crit'] = max(player.floor_specials.get('spell_crit', 0.0), float(vals.get('spell_crit', 0.01)))
        player.floor_specials['spell_power'] = max(player.floor_specials.get('spell_power', 0.0), float(vals.get('spell_power', 0.10)))

def _rebuild_floor_magic_from_active_spells(player):
    player.floor_specials = {}
    for sid, rem in player.active_explore_spells.items():
        if int(rem) > 0:
            _apply_explore_spell_specials(player, sid)

def _spell_power_mult(player):
    specs = player.all_specials()
    pouv = _spell_pouv(player)
    lvl = max(0, player.level - 1)
    # La magie scale surtout sur POUV, avec un léger bonus du niveau.
    return 1.0 + (pouv * 0.08) + (lvl * 0.006) + max(0.0, float(specs.get('spell_power', 0.0)))

def _spell_damage_mult(player):
    specs = player.all_specials()
    pouv = _spell_pouv(player)
    lvl = max(0, player.level - 1)
    # Scaling dégâts volontairement plus doux que le scaling utilitaire.
    pouv_coeff = float(BALANCE.get('spell_damage_mult_pouv_coeff', 0.045))
    return 1.0 + (pouv * pouv_coeff) + (lvl * 0.005) + max(0.0, float(specs.get('spell_power', 0.0)))

def _spell_heal_mult(player):
    specs = player.all_specials()
    pouv = _spell_pouv(player)
    lvl = max(0, player.level - 1)
    pouv_coeff = float(BALANCE.get('spell_heal_mult_pouv_coeff', 0.04))
    return 1.0 + (pouv * pouv_coeff) + (lvl * 0.004) + max(0.0, float(specs.get('spell_power', 0.0)))

def _spell_damage_base(player, spell_power):
    pouv = _spell_pouv(player)
    lvl = max(0, player.level - 1)
    lvl_coeff = float(BALANCE.get('spell_damage_base_lvl_coeff', 0.35))
    pouv_coeff = float(BALANCE.get('spell_damage_base_pouv_coeff', 1.2))
    return spell_power + (lvl * lvl_coeff) + (pouv * pouv_coeff)

def _spell_heal_base(player, spell_power):
    pouv = _spell_pouv(player)
    lvl = max(0, player.level - 1)
    lvl_coeff = float(BALANCE.get('spell_heal_base_lvl_coeff', 0.7))
    pouv_coeff = float(BALANCE.get('spell_heal_base_pouv_coeff', 2.2))
    return spell_power + (lvl * lvl_coeff) + (pouv * pouv_coeff)

def _spell_scroll_price(spell, depth):
    base = {'Commun': 95, 'Rare': 180, 'Épique': 320, 'Légendaire': 560}.get(spell.rarity, 220)
    return int((base + depth * 10) * BALANCE.get('spell_shop_price_mult', 1.0))

def _pick_spell_ids(depth, known_ids, count=1, source='loot'):
    known_ids = set(known_ids or [])
    candidates = [sp for sp in SPELLS if sp.sid not in known_ids]
    if not candidates:
        candidates = SPELLS[:]
    if source == 'sage':
        weights = {'Commun': 40, 'Rare': 40, 'Épique': 17, 'Légendaire': 3}
        if depth >= 10:
            weights = {'Commun': 18, 'Rare': 42, 'Épique': 30, 'Légendaire': 10}
    elif source == 'shop':
        weights = {'Commun': 20, 'Rare': 42, 'Épique': 30, 'Légendaire': 8}
    else:
        weights = {'Commun': 58, 'Rare': 30, 'Épique': 10, 'Légendaire': 2}
        if depth >= 12:
            weights = {'Commun': 32, 'Rare': 36, 'Épique': 22, 'Légendaire': 10}
    picked = []
    pool = candidates[:]
    summon_weight_mult = {
        'summon_slime': 0.45,
        'summon_skeleton': 0.28,
        'summon_dragon': 0.12,
        'summon_afterimage': 0.22,
    }
    for _ in range(min(count, len(pool))):
        total = sum(weights.get(sp.rarity, 1) * summon_weight_mult.get(sp.sid, 1.0) for sp in pool)
        r = random.uniform(0, total)
        acc = 0.0
        chosen = pool[0]
        for sp in pool:
            acc += weights.get(sp.rarity, 1) * summon_weight_mult.get(sp.sid, 1.0)
            if r <= acc:
                chosen = sp
                break
        picked.append(chosen.sid)
        pool = [sp for sp in pool if sp.sid != chosen.sid]
        if not pool:
            break
    return picked

def weighted_choice_by_rarity(depth, unlucky):
    w = _scaled_rarity_weights(
        depth,
        BALANCE.get('rarity_base_weights', RARITY_WEIGHTS_BASE),
        BALANCE.get('rarity_depth_gain', {}),
        BALANCE.get('rarity_min_depth', {}),
    )
    # Malchance réduit la probabilité des meilleures raretés
    if unlucky:
        w['Rare'] = max(0.0, w.get('Rare', 0.0) - 1.0)
        w['Épique'] = max(0.0, w.get('Épique', 0.0) - 2.0)
        w['Légendaire'] = max(0.0, w.get('Légendaire', 0.0) - 1.5)
    total = sum(max(0.0, v) for v in w.values())
    if total <= 0:
        return 'Commun'
    r = random.uniform(0,total); acc = 0
    for k in RARITY_ORDER:
        acc += max(0.0, w.get(k, 0.0))
        if r <= acc:
            return k
    return 'Commun'

def random_item(depth, player):
    unlucky = player.all_specials().get('unlucky',0) > 0
    r = weighted_choice_by_rarity(depth, unlucky)

    # filtrage robuste : ne garde que les vrais Item avec la bonne rareté
    pool = [it for it in ALL_ITEMS if isinstance(it, Item) and getattr(it, 'rarity', None) == r]

    # fallback si la rareté demandée est vide (ex: faute d’accent/clé)
    if not pool:
        pool = [it for it in ALL_ITEMS if isinstance(it, Item)]

    # dernier filet de sécurité (évite IndexError si vraiment vide)
    if not pool:
        # retourne un commun “safe” au cas où
        return Item('Objet inconnu', 'weapon', 0, 1, 0, 0.0, 'Commun', 'Placeholder.', None)

    klass = str(getattr(player, 'klass', '')).lower()
    if klass == 'mage':
        extra = float(BALANCE.get('mage_magic_drop_chance_depth', 0.009)) * max(0, depth)
        force_magic_chance = min(
            float(BALANCE.get('mage_magic_drop_chance_cap', 0.34)),
            float(BALANCE.get('mage_magic_drop_chance_base', 0.14)) + extra
        )
        if random.random() < force_magic_chance:
            magic_pool = [it for it in pool if is_magic_item(it)]
            if not magic_pool:
                magic_pool = [it for it in ALL_ITEMS if isinstance(it, Item) and getattr(it, 'rarity', None) == r and is_magic_item(it)]
            if magic_pool:
                return random.choice(magic_pool)

    return random.choice(pool)

def random_boss_item(depth, player):
    # Coffres de boss: uniquement Rare -> Légendaire, avec montée graduelle.
    target_rarities = ['Rare', 'Épique', 'Légendaire']
    weights = _scaled_rarity_weights(
        depth,
        BALANCE.get('boss_rarity_base_weights', {'Rare': 70, 'Épique': 24, 'Légendaire': 6}),
        BALANCE.get('boss_rarity_depth_gain', {}),
        BALANCE.get('boss_rarity_min_depth', {}),
    )
    total = sum(max(0.0, weights.get(r, 0.0)) for r in target_rarities)
    if total <= 0:
        picked_rarity = 'Rare'
    else:
        r = random.uniform(0, total)
        acc = 0.0
        picked_rarity = 'Rare'
        for rar in target_rarities:
            acc += max(0.0, weights.get(rar, 0.0))
            if r <= acc:
                picked_rarity = rar
                break

    pool = [it for it in ALL_ITEMS if isinstance(it, Item) and getattr(it, 'rarity', None) == picked_rarity]
    if not pool:
        pool = [it for it in ALL_ITEMS if isinstance(it, Item) and getattr(it, 'rarity', None) in target_rarities]
    if not pool:
        return random_item(depth, player)
    return random.choice(pool)

def random_consumable(depth=0, source='loot'):
    pool = CONSUMABLE_POOL[:]
    weights = [24 if c.rarity == 'Commun' else 11 for c in pool]
    if depth >= 10:
        potion_w = 2 if source == 'loot' else 4
        fragment_w = 2 if source == 'loot' else 3
        for hp in HIGH_TIER_POTIONS:
            pool.append(hp)
            if hp.effect == 'summon_full_heal':
                weights.append(1 if source == 'loot' else 2)
            else:
                weights.append(potion_w)
        for fr in GEM_FRAGMENT_POOL:
            pool.append(fr)
            if fr.rarity == 'Commun':
                weights.append(fragment_w + 2)
            elif fr.rarity == 'Rare':
                weights.append(fragment_w)
            else:
                weights.append(max(1, fragment_w - 1))
    return random.choices(pool, weights=weights, k=1)[0]

def _clean_dead_summon(player):
    sm = getattr(player, 'summon', None)
    if isinstance(sm, dict) and int(sm.get('hp', 0)) <= 0:
        player.summon = None

def _active_summon(player):
    _clean_dead_summon(player)
    sm = getattr(player, 'summon', None)
    if not isinstance(sm, dict):
        return None
    if int(sm.get('hp', 0)) <= 0:
        return None
    if sm.get('id') == 'horde':
        _refresh_horde_stats(player, sm)
    return sm

def _afterimage_sprite(player):
    base = player.sprite if getattr(player, 'sprite', None) else SPRITES.get('knight', [])
    return [c(line, Ansi.BRIGHT_CYAN) for line in base]

def _horde_member_stats(player):
    pouv = max(0, _spell_pouv(player))
    pouv_eff = max(0.0, pouv * _summon_softcap_mult(player))
    hp_coeff = float(BALANCE.get('horde_member_pouv_hp', 2.6))
    atk_coeff = float(BALANCE.get('horde_member_pouv_atk', 0.75))
    def_coeff = float(BALANCE.get('horde_member_pouv_def', 0.35))
    return {
        'hp': max(8, 12 + int(pouv_eff * hp_coeff)),
        'atk': max(1, 3 + int(pouv_eff * atk_coeff)),
        'defense': max(0, 1 + int(pouv_eff * def_coeff)),
        'crit': max(0.0, min(0.30, 0.02 + pouv_eff * 0.002)),
    }

def _horde_map_sprite(count):
    ccount = max(1, int(count))
    shown = min(3, ccount)
    extra = max(0, ccount - shown)
    skel = SPRITES.get('skeleton', [])
    if not skel:
        skel = ["[S]"]
    skel_w = max((visible_len(line) for line in skel), default=3)
    padded = [_pad_ansi_right(line, skel_w) for line in skel]
    rows = []
    for line in padded:
        rows.append(c(("  ".join([line] * shown)), Ansi.BRIGHT_WHITE))
    rows.append(c(f"Horde x{ccount}", Ansi.BRIGHT_CYAN))
    if extra > 0:
        rows.append(c(f"(+{extra} squelettes non affichés)", Ansi.BRIGHT_BLACK))
    return rows

def _horde_conversion_chance(player, horde_count):
    # Base + bonus POUV, puis pénalité par taille de horde.
    # Le premier squelette est volontairement capé (jamais > cap).
    pouv = max(0, _spell_pouv(player))
    base = float(BALANCE.get('horde_conversion_base', 0.50))
    pouv_coeff = float(BALANCE.get('horde_conversion_pouv_coeff', 0.010))
    size_penalty = float(BALANCE.get('horde_conversion_size_penalty', 0.03))
    cap = float(BALANCE.get('horde_conversion_cap', 0.60))
    chance = base + (pouv * pouv_coeff) - (max(0, int(horde_count) - 1) * size_penalty)
    return max(0.05, min(cap, chance))

def _refresh_horde_stats(player, horde):
    if not isinstance(horde, dict) or horde.get('id') != 'horde':
        return horde
    count = max(1, int(horde.get('horde_count', 1)))
    member = _horde_member_stats(player)
    old_max = max(1, int(horde.get('max_hp', member['hp'] * count)))
    old_hp = max(0, int(horde.get('hp', old_max)))
    hp_ratio = old_hp / old_max if old_max > 0 else 1.0
    new_max = max(1, member['hp'] * count)
    horde['max_hp'] = new_max
    horde['hp'] = max(0, min(new_max, int(round(new_max * hp_ratio))))
    horde['atk'] = max(1, member['atk'] * count)
    horde['defense'] = max(0, member['defense'] + int(count * 0.12))
    horde['crit'] = member['crit']
    horde['member_hp'] = member['hp']
    horde['member_atk'] = member['atk']
    horde['member_defense'] = member['defense']
    horde['map_sprite'] = _horde_map_sprite(count)
    horde['use_hp_tint'] = False
    horde['can_attack'] = True
    horde['guard_ratio'] = 0.45
    return horde

def _create_horde(player, count=1):
    ccount = max(1, int(count))
    member = _horde_member_stats(player)
    max_hp = member['hp'] * ccount
    horde = {
        'id': 'horde',
        'name': 'Horde',
        'sprite': SPRITES.get('skeleton', []),
        'hp': max_hp,
        'max_hp': max_hp,
        'atk': member['atk'] * ccount,
        'defense': member['defense'],
        'crit': member['crit'],
        'source_sid': 'call_of_dead',
        'horde_count': ccount,
        'member_hp': member['hp'],
        'member_atk': member['atk'],
        'member_defense': member['defense'],
        'can_attack': True,
        'guard_ratio': 0.45,
        'map_sprite': _horde_map_sprite(ccount),
        'use_hp_tint': False,
    }
    return _refresh_horde_stats(player, horde)

def _horde_add_member(player, horde, add=1):
    if not isinstance(horde, dict) or horde.get('id') != 'horde':
        return horde
    add_n = max(1, int(add))
    member = _horde_member_stats(player)
    horde['horde_count'] = max(1, int(horde.get('horde_count', 1))) + add_n
    horde['max_hp'] = max(1, int(horde.get('max_hp', 1)) + member['hp'] * add_n)
    horde['hp'] = min(horde['max_hp'], int(horde.get('hp', 0)) + member['hp'] * add_n)
    return _refresh_horde_stats(player, horde)

def _summon_from_spell(player, sid):
    if sid == 'summon_afterimage':
        pouv = max(0, _spell_pouv(player))
        pouv_eff = max(0.0, pouv * _summon_softcap_mult(player))
        hp_coeff = float(BALANCE.get('summon_afterimage_pouv_hp', 3.0))
        def_coeff = float(BALANCE.get('summon_afterimage_pouv_def', 0.3))
        max_hp = max(18, int(player.max_hp * 0.45) + 8 + int(pouv_eff * hp_coeff))
        return {
            'id': 'afterimage',
            'name': 'Image rémanante',
            'sprite': _afterimage_sprite(player),
            'map_sprite': _afterimage_sprite(player),
            'use_hp_tint': False,
            'hp': max_hp,
            'max_hp': max_hp,
            'atk': 0,
            'defense': max(0, int(player.defense * 0.25) + int(pouv_eff * def_coeff)),
            'crit': 0.0,
            'can_attack': False,
            'guard_ratio': 0.80,
            'source_sid': sid,
        }

    summon_id = {'summon_slime': 'slime', 'summon_skeleton': 'skeleton', 'summon_dragon': 'dragon'}.get(sid)
    if not summon_id:
        return None
    mdef = next((m for m in MONSTER_DEFS if m['id'] == summon_id), None)
    if not mdef:
        return None
    pouv = max(0, _spell_pouv(player))
    pouv_eff = max(0.0, pouv * _summon_softcap_mult(player))
    hp_coeff = float(BALANCE.get('summon_pouv_hp', 4.0))
    atk_coeff = float(BALANCE.get('summon_pouv_atk', 0.8))
    def_coeff = float(BALANCE.get('summon_pouv_def', 0.45))
    base_hp = int(mdef['hp'] * 0.55)
    base_atk = int(mdef['atk'] * 0.55)
    base_def = int(mdef['def'] * 0.55)
    max_hp = max(8, base_hp + 6 + int(pouv_eff * hp_coeff))
    atk = max(1, base_atk + 1 + int(pouv_eff * atk_coeff))
    defense = max(0, base_def + int(pouv_eff * def_coeff))
    return {
        'id': summon_id,
        'name': mdef['name'],
        'sprite': mdef['sprite'],
        'hp': max_hp,
        'max_hp': max_hp,
        'atk': atk,
        'defense': defense,
        'crit': max(0.0, min(0.30, 0.03 + pouv_eff * 0.003)),
        'can_attack': True,
        'guard_ratio': 0.50,
        'source_sid': sid,
    }

def _active_next_combat_buffs(player):
    raw = getattr(player, 'next_combat_buffs', {}) or {}
    fights_left = max(0, int(raw.get('fights_left', 0)))
    if fights_left <= 0:
        return {'atk_pct': 0.0, 'def_pct': 0.0, 'spell_pct': 0.0, 'crit_flat': 0.0, 'fights_left': 0}
    return {
        'atk_pct': max(0.0, float(raw.get('atk_pct', 0.0))),
        'def_pct': max(0.0, float(raw.get('def_pct', 0.0))),
        'spell_pct': max(0.0, float(raw.get('spell_pct', 0.0))),
        'crit_flat': max(0.0, float(raw.get('crit_flat', 0.0))),
        'fights_left': fights_left,
    }

def _grant_next_combat_buff(player, key, amount, fights=3):
    buffs = _active_next_combat_buffs(player)
    caps = {'atk_pct': 0.60, 'def_pct': 0.55, 'spell_pct': 0.70, 'crit_flat': 0.20}
    cur = float(buffs.get(key, 0.0))
    buffs[key] = min(caps.get(key, 0.50), cur + max(0.0, float(amount)))
    buffs['fights_left'] = max(int(buffs.get('fights_left', 0)), max(1, int(fights)))
    player.next_combat_buffs = buffs

def _consume_next_combat_charge(player):
    buffs = _active_next_combat_buffs(player)
    if buffs.get('fights_left', 0) <= 0:
        player.next_combat_buffs = {'atk_pct': 0.0, 'def_pct': 0.0, 'spell_pct': 0.0, 'crit_flat': 0.0, 'fights_left': 0}
        return
    buffs['fights_left'] -= 1
    if buffs['fights_left'] <= 0:
        buffs = {'atk_pct': 0.0, 'def_pct': 0.0, 'spell_pct': 0.0, 'crit_flat': 0.0, 'fights_left': 0}
    player.next_combat_buffs = buffs

def _apply_consumable_effect(player, cns, in_combat=False):
    if cns.effect in ('heal', 'heal_ultra'):
        amount = int(cns.power)
        player.heal(amount)
        return 'used', c(f"+{amount} PV", Ansi.GREEN)
    if cns.effect == 'buff_atk':
        player.temp_buffs['atk'] += int(cns.power)
        player.temp_buffs['turns'] = max(player.temp_buffs['turns'], 3)
        return 'used', c(f"ATK +{int(cns.power)} (3 tours)", Ansi.RED)
    if cns.effect == 'buff_atk_ultra':
        player.temp_buffs['atk'] += int(cns.power)
        player.temp_buffs['turns'] = max(player.temp_buffs['turns'], 4)
        return 'used', c(f"ATK +{int(cns.power)} (4 tours)", Ansi.BRIGHT_RED)
    if cns.effect in ('frag_atk_pct', 'frag_def_pct', 'frag_spell_pct', 'frag_crit_flat'):
        if isinstance(cns.power, (tuple, list)) and len(cns.power) >= 2:
            amount, fights = float(cns.power[0]), int(cns.power[1])
        else:
            amount, fights = float(cns.power), 3
        fights_bonus = max(0, int(player.all_specials().get('frag_duration_bonus', 0)))
        fights = max(1, fights + fights_bonus)
        key = {
            'frag_atk_pct': 'atk_pct',
            'frag_def_pct': 'def_pct',
            'frag_spell_pct': 'spell_pct',
            'frag_crit_flat': 'crit_flat',
        }[cns.effect]
        _grant_next_combat_buff(player, key, amount, fights=fights)
        buffs = _active_next_combat_buffs(player)
        pct = f"{amount*100:.0f}%" if 'pct' in cns.effect else f"{amount:.2f}"
        return 'used', c(f"{cns.name}: bonus {pct} actif ({buffs['fights_left']} combats restants).", Ansi.BRIGHT_MAGENTA)
    if cns.effect == 'summon_full_heal':
        sm = _active_summon(player)
        if not sm:
            return 'blocked', "Aucune invocation active à soigner."
        sm['hp'] = int(sm.get('max_hp', sm.get('hp', 1)))
        return 'used', c(f"{cns.name}: {sm.get('name', 'Invocation')} est entièrement régénérée.", Ansi.BRIGHT_MAGENTA)
    if cns.effect == 'flee':
        if not in_combat:
            return 'blocked', "La pierre de rappel n’a d’effet qu’en combat."
        return 'fled', "Vous utilisez une pierre de rappel : fuite réussie !"
    return 'blocked', "Consommable utilisé."

def _special_price_score(special):
    if not special:
        return 0.0
    score = 0.0
    for k, v in special.items():
        if k == 'regen' and isinstance(v, (int, float)):
            score += 3.2 * v
        elif k == 'thorns' and isinstance(v, (int, float)):
            score += 2.8 * v
        elif k == 'lifesteal' and isinstance(v, (int, float)):
            score += 70.0 * v
        elif k == 'dodge' and isinstance(v, (int, float)):
            score += 90.0 * v
        elif k == 'poison_on_hit' and isinstance(v, (int, float)):
            score += 2.2 * v
        elif k == 'berserk' and isinstance(v, (int, float)):
            score += 10.0 * v
        elif k == 'greed' and isinstance(v, (int, float)):
            score += 8.0 * v
        elif k == 'fov_bonus' and isinstance(v, (int, float)):
            score += 0.8 * v
        elif k == 'special_dmg_mult' and isinstance(v, (int, float)):
            score += 18.0 * max(0.0, v - 1.0)
        elif k == 'spell_power' and isinstance(v, (int, float)):
            score += 80.0 * v
        elif k == 'pouv' and isinstance(v, (int, float)):
            score += 12.0 * v
        elif k == 'spell_slots' and isinstance(v, (int, float)):
            score += 14.0 * v
        elif k == 'spell_damage' and isinstance(v, (int, float)):
            score += 3.0 * v
        elif k == 'spell_defense' and isinstance(v, (int, float)):
            score += 2.4 * v
        elif k == 'vampirism' and isinstance(v, (int, float)):
            score += 1.8 * v
        elif k == 'unlucky' and isinstance(v, (int, float)):
            score -= 80.0 * v
        elif k == 'bleed_self' and isinstance(v, (int, float)):
            score -= 2.5 * v
        elif k == 'special_cost_mult' and isinstance(v, (int, float)):
            score -= 16.0 * max(0.0, v - 1.0)
        elif k in ('cursed', 'heavy', 'glass') and bool(v):
            score -= 4.0
        elif k == 'chaos' and bool(v):
            score += 3.5
    return score

def price_of(it):
    if isinstance(it, Consumable):
        premium = {
            'heal_ultra': 180,
            'buff_atk_ultra': 240,
            'summon_full_heal': 260,
            'frag_atk_pct': 140,
            'frag_def_pct': 140,
            'frag_spell_pct': 170,
            'frag_crit_flat': 165,
        }
        if it.effect in premium:
            return premium[it.effect]
        return {
            'Commun': 12,
            'Rare': 32,
            '\u00c9pique': 52,
            'L\u00e9gendaire': 84,
            '\u00c9trange': 44,
        }.get(it.rarity, 20)

    pos = (
        max(0, it.hp_bonus) * 0.9
        + max(0, it.atk_bonus) * 3.0
        + max(0, it.def_bonus) * 2.4
        + max(0, it.crit_bonus) * 75.0
    )
    neg = (
        abs(min(0, it.hp_bonus)) * 0.6
        + abs(min(0, it.atk_bonus)) * 2.2
        + abs(min(0, it.def_bonus)) * 1.8
        + abs(min(0, it.crit_bonus)) * 55.0
    )
    base_score = max(1.0, pos - neg + _special_price_score(it.special))

    rarity_flat = {'Commun': 7, 'Rare': 16, '\u00c9pique': 29, 'L\u00e9gendaire': 45, '\u00c9trange': 18}
    rarity_mult = {'Commun': 1.00, 'Rare': 1.15, '\u00c9pique': 1.24, 'L\u00e9gendaire': 1.34, '\u00c9trange': 1.10}
    min_price = {'Commun': 8, 'Rare': 16, '\u00c9pique': 28, 'L\u00e9gendaire': 42, '\u00c9trange': 14}

    price = rarity_flat.get(it.rarity, 8) + base_score * rarity_mult.get(it.rarity, 1.0)
    return int(max(min_price.get(it.rarity, 8), round(price)))

def choose_floor_destination(current_depth, direction):
    """
    direction: +1 pour descendre, -1 pour remonter.
    Retourne l'étage cible (int) ou None si annulation.
    """
    if direction > 0:
        options = [
            (current_depth + 1, "Prudent", "danger +, loot +"),
            (current_depth + 2, "Audacieux", "danger ++, loot ++"),
            (current_depth + 3, "Suicidaire", "danger +++, loot +++"),
        ]
        title = "Descente ciblée"
    else:
        options = []
        if current_depth - 1 >= 0:
            options.append((current_depth - 1, "Retour", "plus sûr, moins de loot"))
        if current_depth - 2 >= 0:
            options.append((current_depth - 2, "Retraite rapide", "beaucoup plus sûr"))
        title = "Remontée ciblée"

    if not options:
        return None

    lines = ["Choisissez votre destination :"]
    for i, opt in enumerate(options, 1):
        depth = opt[0]
        risk = opt[1] if len(opt) > 1 else "Inconnu"
        desc = opt[2] if len(opt) > 2 else "—"
        lines.append(f" {i}) Étage {depth} — {risk} ({desc})")
    lines.append(" q) Annuler")
    draw_box(title, lines, width=86)

    while True:
        cmd = input("> ").strip().lower()
        if cmd in ("q", "x", ""):
            return None
        if cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        print("Choix invalide.")

def _upgrade_item_name(name):
    m = re.search(r" \+(\d+)$", name)
    if m:
        lvl = int(m.group(1)) + 1
        return re.sub(r" \+\d+$", f" +{lvl}", name)
    return f"{name} +1"

def _item_upgrade_level(it):
    m = re.search(r" \+(\d+)$", getattr(it, 'name', '') or '')
    return int(m.group(1)) if m else 0

def _item_upgrade_limit(it):
    # None = illimité.
    if isinstance(it, Consumable):
        return 0
    if bool((getattr(it, 'special', {}) or {}).get('cursed', False)):
        return None
    caps = {'Commun': 0, 'Rare': 1, 'Épique': 2, 'Légendaire': None, 'Étrange': 0}
    return caps.get(getattr(it, 'rarity', 'Commun'), 0)

def _item_upgrade_cap_text(it):
    cap = _item_upgrade_limit(it)
    lvl = _item_upgrade_level(it)
    if cap is None:
        return f"+{lvl} / illimité"
    return f"+{lvl} / +{cap} max"

def _can_upgrade_item(it):
    cap = _item_upgrade_limit(it)
    if cap is None:
        return True
    return _item_upgrade_level(it) < cap

def _upgrade_break_chance_for_item(it, base_break_chance):
    ch = float(base_break_chance)
    # Les objets maudits sont plus difficiles à améliorer sans casse.
    if bool((getattr(it, 'special', {}) or {}).get('cursed', False)):
        ch *= 1.9
    return max(0.0, min(0.90, ch))

def _find_fragment_stack_index(player):
    stacks = _consumable_stacks(player)
    for i, st in enumerate(stacks):
        cns = st.get('item')
        if isinstance(cns, Consumable) and str(getattr(cns, 'effect', '')).startswith('frag_'):
            return i
    return None

def _has_fragment_guard(player):
    return _find_fragment_stack_index(player) is not None

def _consume_fragment_guard(player):
    idx = _find_fragment_stack_index(player)
    if idx is None:
        return None
    return _consume_consumable_at(player, idx)

def upgrade_item(it):
    if isinstance(it, Consumable):
        return it
    special = None
    if it.special:
        special = {}
        for k, v in it.special.items():
            if isinstance(v, int):
                special[k] = v + 1
            elif isinstance(v, float):
                special[k] = round(v + 0.01, 2)
            else:
                special[k] = v
    return it._replace(
        name=_upgrade_item_name(it.name),
        hp_bonus=it.hp_bonus + max(1, int(round(max(1, it.hp_bonus) * 0.20))),
        atk_bonus=it.atk_bonus + max(1, int(round(max(1, it.atk_bonus) * 0.20))),
        def_bonus=it.def_bonus + max(1, int(round(max(1, it.def_bonus) * 0.20))),
        crit_bonus=min(0.25, round(it.crit_bonus + 0.01, 2)),
        special=special,
    )

def _casino_upgrade_equipped_item(player, slot, upgrade_cost, upgrade_break_chance, use_fragment_guard=False):
    """
    Tente d'upgrader l'objet équipé dans `slot` de manière transactionnelle.
    Ne consomme jamais d'or si l'upgrade est bloquée.
    """
    old = player.equipment.get(slot)
    if old is None:
        return {'status': 'blocked_missing'}
    if player.gold < upgrade_cost:
        return {'status': 'blocked_gold'}
    if not _can_upgrade_item(old):
        return {'status': 'blocked_cap', 'item': old}

    item_break_chance = _upgrade_break_chance_for_item(old, upgrade_break_chance)
    charged = False
    removed_mods = False
    try:
        player.gold -= upgrade_cost
        charged = True
        player._apply_modifiers(old, remove=True)
        removed_mods = True

        if random.random() < item_break_chance:
            if use_fragment_guard:
                frag_used = _consume_fragment_guard(player)
                player.equipment[slot] = old
                player._apply_modifiers(old, remove=False)
                return {'status': 'guarded', 'item': old, 'frag': frag_used}
            player.equipment[slot] = None
            return {'status': 'broke', 'item': old}

        new_item = upgrade_item(old)
        player.equipment[slot] = new_item
        player._apply_modifiers(new_item, remove=False)
        return {'status': 'upgraded', 'old': old, 'new': new_item}
    except Exception as e:
        # rollback complet: stats + équipement + or
        if removed_mods:
            try:
                player.equipment[slot] = old
                player._apply_modifiers(old, remove=False)
            except Exception:
                pass
        if charged:
            player.gold += upgrade_cost
        return {'status': 'error', 'error': repr(e), 'item': old}

def open_casino(player, depth):
    BOX_W = max(140, MAP_W + 44)
    gamble_cost = BALANCE['casino_gamble_cost_base'] + depth * 2
    upgrade_cost = BALANCE['casino_upgrade_cost_base'] + player.level * 5
    upgrade_break_chance = max(0.0, min(0.50, float(BALANCE.get('casino_upgrade_break_chance', 0.02))))
    while True:
        equipped = [(slot, it) for slot, it in player.equipment.items() if it]

        main_rows = [
            f"Or disponible : {c(str(player.gold), Ansi.YELLOW)}",
            f"Étage : {depth}  |  Niveau : {player.level}",
            "",
            f"1) Miser {gamble_cost} or pour un item aléatoire",
            f"2) Upgrader un objet équipé ({upgrade_cost} or)",
            f"   Risque de casse de base: {upgrade_break_chance*100:.1f}%",
            "q) Quitter",
        ]

        equip_rows = [c("Objets équipés (upgrade)", Ansi.BRIGHT_MAGENTA)]
        if not equipped:
            equip_rows.append(c("(Aucun objet équipé)", Ansi.BRIGHT_BLACK))
        else:
            for i, (slot, it) in enumerate(equipped, 1):
                cap_txt = _item_upgrade_cap_text(it)
                risk_txt = f"{_upgrade_break_chance_for_item(it, upgrade_break_chance)*100:.1f}%"
                state = c("upgrade possible", Ansi.BRIGHT_GREEN) if _can_upgrade_item(it) else c("cap atteint", Ansi.BRIGHT_RED)
                equip_rows.append(f"{i:>2}) {slot}: {item_summary(it)}")
                equip_rows.append(f"    Progression: {cap_txt}  |  Casse: {risk_txt}  |  {state}")
        equip_rows.append("")
        equip_rows.append("Caps: Commun +0, Rare +1, Épique +2, Légendaire illimité, Cursed illimité.")
        equip_rows.append("Un objet cursed casse plus facilement; un fragment peut le protéger sur une tentative.")
        equip_rows.append("Tapez 2 puis le numéro de l'objet.")

        clear_screen()
        draw_box("Casino clandestin", main_rows, width=BOX_W)
        print()
        draw_box("Panneau upgrade", equip_rows, width=BOX_W)

        cmd = input("> ").strip().lower()
        if cmd == "q":
            return
        if cmd == "1":
            if player.gold < gamble_cost:
                print("Pas assez d'or."); time.sleep(0.7); continue
            if len(player.inventory) >= player.inventory_limit:
                print("Inventaire plein."); time.sleep(0.7); continue
            player.gold -= gamble_cost
            roll = random.random()
            loot_depth = depth + (2 if roll < 0.12 else (1 if roll < 0.45 else 0))
            it = random_item(max(0, loot_depth), player)
            player.inventory.append(it)
            draw_box("Casino", [f"Vous gagnez: {item_summary(it)}"], width=BOX_W)
            pause()
            continue
        if cmd == "2":
            if player.gold < upgrade_cost:
                print("Pas assez d'or."); time.sleep(0.7); continue
            if not equipped:
                print("Aucun objet équipé à upgrader."); time.sleep(0.7); continue
            draw_box("Upgrade casino", [f"{i+1}) {slot}: {item_summary(it)}" for i, (slot, it) in enumerate(equipped)] + ["q) Annuler"], width=BOX_W)
            pick = input("> ").strip().lower()
            if pick == "q":
                continue
            if not pick.isdigit() or not (1 <= int(pick) <= len(equipped)):
                print("Choix invalide."); time.sleep(0.6); continue
            idx = int(pick) - 1
            slot, old = equipped[idx]
            # Revalidation sur l'équipement réel au moment de confirmer.
            old = player.equipment.get(slot)
            if old is None:
                draw_box("Upgrade bloqué", [f"Aucun objet équipé dans le slot {slot}."], width=BOX_W)
                pause()
                continue
            if not _can_upgrade_item(old):
                draw_box("Upgrade bloqué", [f"{old.name}: cap d'amélioration atteint ({_item_upgrade_cap_text(old)})."], width=BOX_W)
                pause()
                continue

            use_fragment_guard = False
            is_cursed = bool((getattr(old, 'special', {}) or {}).get('cursed', False))
            if is_cursed:
                item_break_chance = _upgrade_break_chance_for_item(old, upgrade_break_chance)
                if _has_fragment_guard(player):
                    ask = input("Objet cursed: utiliser 1 fragment pour éviter la casse en cas d'échec ? (o/n) ").strip().lower()
                    use_fragment_guard = (ask in ('o', 'y'))
                else:
                    draw_box("Avertissement cursed", [
                        f"{old.name} est maudit.",
                        f"Risque de casse élevé: {item_break_chance*100:.1f}%",
                        "Aucun fragment disponible pour sécuriser la tentative."
                    ], width=BOX_W)
                    time.sleep(0.8)

            result = _casino_upgrade_equipped_item(
                player, slot, upgrade_cost, upgrade_break_chance, use_fragment_guard=use_fragment_guard
            )
            status = result.get('status')
            if status == 'blocked_cap':
                itb = result.get('item')
                draw_box("Upgrade bloqué", [f"{itb.name}: cap d'amélioration atteint ({_item_upgrade_cap_text(itb)})."], width=BOX_W)
            elif status == 'blocked_gold':
                draw_box("Upgrade bloqué", ["Pas assez d'or pour l'amélioration."], width=BOX_W)
            elif status == 'blocked_missing':
                draw_box("Upgrade bloqué", [f"Aucun objet équipé dans le slot {slot}."], width=BOX_W)
            elif status == 'guarded':
                old_it = result.get('item')
                frag_used = result.get('frag')
                frag_name = frag_used.name if frag_used else "fragment"
                draw_box("Protection activée", [
                    f"Tentative ratée sur {old_it.name}, mais l'objet ne casse pas.",
                    f"Consommé: {frag_name}.",
                ], width=BOX_W)
            elif status == 'broke':
                old_it = result.get('item')
                draw_box("Upgrade raté", [f"{old_it.name} se brise pendant l'amélioration.", "Le risque du casino..."], width=BOX_W)
            elif status == 'upgraded':
                old_it = result.get('old')
                new_it = result.get('new')
                draw_box("Upgrade réussi", [f"{old_it.name} -> {new_it.name}"], width=BOX_W)
            else:
                draw_box("Erreur upgrade", [
                    "Une erreur est survenue. L'opération a été annulée.",
                    "Aucun or n'a été perdu.",
                    str(result.get('error', 'inconnue')),
                ], width=BOX_W)
            pause()
            continue
        print("Commande inconnue."); time.sleep(0.6)

def open_altar(player, depth):
    blessing_labels = {
        "vitalite": "Vitalité antique",
        "puissance": "Puissance martiale",
        "rempart": "Rempart sacré",
        "precision": "Précision funeste",
        "clairvoyance": "Clairvoyance",
        "vigueur": "Vigueur du roc",
        "duelliste": "Voie du duelliste",
        "prosperite": "Prospérité dorée",
        "canalisation": "Canalisation arcanique",
        "gemmologie": "Gemmologie",
    }
    pact_labels = {
        "verre": "Pacte de verre",
        "acier": "Pacte d'acier",
        "ombre": "Pacte d'ombre",
        "avidite": "Pacte d'avidité",
        "sang": "Pacte de sang",
        "ruine": "Pacte de ruine",
        "arcanique": "Pacte arcanique",
    }

    def _roll_altar_option():
        kind = random.choice(["blessing", "curse"])
        if kind == "blessing":
            blessing = random.choice(list(blessing_labels.keys()))
            return {
                "kind": "blessing",
                "blessing": blessing,
                "name": f"Bénédiction — {blessing_labels.get(blessing, blessing)}",
            }
        tier = random.choices(
            population=["moderee", "forte", "brutale"],
            weights=[45, 40, 15],
            k=1,
        )[0]
        pact = random.choice(list(pact_labels.keys()))
        return {
            "kind": "curse",
            "pact": pact,
            "tier": tier,
            "name": f"Malédiction — {pact_labels.get(pact, pact)} ({tier})",
        }

    altar_options = [_roll_altar_option(), _roll_altar_option()]
    rows = [
        "L'autel pulse d'une énergie instable.",
        "Deux révélations s'offrent à vous.",
        f"1) {altar_options[0]['name']}",
        f"2) {altar_options[1]['name']}",
        "q) Ignorer",
    ]
    draw_box("Sanctuaire ancien", rows, width=88)
    cmd = input("> ").strip().lower()
    if cmd in ("q", ""):
        return False
    if cmd not in ("1", "2"):
        print("Choix invalide."); time.sleep(0.6)
        return False

    def _gain_int_pct(attr, pct, min_gain=1, floor_value=0):
        base = max(floor_value, int(round(player._altar_dynamic_base(attr))))
        applied = player.add_altar_dynamic_effect(attr, pct, kind='gain', min_delta=min_gain, floor_value=floor_value, is_float=False)
        return int(round(max(0.0, applied))), base

    def _lose_int_pct(attr, pct, min_loss=1, floor_value=0):
        base = max(floor_value, int(round(player._altar_dynamic_base(attr))))
        applied = player.add_altar_dynamic_effect(attr, pct, kind='loss', min_delta=min_loss, floor_value=floor_value, is_float=False)
        return int(round(max(0.0, -applied))), base

    def _gain_crit_pct(pct, min_gain=0.01):
        base = max(0.0, player._altar_dynamic_base('crit'))
        applied = player.add_altar_dynamic_effect('crit', pct, kind='gain', min_delta=min_gain, floor_value=0, is_float=True)
        return round(max(0.0, applied), 3), base

    def _lose_crit_pct(pct, min_loss=0.01):
        base = max(0.0, player._altar_dynamic_base('crit'))
        applied = player.add_altar_dynamic_effect('crit', pct, kind='loss', min_delta=min_loss, floor_value=0, is_float=True)
        return round(max(0.0, -applied), 3), base

    def _gain_special_int_pct(key, pct, min_gain=1):
        base = max(0, int(round(player.all_specials().get(key, 0))))
        delta = max(min_gain, int(round(base * pct)))
        player.passive_specials[key] = int(player.passive_specials.get(key, 0)) + delta
        return delta, base

    def _lose_special_int_pct(key, pct, min_loss=1):
        base = max(0, int(round(player.all_specials().get(key, 0))))
        if base <= 0:
            return 0, 0
        delta = max(min_loss, int(round(base * pct)))
        real_loss = min(base, delta)
        player.passive_specials[key] = int(player.passive_specials.get(key, 0)) - real_loss
        return real_loss, base

    selected_option = altar_options[int(cmd) - 1]
    selected_kind = selected_option["kind"]

    if selected_kind == "blessing":
        blessing = selected_option["blessing"]
        if blessing == "vitalite":
            hp_gain, hp_base = _gain_int_pct("max_hp", 0.10, min_gain=3, floor_value=8)
            player.hp = min(player.max_hp, player.hp + hp_gain)
            msg = f"+{hp_gain} PV max (+10% de {hp_base})"
        elif blessing == "puissance":
            atk_gain, atk_base = _gain_int_pct("atk", 0.12, min_gain=1, floor_value=1)
            msg = f"+{atk_gain} ATK (+12% de {atk_base})"
        elif blessing == "rempart":
            def_gain, def_base = _gain_int_pct("defense", 0.12, min_gain=1, floor_value=0)
            msg = f"+{def_gain} DEF (+12% de {def_base})"
        elif blessing == "precision":
            crit_gain, crit_base = _gain_crit_pct(0.35, min_gain=0.01)
            msg = f"+{crit_gain:.2f} CRIT (+35% de {crit_base:.2f})"
        elif blessing == "clairvoyance":
            fov_gain = 1 if random.random() < 0.75 else 2
            player.passive_specials['fov_bonus'] = player.passive_specials.get('fov_bonus', 0) + fov_gain
            msg = f"+{fov_gain} vision permanente"
        elif blessing == "vigueur":
            hp_gain, hp_base = _gain_int_pct("max_hp", 0.08, min_gain=2, floor_value=8)
            def_gain, def_base = _gain_int_pct("defense", 0.08, min_gain=1, floor_value=0)
            player.hp = min(player.max_hp, player.hp + hp_gain)
            msg = f"+{hp_gain} PV max (+8% de {hp_base}), +{def_gain} DEF (+8% de {def_base})"
        elif blessing == "duelliste":
            atk_gain, atk_base = _gain_int_pct("atk", 0.08, min_gain=1, floor_value=1)
            crit_gain, crit_base = _gain_crit_pct(0.22, min_gain=0.01)
            msg = f"+{atk_gain} ATK (+8% de {atk_base}), +{crit_gain:.2f} CRIT (+22% de {crit_base:.2f})"
        elif blessing == "canalisation":
            pouv_gain, pouv_base = _gain_special_int_pct("pouv", 0.35, min_gain=1)
            msg = f"+{pouv_gain} POUV (+35% de {pouv_base})"
        elif blessing == "gemmologie":
            bonus = 1
            player.passive_specials['frag_duration_bonus'] = int(player.passive_specials.get('frag_duration_bonus', 0)) + bonus
            msg = f"+{bonus} combat de durée pour tous les fragments"
        else:  # prosperite
            gold_gain = int(35 + depth * 12)
            player.gold += gold_gain
            atk_gain, atk_base = _gain_int_pct("atk", 0.06, min_gain=1, floor_value=1)
            msg = f"+{gold_gain} or, +{atk_gain} ATK (+6% de {atk_base})"
        player.blessings_count += 1
        player.altar_history.append(f"Étage {depth} — Bénédiction: {msg}")
        draw_box("Bénédiction", [f"Révélation: {blessing_labels.get(blessing, blessing)}", msg], width=84)
        pause()
        return True
    if selected_kind == "curse":
        # Intensité recalculée dynamiquement selon les stats actuelles du joueur.
        tier = selected_option["tier"]
        mult = {"moderee": 0.85, "forte": 1.00, "brutale": 1.25}[tier]

        pact = selected_option["pact"]
        reward_lines = [f"Révélation: {pact_labels.get(pact, pact)} ({tier})", "Puissance accrue, prix à payer."]

        if pact == "verre":
            atk_gain, atk_base = _gain_int_pct("atk", 0.22 * mult, min_gain=2, floor_value=1)
            hp_loss, hp_base = _lose_int_pct("max_hp", 0.18 * mult, min_loss=4, floor_value=8)
            player.hp = min(player.hp, player.max_hp)
            reward_lines += [f"Bonus: +{atk_gain} ATK (+{int(22*mult)}% de {atk_base})", f"Malus: -{hp_loss} PV max (-{int(18*mult)}% de {hp_base})"]
            altar_log = f"Étage {depth} — Malédiction({tier}) Pacte de verre: +{atk_gain} ATK / -{hp_loss} PV max"
        elif pact == "acier":
            def_gain, def_base = _gain_int_pct("defense", 0.24 * mult, min_gain=1, floor_value=0)
            atk_loss, atk_base = _lose_int_pct("atk", 0.10 * mult, min_loss=1, floor_value=1)
            crit_loss, crit_base = _lose_crit_pct(0.22 * mult, min_loss=0.01)
            pouv_loss, _ = _lose_special_int_pct("pouv", 0.25 * mult, min_loss=1)
            pouv_txt = f", -{pouv_loss} POUV" if pouv_loss > 0 else ""
            reward_lines += [f"Bonus: +{def_gain} DEF (+{int(24*mult)}% de {def_base})", f"Malus: -{atk_loss} ATK (-{int(10*mult)}% de {atk_base}), -{crit_loss:.2f} CRIT{pouv_txt}"]
            altar_log = f"Étage {depth} — Malédiction({tier}) Pacte d'acier: +{def_gain} DEF / -{atk_loss} ATK -{crit_loss:.2f} CRIT{pouv_txt}"
        elif pact == "ombre":
            crit_gain, crit_base = _gain_crit_pct(0.55 * mult, min_gain=0.01)
            fov_gain = max(1, int(round(1 * mult)))
            def_loss, def_base = _lose_int_pct("defense", 0.16 * mult, min_loss=1, floor_value=0)
            hp_loss, hp_base = _lose_int_pct("max_hp", 0.12 * mult, min_loss=3, floor_value=8)
            player.passive_specials['fov_bonus'] = player.passive_specials.get('fov_bonus', 0) + fov_gain
            player.hp = min(player.hp, player.max_hp)
            reward_lines += [f"Bonus: +{crit_gain:.2f} CRIT (+{int(55*mult)}% de {crit_base:.2f}), +{fov_gain} vision", f"Malus: -{def_loss} DEF (-{int(16*mult)}% de {def_base}), -{hp_loss} PV max"]
            altar_log = f"Étage {depth} — Malédiction({tier}) Pacte d'ombre: +{crit_gain:.2f} CRIT +{fov_gain} vision / -{def_loss} DEF -{hp_loss} PV max"
        elif pact == "avidite":
            gold_gain = int((120 + depth * 18) * mult)
            atk_gain, atk_base = _gain_int_pct("atk", 0.10 * mult, min_gain=1, floor_value=1)
            unlucky_gain = max(1, int(round(1 * mult)))
            def_loss, def_base = _lose_int_pct("defense", 0.12 * mult, min_loss=1, floor_value=0)
            player.gold += gold_gain
            player.passive_specials['unlucky'] = player.passive_specials.get('unlucky', 0) + unlucky_gain
            reward_lines += [f"Bonus: +{gold_gain} or, +{atk_gain} ATK (+{int(10*mult)}% de {atk_base})", f"Malus: malchance +{unlucky_gain}, -{def_loss} DEF (-{int(12*mult)}% de {def_base})"]
            altar_log = f"Étage {depth} — Malédiction({tier}) Pacte d'avidité: +{gold_gain} or +{atk_gain} ATK / malchance +{unlucky_gain} -{def_loss} DEF"
        elif pact == "sang":
            hp_gain, hp_base = _gain_int_pct("max_hp", 0.14 * mult, min_gain=4, floor_value=8)
            player.hp = min(player.max_hp, player.hp + hp_gain)
            lifesteal_gain = round(0.03 * mult, 2)
            player.passive_specials['lifesteal'] = round(player.passive_specials.get('lifesteal', 0.0) + lifesteal_gain, 2)
            def_loss, def_base = _lose_int_pct("defense", 0.15 * mult, min_loss=1, floor_value=0)
            crit_loss, _ = _lose_crit_pct(0.18 * mult, min_loss=0.01)
            reward_lines += [f"Bonus: +{hp_gain} PV max (+{int(14*mult)}% de {hp_base}), vol de vie +{lifesteal_gain:.2f}", f"Malus: -{def_loss} DEF (-{int(15*mult)}% de {def_base}), -{crit_loss:.2f} CRIT"]
            altar_log = f"Étage {depth} — Malédiction({tier}) Pacte de sang: +{hp_gain} PV max, vol de vie +{lifesteal_gain:.2f} / -{def_loss} DEF -{crit_loss:.2f} CRIT"
        elif pact == "arcanique":
            pouv_gain, pouv_base = _gain_special_int_pct("pouv", 0.60 * mult, min_gain=1)
            hp_loss, hp_base = _lose_int_pct("max_hp", 0.12 * mult, min_loss=3, floor_value=8)
            def_loss, def_base = _lose_int_pct("defense", 0.10 * mult, min_loss=1, floor_value=0)
            player.hp = min(player.hp, player.max_hp)
            reward_lines += [f"Bonus: +{pouv_gain} POUV (+{int(60*mult)}% de {pouv_base})", f"Malus: -{hp_loss} PV max (-{int(12*mult)}% de {hp_base}), -{def_loss} DEF (-{int(10*mult)}% de {def_base})"]
            altar_log = f"Étage {depth} — Malédiction({tier}) Pacte arcanique: +{pouv_gain} POUV / -{hp_loss} PV max -{def_loss} DEF"
        else:  # ruine
            atk_gain, atk_base = _gain_int_pct("atk", 0.18 * mult, min_gain=2, floor_value=1)
            def_gain, def_base = _gain_int_pct("defense", 0.18 * mult, min_gain=1, floor_value=0)
            hp_loss, hp_base = _lose_int_pct("max_hp", 0.20 * mult, min_loss=5, floor_value=8)
            player.hp = min(player.hp, player.max_hp)
            reward_lines += [f"Bonus: +{atk_gain} ATK (+{int(18*mult)}% de {atk_base}), +{def_gain} DEF (+{int(18*mult)}% de {def_base})", f"Malus: -{hp_loss} PV max (-{int(20*mult)}% de {hp_base})"]
            altar_log = f"Étage {depth} — Malédiction({tier}) Pacte de ruine: +{atk_gain} ATK +{def_gain} DEF / -{hp_loss} PV max"

        player.curses_count += 1
        player.altar_history.append(altar_log)
        draw_box("Pacte sombre", reward_lines, width=140)
        pause()
        return True
    return False

# ========================== INVENTAIRE ==========================
def effect_str(special):
    if not special: return ''
    parts=[]
    for k,v in special.items(): parts.append(f"{k}={v}" if not isinstance(v,bool) else k)
    return ' | Effets: ' + ', '.join(parts)

def item_summary(it):
    if it is None: return '—'
    if isinstance(it, Consumable):
        return f"{it.name} [{it.rarity}] — {it.description}"
    slot_label = {'weapon': 'Arme', 'armor': 'Armure', 'accessory': 'Accessoire'}.get(it.slot, it.slot)
    magic_tag = " [Magique]" if is_magic_item(it) else ""
    # stats colorées
    s_hp   = f"{color_label('HP')}+{color_val('HP', it.hp_bonus)}"
    s_atk  = f"{color_label('ATK')}+{color_val('ATK', it.atk_bonus)}"
    s_def  = f"{color_label('DEF')}+{color_val('DEF', it.def_bonus)}"
    s_crit = f"{color_label('CRIT')}+{color_val('CRIT', f'{it.crit_bonus:.2f}')}"
    s_pouv = ""
    if item_pouv(it):
        s_pouv = f" {color_label('POUV')}+{color_val('POUV', item_pouv(it))}"
    return (f"{it.name} [{slot_label}] [{it.rarity}]{magic_tag} — {it.description} | "
            f"{s_hp} {s_atk} {s_def} {s_crit}{s_pouv}" + effect_str(it.special))

def item_brief_stats(it):
    """Affichage compact pour shop/coffres: bonus + effets, sans légende/description."""
    if it is None:
        return '—'
    if isinstance(it, Consumable):
        return item_summary(it)
    slot_label = {'weapon': 'Arme', 'armor': 'Armure', 'accessory': 'Accessoire'}.get(it.slot, it.slot)
    magic_tag = " [Magique]" if is_magic_item(it) else ""
    stats_parts = []
    if it.hp_bonus:
        stats_parts.append(f"HP{it.hp_bonus:+}")
    if it.atk_bonus:
        stats_parts.append(f"ATK{it.atk_bonus:+}")
    if it.def_bonus:
        stats_parts.append(f"DEF{it.def_bonus:+}")
    if abs(float(it.crit_bonus)) > 1e-9:
        stats_parts.append(f"CRIT{it.crit_bonus:+.2f}")
    pouv_bonus = item_pouv(it)
    if pouv_bonus:
        stats_parts.append(f"POUV{pouv_bonus:+}")
    stats_txt = " ".join(stats_parts) if stats_parts else "Aucun bonus de stats"
    eff_txt = effect_str(it.special)
    return f"{it.name} [{slot_label}] [{it.rarity}]{magic_tag} | {stats_txt}{eff_txt}"

def item_compact_header(it):
    if not isinstance(it, Item):
        return item_brief_stats(it)
    slot_label = {'weapon': 'Arme', 'armor': 'Armure', 'accessory': 'Accessoire'}.get(it.slot, it.slot)
    magic_tag = " [Magique]" if is_magic_item(it) else ""
    return f"{it.name} [{slot_label}] [{it.rarity}]{magic_tag}"

def open_stats_interface(player):
    eq_items = [it for it in player.equipment.values() if it]
    eq_hp = sum(it.hp_bonus for it in eq_items)
    eq_atk = sum(it.atk_bonus for it in eq_items)
    eq_def = sum(it.def_bonus for it in eq_items)
    eq_crit = sum(it.crit_bonus for it in eq_items)
    pouv_info = _spell_pouv_breakdown(player)
    pouv_total = int(pouv_info.get('total', 0))
    pouv_specs = float(pouv_info.get('specs', 0.0))
    pouv_passive = float(pouv_info.get('passive_floor', 0.0))
    pouv_equip = float(pouv_info.get('equipment', 0.0))
    pouv_class = float(pouv_info.get('class_bonus', 0.0))

    core_rows = [
        c("Stats actuelles", Ansi.BRIGHT_WHITE),
        f"HP: {player.hp}/{_fmt_num(player.max_hp)}",
        f"ATK: {_fmt_num(player.atk)} (+temp {_fmt_num(player.temp_buffs['atk'])})",
        f"DEF: {_fmt_num(player.defense)}",
        f"CRIT: {_fmt_num(player.crit)}",
        f"POUV: {_fmt_num(pouv_total)}",
        f"OR: {_fmt_num(player.gold)}",
        "",
        c("Répartition (total = hors équipement + équipement)", Ansi.BRIGHT_CYAN),
        f"HP max: {_fmt_num(player.max_hp)} = {_fmt_num(player.max_hp - eq_hp)} + {_fmt_num(eq_hp)}",
        f"ATK: {_fmt_num(player.atk)} = {_fmt_num(player.atk - eq_atk)} + {_fmt_num(eq_atk)}",
        f"DEF: {_fmt_num(player.defense)} = {_fmt_num(player.defense - eq_def)} + {_fmt_num(eq_def)}",
        f"CRIT: {_fmt_num(player.crit)} = {_fmt_num(player.crit - eq_crit)} + {_fmt_num(eq_crit)}",
        f"POUV (sources): {_fmt_num(pouv_total)} = specs({_fmt_num(pouv_specs)}) + classe({_fmt_num(pouv_class)})",
        f"  ↳ specs({_fmt_num(pouv_specs)}) = passifs/sol({_fmt_num(pouv_passive)}) + équipement({_fmt_num(pouv_equip)})",
    ]

    equip_rows = [c("Sources équipement", Ansi.BRIGHT_MAGENTA)]
    if not eq_items:
        equip_rows.append(c("(Aucun objet équipé)", Ansi.BRIGHT_BLACK))
    else:
        for slot, it in player.equipment.items():
            if not it:
                continue
            slot_name = {"weapon":"Arme","armor":"Armure","accessory":"Accessoire"}.get(slot, slot)
            bonus = f"HP+{_fmt_num(it.hp_bonus)} ATK+{_fmt_num(it.atk_bonus)} DEF+{_fmt_num(it.def_bonus)} CRIT+{_fmt_num(it.crit_bonus)} POUV+{_fmt_num(item_pouv(it))}"
            line = f"- {slot_name}: {it.name} [{it.rarity}] | {bonus}"
            equip_rows.append(c(line, item_display_color(it)))
            if it.special:
                equip_rows.append(f"  Effets: {effect_str(it.special).replace(' | Effets: ','')}")

    altar_rows = [c("Historique des autels", Ansi.BRIGHT_YELLOW)]
    altar_rows.append(f"Bénédictions: {player.blessings_count}  |  Malédictions: {player.curses_count}")
    altar_rows.append("")
    if not player.altar_history:
        altar_rows.append(c("(Aucun effet d'autel appliqué)", Ansi.BRIGHT_BLACK))
    else:
        for i, entry in enumerate(player.altar_history, 1):
            altar_rows.append(f"{i:>2}) {entry}")

    magic_rows = [c("Magie & Grimoire", Ansi.BRIGHT_CYAN)]
    if not player.spellbook_unlocked:
        magic_rows.append("Grimoire: verrouillé")
    else:
        magic_rows.append("Grimoire: débloqué")
        magic_rows.append(f"Parchemins en poche: {len(player.spell_scrolls)}")
        magic_rows.append(f"Lancers restants cet étage: {_spell_casts_left(player)}/{_spell_cast_limit(player)}")
        magic_rows.append(f"Recharge translocation: {player.teleport_spell_cd}/{_teleport_cooldown_duration(player)} étage(s)")
        sm = _active_summon(player)
        if sm:
            magic_rows.append(f"Invocation active: {sm.get('name', '?')} ({sm.get('hp', 0)}/{sm.get('max_hp', 0)} PV)")
        else:
            magic_rows.append("Invocation active: aucune")
        summon_cds = sorted((getattr(player, 'summon_spell_cds', {}) or {}).items())
        summon_cds = [(sid, int(rem)) for sid, rem in summon_cds if int(rem) > 0]
        if summon_cds:
            names = []
            for sid, rem in summon_cds:
                sp = _spell_by_id(sid)
                names.append(f"{sp.name if sp else sid}: {rem}")
            magic_rows.append("Cooldown invocations: " + ", ".join(names))
        else:
            magic_rows.append("Cooldown invocations: aucun")
        active_spells = []
        for sid, rem in sorted(player.active_explore_spells.items()):
            if int(rem) <= 0:
                continue
            sp = _spell_by_id(sid)
            active_spells.append(f"{sp.name if sp else sid}: {int(rem)} étage(s)")
        if active_spells:
            magic_rows.append("Sorts d'exploration actifs:")
            for line in active_spells:
                magic_rows.append(f" - {line}")
        else:
            magic_rows.append("Sorts d'exploration actifs: aucun")

    frag_rows = [c("Fragments (prochains combats)", Ansi.BRIGHT_MAGENTA)]
    frag = _active_next_combat_buffs(player)
    if int(frag.get('fights_left', 0)) > 0:
        frag_rows.append(f"Durée restante: {int(frag.get('fights_left', 0))} combat(s)")
        atk_pct = float(frag.get('atk_pct', 0.0))
        def_pct = float(frag.get('def_pct', 0.0))
        spell_pct = float(frag.get('spell_pct', 0.0))
        crit_flat = float(frag.get('crit_flat', 0.0))
        frag_rows.append(f"ATK: +{int(round(atk_pct * 100))}%  |  DEF: +{int(round(def_pct * 100))}%")
        frag_rows.append(f"Sorts: +{int(round(spell_pct * 100))}%  |  CRIT: +{crit_flat:.2f}")
    else:
        frag_rows.append(c("(Aucun bonus de fragment en attente)", Ansi.BRIGHT_BLACK))

    spec_rows = [c("Effets passifs cumulés", Ansi.BRIGHT_GREEN)]
    specs = player.all_specials()
    if not specs:
        spec_rows.append(c("(Aucun effet spécial actif)", Ansi.BRIGHT_BLACK))
    else:
        for k in sorted(specs.keys()):
            spec_rows.append(f"- {k}: {_fmt_num(specs[k])}")

    clear_screen()
    draw_box("Stats — Vue détaillée", core_rows, width=max(150, MAP_W + 50))
    print()
    draw_box("Stats — Équipement", equip_rows, width=max(150, MAP_W + 50))
    print()
    draw_box("Stats — Autels, Magie & Effets", altar_rows + [""] + magic_rows + [""] + frag_rows + [""] + spec_rows, width=max(150, MAP_W + 50))
    pause()

def preview_delta(player, it):
    if isinstance(it, Consumable): return '(consommable)'
    cur = player.equipment.get(it.slot)
    def tup(obj):
        if not obj:
            return (0,0,0,0,0)
        return (obj.hp_bonus, obj.atk_bonus, obj.def_bonus, obj.crit_bonus, item_pouv(obj))
    dhp, datk, ddef, dcrit, dpouv = tuple(a-b for a,b in zip(tup(it),tup(cur)))
    return ("Δ "
        f"{color_label('HP')}:{color_delta(dhp)} "
        f"{color_label('ATK')}:{color_delta(datk)} "
        f"{color_label('DEF')}:{color_delta(ddef)} "
        f"{color_label('CRIT')}:{color_delta_crit(dcrit)} "
        f"{color_label('POUV')}:{color_delta(dpouv)}")

def open_inventory(player):
    """
    Inventaire 'bi-panneau' façon marchand :
    - Fiche héros (stats colorées)
    - Équipement (3 slots)
    - Sac Objets (équipables/vendables) — actions : e<num>, d<num>, s<num>
    - Sac Consommables (non vendables) — actions : uc<num>, dc<num>
    """
    BOX_W = max(138, MAP_W + 42)

    while True:
        # === PANNEAU 1 : Fiche & Équipement ===
        top_rows = []
        # Fiche
        top_rows.append(c('Fiche du héros', Ansi.BRIGHT_WHITE))
        top_rows.append(player.stats_summary())
        top_rows.append('')

        # Équipement
        top_rows.append(c('Équipement', Ansi.BRIGHT_CYAN))
        slots = [('weapon', 'Arme'), ('armor','Armure'), ('accessory','Accessoire')]
        for key,label in slots:
            it = player.equipment.get(key)
            top_rows.append(f"- {label}: {item_summary(it) if it else '—'}")
        top_rows.append('')

        # Infos de capacité
        top_rows.append(
            f"Sac Objets : {len(player.inventory)}/{player.inventory_limit}   |   "
            f"Sac Consommables : {_consumable_slots_used(player)}/{getattr(player,'consumables_limit',0)} slots "
            f"({_consumable_total_count(player)} objets)"
        )

        # === PANNEAU 2 : Sac Objets (vendables/équipables) ===
        bag_rows = []
        bag_rows.append(c('Sac — Objets', Ansi.BRIGHT_MAGENTA))
        if not player.inventory:
            bag_rows.append(c('(Vide)', Ansi.BRIGHT_BLACK))
        else:
            for i, it in enumerate(player.inventory, 1):
                label = item_summary(it)
                if not isinstance(it, Consumable):
                    # colorer par rareté
                    label = c(label, item_display_color(it))
                bag_rows.append(f"{i:>2}) {label}   {preview_delta(player, it)}")

        bag_rows.append('')
        bag_rows.append(c('Actions objets :', Ansi.BRIGHT_WHITE))
        bag_rows.append(" - e<num> : équiper l’objet")
        bag_rows.append(" - d<num> : jeter l’objet")
        bag_rows.append(" - s<num> : détails de l’objet")
        bag_rows.append(" - q : quitter l’inventaire")

        # === PANNEAU 3 : Sac Consommables (non vendables) ===
        conso_rows = []
        conso_rows.append(c('Sac — Consommables (non vendables)', Ansi.BRIGHT_CYAN))
        cons = _consumable_stacks(player)
        if not cons:
            conso_rows.append(c('(Vide)', Ansi.BRIGHT_BLACK))
        else:
            for i, st in enumerate(cons, 1):
                cns = st['item']
                label = item_summary(cns)
                if str(getattr(cns, 'effect', '')).startswith('frag_'):
                    label = c(label, consumable_display_color(cns))
                conso_rows.append(f"{i:>2}) {label}  x{st['qty']}")

        conso_rows.append('')
        conso_rows.append(c('Actions consommables :', Ansi.BRIGHT_WHITE))
        conso_rows.append(" - uc<num> : utiliser le consommable")
        conso_rows.append(" - ucm<num> / ucmax<num> : utiliser toute la pile du consommable")
        conso_rows.append(" - dc<num> : jeter 1 unité du consommable")

        # === Rendu ===
        clear_screen()
        draw_box('Inventaire — Fiche & Équipement', top_rows, width=BOX_W)
        print()
        draw_box('Inventaire — Sac Objets', bag_rows, width=BOX_W)
        print()
        draw_box('Inventaire — Sac Consommables', conso_rows, width=BOX_W)

        # === Saisie ===
        cmd = input('> ').strip().lower()
        if cmd == 'q':
            break

        # OBJETS : équiper / jeter / détails (e<num>, d<num>, s<num>)
        if (cmd.startswith('e') or cmd.startswith('d') or cmd.startswith('s')) and cmd[1:].isdigit():
            idx = int(cmd[1:]) - 1
            if 0 <= idx < len(player.inventory):
                it = player.inventory[idx]

                # s<num> — détails
                if cmd[0] == 's':
                    print(item_summary(it))
                    print(preview_delta(player, it))
                    pause('Entrée...')
                    continue

                # e<num> — équiper (seulement Items, pas Consommables)
                if cmd[0] == 'e':
                    if isinstance(it, Consumable):
                        print("Ce consommable ne peut pas être équipé."); time.sleep(0.7); continue
                    # équiper : retire du sac puis équipe (l’ancien revient dans le sac via player.equip)
                    player.inventory.pop(idx)
                    player.equip(it)
                    print(f"Vous équipez {it.name}."); time.sleep(0.6)
                    continue

                # d<num> — jeter
                if cmd[0] == 'd':
                    trash = player.inventory.pop(idx)
                    print(f"Jeté: {getattr(trash, 'name', '?')}"); time.sleep(0.6)
                    continue
            else:
                print("Index d’objet invalide."); time.sleep(0.6)
            continue

        # CONSOMMABLES : utiliser tout / utiliser 1 / jeter 1 (ucm<num>, uc<num>, dc<num>)
        if (cmd.startswith('ucm') and cmd[3:].isdigit()) or (cmd.startswith('ucmax') and cmd[5:].isdigit()):
            idx = int(cmd[3:]) - 1 if cmd.startswith('ucm') else int(cmd[5:]) - 1
            cons = _consumable_stacks(player)
            if 0 <= idx < len(cons):
                cns = cons[idx]['item']
                qty = int(cons[idx].get('qty', 1))
                used = 0
                last_msg = ""
                for _ in range(max(0, qty)):
                    status, msg = _apply_consumable_effect(player, cns, in_combat=False)
                    last_msg = msg
                    if status == 'blocked':
                        break
                    _consume_consumable_at(player, idx)
                    used += 1
                if used <= 0:
                    print(last_msg or "Impossible d'utiliser ce consommable.")
                    time.sleep(0.8)
                else:
                    print(f"{cns.name}: {used} utilisation(s) appliquée(s).")
                    if last_msg:
                        print(last_msg)
                    time.sleep(0.7)
            else:
                print("Index de consommable invalide."); time.sleep(0.6)
            continue

        if (cmd.startswith('uc') or cmd.startswith('dc')) and cmd[2:].isdigit():
            idx = int(cmd[2:]) - 1
            cons = _consumable_stacks(player)
            if 0 <= idx < len(cons):
                if cmd.startswith('uc'):
                    cns = cons[idx]['item']
                    status, msg = _apply_consumable_effect(player, cns, in_combat=False)
                    if status != 'blocked':
                        _consume_consumable_at(player, idx)
                    print(msg); time.sleep(0.8 if status == 'blocked' else 0.6)
                else:  # dc<num>
                    dropped = _discard_consumable_at(player, idx, qty=1)
                    print(f"Consommable jeté ({dropped})."); time.sleep(0.6)
            else:
                print("Index de consommable invalide."); time.sleep(0.6)
            continue

        print('Commande inconnue.'); time.sleep(0.6)


# ========================== GRIMOIRE ==========================
def _spell_damage_roll(player, spell_power, rand_min, rand_max, coeff=1.0):
    # Scaling dégâts ralenti pour éviter l'explosion de puissance à POUV moyen/haut.
    base = _spell_damage_base(player, spell_power)
    scaled = int(base * coeff * _spell_damage_mult(player))
    return max(1, scaled + random.randint(rand_min, rand_max))

def _spell_heal_amount(player, spell_power, ratio=1.0):
    base = _spell_heal_base(player, spell_power)
    return max(1, int(round(base * ratio * _spell_heal_mult(player) * _spell_heal_softcap_mult(player))))

def _spell_effect_details(sp, player):
    pouv = _spell_pouv(player)
    lvl = max(0, player.level - 1)
    if sp.sid == 'pulse':
        lo = max(1, int(_spell_damage_base(player, sp.power) * 0.62 * _spell_damage_mult(player)))
        hi = lo + 1
        return f"Combat • dégâts: {lo}-{hi} (cantrip)"
    if sp.sid == 'spark':
        lo = max(1, int(_spell_damage_base(player, sp.power) * 0.92 * _spell_damage_mult(player)))
        hi = lo + 3
        return f"Combat • dégâts: {lo}-{hi} (scale: Niv léger + POUV fort)"
    if sp.sid == 'frostbind':
        lo = max(1, int(_spell_damage_base(player, sp.power) * 0.80 * _spell_damage_mult(player)))
        hi = lo + 3
        weaken = max(1, int(1 + (pouv * 0.16)))
        return f"Combat • dégâts: {lo}-{hi} • -{weaken} ATK ennemi (2 tours)"
    if sp.sid == 'withering_hex':
        lo = max(1, int(_spell_damage_base(player, sp.power) * 0.72 * _spell_damage_mult(player)))
        hi = lo + 2
        weaken = max(1, int(2 + (pouv * 0.22)))
        return f"Combat • dégâts: {lo}-{hi} • -{weaken} ATK ennemi (3 tours)"
    if sp.sid == 'sunder_ward':
        lo = max(1, int(_spell_damage_base(player, sp.power) * 0.72 * _spell_damage_mult(player)))
        hi = lo + 2
        shred = max(1, int(1 + (pouv * 0.20)))
        return f"Combat • dégâts: {lo}-{hi} • -{shred} DEF ennemi (3 tours)"
    if sp.sid == 'call_of_dead':
        sm = _active_summon(player)
        hcount = int(sm.get('horde_count', 0)) if sm and sm.get('id') == 'horde' else 0
        chance = int(round(_horde_conversion_chance(player, hcount + 1) * 100))
        return f"Combat • vs Squelette uniquement • conversion en Horde: {chance}% (diminue avec la taille)"
    if sp.sid == 'arcbolt':
        lo = max(1, int(_spell_damage_base(player, sp.power) * 1.05 * _spell_damage_mult(player)))
        hi = lo + 6
        return f"Combat • dégâts: {lo}-{hi} (variance élevée)"
    if sp.sid == 'siphon':
        lo = max(1, int(_spell_damage_base(player, sp.power) * 0.90 * _spell_damage_mult(player)))
        hi = lo + 4
        return f"Combat • dégâts: {lo}-{hi} • soin: 25% des dégâts"
    if sp.sid == 'mending':
        heal = _spell_heal_amount(player, sp.power, ratio=0.95)
        return f"Combat/Exploration • soin: {heal} PV • sans cooldown"
    if sp.sid == 'greater_mending':
        heal = _spell_heal_amount(player, sp.power, ratio=1.15)
        return f"Combat/Exploration • soin: {heal} PV • sans cooldown"
    if sp.sid == 'rift':
        lo = max(1, int(_spell_damage_base(player, sp.power) * 1.18 * _spell_damage_mult(player))) + 1
        hi = lo + 5
        return f"Combat • dégâts: {lo}-{hi} (impact)"
    if sp.sid == 'nova':
        lo = max(1, int(_spell_damage_base(player, sp.power) * 1.32 * _spell_damage_mult(player))) + 1
        hi = lo + 5
        return f"Combat • dégâts: {lo}-{hi} (burst)"
    if sp.sid == 'comet':
        lo = max(1, int(_spell_damage_base(player, sp.power) * 1.40 * _spell_damage_mult(player))) + 1
        hi = lo + 7
        return f"Combat • dégâts: {lo}-{hi} (burst volatil)"
    if sp.sid in ('summon_slime', 'summon_skeleton', 'summon_dragon', 'summon_afterimage'):
        sm = _active_summon(player)
        name = {
            'summon_slime': 'Slime',
            'summon_skeleton': 'Squelette',
            'summon_dragon': 'Dragonnet',
            'summon_afterimage': 'Image rémanante',
        }.get(sp.sid, 'Invocation')
        cd_left = _summon_spell_cd_left(player, sp.sid)
        cd_total = _summon_spell_cooldown_for_sid(sp.sid)
        cd_txt = f" • recharge: {cd_left}/{cd_total} étage(s)" if cd_left > 0 else f" • recharge: {cd_total} étage(s)"
        if sm:
            return f"Combat/Exploration • invoque {name} (actif: {sm.get('name','?')} {sm.get('hp',0)}/{sm.get('max_hp',0)}){cd_txt}"
        if sp.sid == 'summon_afterimage':
            pouv_eff = max(0.0, pouv * _summon_softcap_mult(player))
            pv = max(18, int(player.max_hp * 0.45) + 8 + int(pouv_eff * float(BALANCE.get('summon_afterimage_pouv_hp', 3.0))))
            return f"Combat/Exploration • invoque {name} • clone non-offensif ({pv} PV) • intercepte 90%{cd_txt}"
        pouv_eff = max(0.0, pouv * _summon_softcap_mult(player))
        pv = max(8, int((12 + sp.power * 4) + pouv_eff * float(BALANCE.get('summon_pouv_hp', 4.0))))
        atk = max(1, int((3 + sp.power) + pouv_eff * float(BALANCE.get('summon_pouv_atk', 0.8))))
        return f"Combat/Exploration • invoque {name} • stats approx: {pv} PV / {atk} ATK{cd_txt}"
    if sp.sid == 'clairvoyance':
        bonus = int(round(sp.power * _spell_power_mult(player)))
        return f"Exploration • vision +{bonus} ({_explore_spell_duration(player)} étage(s))"
    if sp.sid == 'warding_mist':
        bonus = int(_explore_stat_spell_values(player, sp.sid).get('spell_defense', 1))
        return f"Exploration • DEF magique +{bonus} ({_explore_spell_duration(player)} étage(s))"
    if sp.sid == 'prospection':
        gain = int(sp.power * _spell_power_mult(player))
        return f"Exploration • +{gain} or"
    if sp.sid == 'gild_touch':
        gain = int(sp.power * _spell_power_mult(player))
        return f"Exploration • +{gain} or"
    if sp.sid == 'arcane_skin':
        bonus = int(_explore_stat_spell_values(player, sp.sid).get('spell_defense', 1))
        return f"Exploration • DEF magique +{bonus} ({_explore_spell_duration(player)} étage(s))"
    if sp.sid == 'focus_sigil':
        vals = _explore_stat_spell_values(player, sp.sid)
        crit_gain = float(vals.get('spell_crit', 0.01))
        power_gain = float(vals.get('spell_power', 0.10))
        return f"Exploration • CRIT +{crit_gain:.2f} • puissance +{int(round(power_gain*100))}% ({_explore_spell_duration(player)} étage(s))"
    if sp.sid == 'teleport':
        cd_total = _teleport_cooldown_duration(player)
        cd_left = int(player.teleport_spell_cd)
        if cd_left > 0:
            return f"Exploration • téléporte près de l'escalier bas • recharge: {cd_left}/{cd_total} étage(s)"
        return f"Exploration • téléporte près de l'escalier bas • recharge: {cd_total} étage(s)"
    return "Effet inconnu"

def _display_spell(sp, player):
    cost = _spell_slot_cost(sp)
    return f"{sp.name} [{sp.rarity}] ({sp.kind}, coût {cost}) — {_spell_effect_details(sp, player)}"

def _cast_explore_spell(player, sid, floor=None, player_pos=None):
    sp = _spell_by_id(sid)
    if not sp:
        print("Parchemin introuvable."); time.sleep(0.7)
        return player_pos, False
    cost = _spell_slot_cost(sp)
    if not _spell_can_pay(player, sp):
        print(f"Emplacements insuffisants pour ce sort (coût {cost})."); time.sleep(0.8)
        return player_pos, False
    if sid in ('summon_slime', 'summon_skeleton', 'summon_dragon', 'summon_afterimage'):
        if _active_summon(player):
            print("Une invocation est déjà active."); time.sleep(0.7)
            return player_pos, False
        cd_left = _summon_spell_cd_left(player, sid)
        if cd_left > 0:
            print(f"Sort d'invocation en recharge: {cd_left} étage(s) restant(s)."); time.sleep(0.8)
            return player_pos, False
        summon = _summon_from_spell(player, sid)
        if not summon:
            print("Invocation impossible."); time.sleep(0.7)
            return player_pos, False
        player.summon = summon
        player.summon_spell_cds[sid] = _summon_spell_cooldown_for_sid(sid)
        _spend_spell_slots(player, sp)
        draw_box("Magie", [f"{sp.name}: {summon['name']} vous accompagne désormais ({summon['hp']} PV)."], width=96)
        time.sleep(0.8)
        return player_pos, True
    if sid in ('mending', 'greater_mending'):
        ratio = 0.95 if sid == 'mending' else 1.15
        healed = _spell_heal_amount(player, sp.power, ratio=ratio)
        hp_before = player.hp
        player.heal(healed)
        hp_real = max(0, player.hp - hp_before)
        _spend_spell_slots(player, sp)
        draw_box("Magie", [f"{sp.name}: +{hp_real} PV."], width=72)
        time.sleep(0.8)
        return player_pos, True
    if sp.kind != 'explore':
        print("Ce parchemin ne se lance pas hors combat."); time.sleep(0.7)
        return player_pos, False
    if sid == 'clairvoyance':
        if int(player.active_explore_spells.get(sid, 0)) > 0:
            print(f"{sp.name} est déjà actif."); time.sleep(0.7)
            return player_pos, False
        duration = _explore_spell_duration(player)
        player.active_explore_spells[sid] = duration
        _rebuild_floor_magic_from_active_spells(player)
        bonus = int(player.floor_specials.get('fov_bonus', 0))
        _spend_spell_slots(player, sp)
        draw_box("Magie", [f"{sp.name} active: vision +{bonus} pendant {duration} étage(s)."], width=96)
        time.sleep(0.8)
        return player_pos, True
    if sid in ('prospection', 'gild_touch'):
        gain = int(sp.power * _spell_power_mult(player))
        player.gold += gain
        _spend_spell_slots(player, sp)
        draw_box("Magie", [f"{sp.name}: +{gain} or transmuté."], width=72)
        time.sleep(0.8)
        return player_pos, True
    if sid in ('arcane_skin', 'warding_mist'):
        if int(player.active_explore_spells.get(sid, 0)) > 0:
            print(f"{sp.name} est déjà actif."); time.sleep(0.7)
            return player_pos, False
        duration = _explore_spell_duration(player)
        player.active_explore_spells[sid] = duration
        _rebuild_floor_magic_from_active_spells(player)
        bonus = int(player.floor_specials.get('spell_defense', 0))
        _spend_spell_slots(player, sp)
        draw_box("Magie", [f"{sp.name}: DEF magique +{bonus} pendant {duration} étage(s)."], width=96)
        time.sleep(0.8)
        return player_pos, True
    if sid == 'focus_sigil':
        if int(player.active_explore_spells.get(sid, 0)) > 0:
            print(f"{sp.name} est déjà actif."); time.sleep(0.7)
            return player_pos, False
        duration = _explore_spell_duration(player)
        player.active_explore_spells[sid] = duration
        _rebuild_floor_magic_from_active_spells(player)
        vals = _explore_stat_spell_values(player, sid)
        crit_gain = float(vals.get('spell_crit', 0.01))
        power_gain = float(vals.get('spell_power', 0.10))
        _spend_spell_slots(player, sp)
        draw_box("Magie", [f"{sp.name}: CRIT magique +{crit_gain:.2f} et puissance +{int(round(power_gain*100))}% pendant {duration} étage(s)."], width=112)
        time.sleep(0.8)
        return player_pos, True
    if sid == 'teleport':
        if not floor or player_pos is None:
            print("Translocation indisponible ici."); time.sleep(0.7)
            return player_pos, False
        if player.teleport_spell_cd > 0:
            print(f"Translocation en recharge: {player.teleport_spell_cd} étage(s) restant(s)."); time.sleep(0.8)
            return player_pos, False
        dest = _pick_teleport_destination(floor, player_pos)
        if not dest:
            print("Impossible de verrouiller une destination près de l'escalier."); time.sleep(0.8)
            return player_pos, False
        player_pos = dest
        player.teleport_spell_cd = _teleport_cooldown_duration(player)
        _spend_spell_slots(player, sp)
        draw_box("Magie", [f"{sp.name}: vous êtes transloqué près de l'escalier de descente."], width=92)
        time.sleep(0.8)
        return player_pos, True
    print("Ce parchemin ne se lance pas hors combat."); time.sleep(0.7)
    return player_pos, False

def open_spellbook(player, depth, floor=None, player_pos=None):
    if not player.spellbook_unlocked:
        draw_box("Grimoire", ["Vous ne possédez pas encore de grimoire.", "Trouvez le Sorcier pour l'obtenir."], width=82)
        pause()
        return player_pos
    while True:
        cast_cap = _spell_cast_limit(player)
        sm = _active_summon(player)
        summon_cds = getattr(player, 'summon_spell_cds', {}) or {}
        summon_cd_txt = ", ".join(f"{sid}:{int(v)}" for sid, v in sorted(summon_cds.items()) if int(v) > 0)
        rows = [
            f"Étage {depth}  |  Lancers restants: {_spell_casts_left(player)}/{cast_cap}",
            f"POUV total: {_spell_pouv(player)}",
            f"Multiplicateur magique: x{_spell_power_mult(player):.2f}",
            f"Durée sorts d'exploration: {_explore_spell_duration(player)} étage(s)",
            f"Recharge Translocation: {player.teleport_spell_cd}/{_teleport_cooldown_duration(player)} étage(s)",
            (f"Invocation active: {sm.get('name', 'Aucune')} ({sm.get('hp', 0)}/{sm.get('max_hp', 0)} PV)" if sm else "Invocation active: Aucune"),
            ("Cooldown invocations: " + summon_cd_txt) if summon_cd_txt else "Cooldown invocations: aucun",
            "",
            c("Parchemins disponibles", Ansi.BRIGHT_CYAN),
        ]
        active_rows = []
        for sid, rem in player.active_explore_spells.items():
            if int(rem) > 0:
                sp = _spell_by_id(sid)
                if sp:
                    active_rows.append(f"- {sp.name}: {rem} étage(s) restant(s)")
        if active_rows:
            rows += ["", c("Sorts d'exploration actifs", Ansi.BRIGHT_GREEN)]
            rows += active_rows
        if not player.spell_scrolls:
            rows.append(c("(Aucun parchemin)", Ansi.BRIGHT_BLACK))
        else:
            for i, sid in enumerate(player.spell_scrolls, 1):
                sp = _spell_by_id(sid)
                if sp:
                    rows.append(f"{i:>2}) {_display_spell(sp, player)}")
        rows += ["", c(f"Parchemins en poche: {len(player.spell_scrolls)}", Ansi.BRIGHT_MAGENTA)]
        rows += [
            "",
            "Commandes:",
            " Lancement rapide en jeu : & é \" ' ( - (puis è _ ç à)",
            " d<num> : jeter un parchemin",
            " q) Retour",
        ]
        clear_screen()
        draw_box("Grimoire", rows, width=max(120, MAP_W + 42))
        cmd = input("> ").strip().lower()
        if cmd in ("q", ""):
            return player_pos
        if cmd.isdigit():
            idx = int(cmd) - 1
            if not (0 <= idx < len(player.spell_scrolls)):
                print("Index invalide."); time.sleep(0.6); continue
            sid = player.spell_scrolls[idx]
            player_pos, casted = _cast_explore_spell(player, sid, floor, player_pos)
            if casted and sid == 'teleport':
                return player_pos
            continue
        if len(cmd) > 1 and cmd[1:].isdigit() and cmd[0] in ("e", "d"):
            idx = int(cmd[1:]) - 1
            if not (0 <= idx < len(player.spell_scrolls)):
                print("Index invalide."); time.sleep(0.6); continue
            sid = player.spell_scrolls[idx]
            sp = _spell_by_id(sid)
            if cmd[0] == "d":
                player.spell_scrolls.pop(idx)
                print("Parchemin détruit."); time.sleep(0.6); continue
            player_pos, casted = _cast_explore_spell(player, sid, floor, player_pos)
            if casted and sid == 'teleport':
                return player_pos

def open_sage_spell_offer(player, depth):
    def _draw_sage_dialog(title, rows, width=96, side_by_side=False):
        clear_screen()
        sage_sprite = [c(line, Ansi.BRIGHT_BLUE) for line in SPRITES.get('sorcier', [])]
        if sage_sprite:
            draw_box("Le Sorcier", sage_sprite, width=max(76, MAP_W + 8))
            print()
        draw_box(title, rows, width=width)

    if depth in player.sage_depths_visited:
        _draw_sage_dialog("Sorcier", ["Le Sorcier hoche la tête.", "« Nous nous reverrons plus bas. »"], width=72)
        pause()
        return False
    if not player.spellbook_unlocked:
        player.spellbook_unlocked = True
        intro = ["Le Sorcier vous confie un Grimoire vide.", "« Nourris-le avec des parchemins. »"]
        _draw_sage_dialog("Sorcier", intro, width=72, side_by_side=True)
        time.sleep(0.8)
    picks = _pick_spell_ids(depth, set(player.spell_scrolls), count=3, source='sage')
    if not picks:
        _draw_sage_dialog("Sorcier", ["Le Sorcier n'a plus rien à enseigner."], width=64); pause(); return False
    rows = ["Choisissez un parchemin :"]
    for i, sid in enumerate(picks, 1):
        sp = _spell_by_id(sid)
        rows.append(f"{i}) {_display_spell(sp, player)}")
    rows.append("q) Refuser")
    _draw_sage_dialog("Sorcier — Offrande", rows, width=max(96, MAP_W + 26), side_by_side=True)
    cmd = input("> ").strip().lower()
    if cmd.isdigit() and 1 <= int(cmd) <= len(picks):
        sid = picks[int(cmd)-1]
        sp = _spell_by_id(sid)
        player.spell_scrolls.append(sid)
        player.sage_depths_visited.add(depth)
        _draw_sage_dialog("Sorcier", [f"Vous recevez le parchemin: {sp.name}."], width=70)
        pause()
        return True
    else:
        _draw_sage_dialog("Sorcier", ["Le Sorcier range lentement ses parchemins."], width=70); pause()
        return False

# ========================== COMBAT ==========================
def _combat_panel(player, monster, mname, sprite_m, depth, summon=None):
    lines=[]
    lines.append(f"{player.name} vs {mname}")
    p_sprite = player.sprite if getattr(player, 'sprite', None) else SPRITES.get('knight', [])
    p_col = colorize_sprite_by_hp(p_sprite, player.hp, player.max_hp)
    right = sprite_m[:]
    left = p_col[:]
    lines.append(c("Vous", Ansi.BRIGHT_GREEN))

    h = max(len(left), len(right))
    left_w = max((visible_len(x) for x in left), default=20) + 2
    left = left + ['' for _ in range(h-len(left))]
    right = right + ['' for _ in range(h-len(right))]
    for la, rb in zip(left, right):
        lines.append(la + (' ' * max(0, left_w - visible_len(la))) + "    " + rb)
    # Affichage des PV
    if summon and int(summon.get('hp', 0)) > 0:
        summon_name = summon.get('name', 'Invocation')
        lines.append(
            f"Vous: {hp_gauge_text(player.hp, player.max_hp)}  |  "
            f"{summon_name}: {hp_gauge_text(int(summon.get('hp', 0)), int(summon.get('max_hp', 1)))}  |  "
            f"Ennemi: {hp_gauge_text(monster.hp, monster.max_hp)}"
        )
    else:
        lines.append(
            f"Vous: {hp_gauge_text(player.hp, player.max_hp)}    "
            f"Ennemi: {hp_gauge_text(monster.hp, monster.max_hp)}")
    lines.append('')
    if player.spellbook_unlocked:
        spell_label = c(f"3) Sort ({_spell_casts_left(player)}/{_spell_cast_limit(player)})", Ansi.BRIGHT_BLUE)
    else:
        spell_label = c("3) Sort (verrouillé)", Ansi.BRIGHT_BLUE)
    lines.append(
        f"1) Attaquer  2) Spéciale  {spell_label}  4) Consommable  {c('Q) Fuir', Ansi.BRIGHT_RED)}"
    )
    frag = _active_next_combat_buffs(player)
    if frag.get('fights_left', 0) > 0:
        frag_parts = []
        if frag.get('atk_pct', 0.0) > 0: frag_parts.append(f"ATK +{int(round(frag['atk_pct']*100))}%")
        if frag.get('def_pct', 0.0) > 0: frag_parts.append(f"DEF +{int(round(frag['def_pct']*100))}%")
        if frag.get('spell_pct', 0.0) > 0: frag_parts.append(f"Sorts +{int(round(frag['spell_pct']*100))}%")
        if frag.get('crit_flat', 0.0) > 0: frag_parts.append(f"CRIT +{frag['crit_flat']:.2f}")
        if frag_parts:
            lines.append(c(f"Fragments actifs ({frag['fights_left']} combats): " + " • ".join(frag_parts), Ansi.BRIGHT_MAGENTA))
    clear_screen(); draw_box(f"Combat — Étage {depth}", lines, width=max(MAP_W, 80))

def _use_combat_consumable(player):
    cons = _consumable_stacks(player)
    if not cons:
        print('Aucun consommable.'); time.sleep(0.6); return False
    rows = [f"{i+1}) {item_summary(st['item'])}  x{st['qty']}" for i, st in enumerate(cons)]
    rows += ["q) Retour"]
    draw_box("Consommables", rows, width=max(96, MAP_W + 26))
    s = input('> ').strip().lower()
    if s in ('q', ''):
        return False
    if not s.isdigit():
        print("Choix invalide."); time.sleep(0.6); return False
    i = int(s) - 1
    if not (0 <= i < len(cons)):
        print("Index invalide."); time.sleep(0.6); return False
    cns = cons[i]['item']
    status, msg = _apply_consumable_effect(player, cns, in_combat=True)
    if status == 'used':
        _consume_consumable_at(player, i)
        print(msg)
        return True
    if status == 'fled':
        _consume_consumable_at(player, i)
        print(msg)
        return 'fled'
    print(msg); time.sleep(0.6)
    return False

def _cast_combat_spell(player, monster, depth, p_specs, combat_state):
    if not player.spellbook_unlocked:
        print("Vous n'avez pas de grimoire."); time.sleep(0.6); return False, None, None
    choices = []
    for i, sid in enumerate(player.spell_scrolls):
        sp_i = _spell_by_id(sid)
        if not sp_i or sp_i.kind != 'combat':
            continue
        if _spell_can_pay(player, sp_i):
            choices.append((i, sid))
    if not choices:
        print("Aucun sort de combat lançable (emplacements insuffisants)."); time.sleep(0.7); return False, None, None

    rows = [f"{i+1}) {_display_spell(_spell_by_id(sid), player)}" for i, (_, sid) in enumerate(choices)]
    rows += ["q) Annuler"]
    draw_box("Lancer un sort", rows, width=max(96, MAP_W + 26))
    cmd = input("> ").strip().lower()
    if cmd in ("q", ""):
        return False, None, None
    if not cmd.isdigit() or not (1 <= int(cmd) <= len(choices)):
        print("Choix invalide."); time.sleep(0.6); return False, None, None

    _inv_idx, sid = choices[int(cmd)-1]
    sp = _spell_by_id(sid)
    cost = _spell_slot_cost(sp)
    if not _spell_can_pay(player, sp):
        print(f"Emplacements insuffisants pour ce sort (coût {cost})."); time.sleep(0.7); return False, None, None
    bonus = int(round(float(p_specs.get('spell_damage', 0.0))))
    spell_mult = max(0.30, float(p_specs.get('frag_spell_mult', 1.0)))
    spell_crit_chance = max(0.0, min(0.9, player.crit * 0.65 + float(p_specs.get('spell_crit', 0.0))))
    spell_crit = random.random() < spell_crit_chance

    if sid == 'pulse':
        dmg = int((_spell_damage_roll(player, sp.power, 0, 1, coeff=0.62) + bonus) * spell_mult)
        if spell_crit: dmg = max(1, int(dmg * 1.65))
        monster.take_damage(dmg)
        print(c(f"{sp.name} inflige {dmg} dégâts.", Ansi.BRIGHT_MAGENTA))
    elif sid == 'spark':
        dmg = int((_spell_damage_roll(player, sp.power, 0, 3, coeff=0.92) + bonus) * spell_mult)
        if spell_crit: dmg = max(1, int(dmg * 1.65))
        monster.take_damage(dmg)
        print(c(f"{sp.name} inflige {dmg} dégâts.", Ansi.BRIGHT_MAGENTA))
    elif sid == 'frostbind':
        dmg = int(_spell_damage_roll(player, sp.power, 0, 3, coeff=0.80) * spell_mult)
        if spell_crit: dmg = max(1, int(dmg * 1.65))
        monster.take_damage(dmg)
        weaken = max(1, int(1 + (_spell_pouv(player) * 0.16)))
        combat_state['enemy_weaken_turns'] = max(combat_state.get('enemy_weaken_turns', 0), 2)
        combat_state['enemy_weaken_amount'] = max(combat_state.get('enemy_weaken_amount', 0), weaken)
        print(c(f"{sp.name}: {dmg} dégâts et -{weaken} ATK ennemi (2 tours).", Ansi.BRIGHT_CYAN))
    elif sid == 'withering_hex':
        dmg = int(_spell_damage_roll(player, sp.power, 0, 2, coeff=0.72) * spell_mult)
        if spell_crit: dmg = max(1, int(dmg * 1.65))
        monster.take_damage(dmg)
        weaken = max(1, int(2 + (_spell_pouv(player) * 0.22)))
        combat_state['enemy_weaken_turns'] = max(combat_state.get('enemy_weaken_turns', 0), 3)
        combat_state['enemy_weaken_amount'] = max(combat_state.get('enemy_weaken_amount', 0), weaken)
        print(c(f"{sp.name}: {dmg} dégâts et -{weaken} ATK ennemi (3 tours).", Ansi.BRIGHT_CYAN))
    elif sid == 'sunder_ward':
        dmg = int(_spell_damage_roll(player, sp.power, 0, 2, coeff=0.72) * spell_mult)
        if spell_crit: dmg = max(1, int(dmg * 1.65))
        monster.take_damage(dmg)
        shred = max(1, int(1 + (_spell_pouv(player) * 0.20)))
        combat_state['enemy_def_shred_turns'] = max(combat_state.get('enemy_def_shred_turns', 0), 3)
        combat_state['enemy_def_shred_amount'] = max(combat_state.get('enemy_def_shred_amount', 0), shred)
        print(c(f"{sp.name}: {dmg} dégâts et -{shred} DEF ennemi (3 tours).", Ansi.BRIGHT_CYAN))
    elif sid == 'call_of_dead':
        if combat_state.get('monster_id') != 'skeleton':
            print("Appel des morts ne fonctionne que contre un squelette."); time.sleep(0.6); return False, None, None
        sm = _active_summon(player)
        if sm and sm.get('id') != 'horde':
            print("Une autre invocation est déjà active."); time.sleep(0.6); return False, None, None
        current_count = int(sm.get('horde_count', 0)) if sm else 0
        chance = _horde_conversion_chance(player, current_count + 1)
        _spend_spell_slots(player, sp)
        if random.random() <= chance:
            if sm and sm.get('id') == 'horde':
                _horde_add_member(player, sm, add=1)
                new_count = int(sm.get('horde_count', 1))
            else:
                player.summon = _create_horde(player, count=1)
                new_count = 1
            monster.hp = 0
            print(c(f"{sp.name}: conversion réussie ({int(round(chance*100))}%). Horde x{new_count}.", Ansi.BRIGHT_CYAN))
            return True, Ansi.BRIGHT_CYAN, 'convert'
        print(c(f"{sp.name}: échec de conversion ({int(round(chance*100))}% de chance).", Ansi.BRIGHT_BLUE))
        return True, Ansi.BRIGHT_BLUE, 'utility'
    elif sid == 'arcbolt':
        dmg = int((_spell_damage_roll(player, sp.power, 0, 6, coeff=1.05) + bonus) * spell_mult)
        if spell_crit: dmg = max(1, int(dmg * 1.65))
        monster.take_damage(dmg)
        print(c(f"{sp.name} électrise la cible pour {dmg} dégâts.", Ansi.BRIGHT_MAGENTA))
    elif sid == 'siphon':
        dmg = int(_spell_damage_roll(player, sp.power, 0, 4, coeff=0.90) * spell_mult)
        if spell_crit: dmg = max(1, int(dmg * 1.65))
        heal = max(1, int(dmg * 0.25))
        monster.take_damage(dmg)
        player.heal(heal)
        print(c(f"{sp.name}: {dmg} dégâts, +{heal} PV.", Ansi.BRIGHT_MAGENTA))
    elif sid == 'mending':
        heal = _spell_heal_amount(player, sp.power, ratio=0.95)
        hp_before = player.hp
        player.heal(heal)
        hp_real = max(0, player.hp - hp_before)
        print(c(f"{sp.name}: +{hp_real} PV.", Ansi.BRIGHT_CYAN))
    elif sid == 'greater_mending':
        heal = _spell_heal_amount(player, sp.power, ratio=1.15)
        hp_before = player.hp
        player.heal(heal)
        hp_real = max(0, player.hp - hp_before)
        print(c(f"{sp.name}: +{hp_real} PV.", Ansi.BRIGHT_CYAN))
    elif sid == 'rift':
        dmg = int((_spell_damage_roll(player, sp.power, 1, 5, coeff=1.18) + 1 + bonus) * spell_mult)
        if spell_crit: dmg = max(1, int(dmg * 1.65))
        monster.take_damage(dmg)
        print(c(f"{sp.name} fracture l'air pour {dmg} dégâts.", Ansi.BRIGHT_MAGENTA))
    elif sid == 'nova':
        dmg = int((_spell_damage_roll(player, sp.power, 1, 6, coeff=1.32) + 1 + bonus) * spell_mult)
        if spell_crit: dmg = max(1, int(dmg * 1.65))
        monster.take_damage(dmg)
        print(c(f"{sp.name} explose pour {dmg} dégâts !", Ansi.BRIGHT_MAGENTA))
    elif sid == 'comet':
        dmg = int((_spell_damage_roll(player, sp.power, 1, 7, coeff=1.40) + 1 + bonus) * spell_mult)
        if spell_crit: dmg = max(1, int(dmg * 1.65))
        monster.take_damage(dmg)
        print(c(f"{sp.name} percute la cible pour {dmg} dégâts !", Ansi.BRIGHT_MAGENTA))
    elif sid in ('summon_slime', 'summon_skeleton', 'summon_dragon', 'summon_afterimage'):
        if _active_summon(player):
            print("Une invocation est déjà active."); time.sleep(0.6); return False, None, None
        cd_left = _summon_spell_cd_left(player, sid)
        if cd_left > 0:
            print(f"Sort d'invocation en recharge: {cd_left} étage(s) restant(s)."); time.sleep(0.7); return False, None, None
        summon = _summon_from_spell(player, sid)
        if not summon:
            print("Invocation impossible."); time.sleep(0.6); return False, None, None
        player.summon = summon
        player.summon_spell_cds[sid] = _summon_spell_cooldown_for_sid(sid)
        print(c(f"{sp.name}: {summon['name']} rejoint le combat ({summon['hp']} PV).", Ansi.BRIGHT_CYAN))
        _spend_spell_slots(player, sp)
        return True, Ansi.BRIGHT_CYAN, 'summon'
    else:
        print("Ce sort n'est pas utilisable en combat."); time.sleep(0.6); return False, None, None

    if spell_crit:
        print(c("Critique de sort !", Ansi.BRIGHT_MAGENTA))
    _spend_spell_slots(player, sp)
    return True, (Ansi.BRIGHT_MAGENTA if spell_crit else Ansi.BRIGHT_BLUE), 'damage'

def compute_damage(attacker, defender, attacker_specs=None):
    attacker_specs = attacker_specs or {}
    flat_def_pen = max(0, int(round(float(attacker_specs.get('flat_def_pen', 0.0)))))
    eff_def = max(0, int(defender.defense) - flat_def_pen)
    base = max(0, attacker.atk - eff_def)
    variance = random.randint(-2, 3)
    dmg = max(0, base + variance)
    bonus_crit = float(attacker_specs.get('bonus_crit', 0.0))
    is_crit = random.random() < max(0.0, attacker.crit + bonus_crit + (0.05 if attacker_specs.get('glass') else 0.0))
    if is_crit:
        dmg = max(1, int(dmg * 1.8))
    return dmg, is_crit

def _try_grant_normal_key(player, depth, bonus_chance=0.0):
    key_chance = BALANCE.get('normal_key_drop_chance', 0.05) + bonus_chance + min(0.03, depth * 0.002)
    if random.random() < key_chance:
        player.normal_keys += 1
        print(c("Vous récupérez une clé normale.", Ansi.BRIGHT_YELLOW))

def _normal_monster_ids_for_depth(depth):
    if depth <= 1:
        return {'slime', 'bat', 'goblin'}
    if depth <= 3:
        return {'slime', 'bat', 'goblin', 'skeleton'}
    if depth <= 6:
        return {'slime', 'bat', 'goblin', 'skeleton', 'esprit'}
    return {'slime', 'bat', 'goblin', 'skeleton', 'esprit', 'diable', 'dragon'}

def _combat_item_drop_chance(depth):
    return _tiered_value(depth, [
        (0, 0.18),
        (3, 0.23),
        (6, 0.28),
        (10, 0.34),
        (15, 0.40),
    ])

def _combat_cons_drop_chance(depth):
    return _tiered_value(depth, [
        (0, 0.28),
        (6, 0.30),
        (12, 0.34),
    ])

def fight(player, depth, boss=False):
    if boss:
        pool = [m for m in MONSTER_DEFS if m['id'] in ('diable', 'dragon')]
        mdef = random.choice(pool).copy()
    else:
        allowed = _normal_monster_ids_for_depth(depth)
        heavy_pool = [m for m in MONSTER_DEFS if m['id'] in ('diable', 'dragon') and m['id'] in allowed]
        normal_pool = [m for m in MONSTER_DEFS if m['id'] in allowed and m['id'] not in ('diable', 'dragon')]
        heavy_chance = BALANCE.get('nonboss_diable_dragon_chance', 0.04)
        # Pas de diable/dragon trop tôt, puis faible chance ensuite.
        if depth < 6:
            heavy_chance = 0.0
        elif depth < 10:
            heavy_chance *= 0.5
        if heavy_pool and random.random() < heavy_chance:
            mdef = random.choice(heavy_pool).copy()
        else:
            mdef = random.choice(normal_pool).copy()
    mdef = scale_monster(mdef, player, depth, elite=boss)
    if boss:
        boss_mult = BALANCE.get('boss_stat_mult', {})
        mdef['hp'] = max(1, int(round(mdef['hp'] * boss_mult.get('hp', 1.0))))
        mdef['atk'] = max(1, int(round(mdef['atk'] * boss_mult.get('atk', 1.0))))
        mdef['def'] = max(0, int(round(mdef['def'] * boss_mult.get('def', 1.0))))
        until_depth = BALANCE.get('early_boss_nerf_until_depth', 0)
        if depth <= until_depth:
            # Ex: à l'étage 5, on applique environ la moitié du nerf max.
            fade = max(0.0, 1.0 - (depth / max(1, until_depth)))
            nerf = BALANCE.get('early_boss_nerf', {})
            mdef['hp'] = max(1, int(round(mdef['hp'] * (1.0 - nerf.get('hp', 0.0) * fade))))
            mdef['atk'] = max(1, int(round(mdef['atk'] * (1.0 - nerf.get('atk', 0.0) * fade))))
            mdef['def'] = max(0, int(round(mdef['def'] * (1.0 - nerf.get('def', 0.0) * fade))))
        mdef['name'] = f"Boss {mdef['name']}"
        mdef['xp'] = int(mdef['xp'] * 1.35)
        mdef['gold'] = int(mdef['gold'] * 1.40)
    monster = Character(mdef['name'], mdef['hp'], mdef['atk'], mdef['def'], mdef['crit'])
    monster.max_hp = mdef['hp']
    sprite_m = mdef['sprite']
    summon = _active_summon(player)
    p_specs = player.all_specials()
    frag = _active_next_combat_buffs(player)
    frag_active = frag.get('fights_left', 0) > 0
    perm_atk_pct = max(0.0, float(p_specs.get('perm_frag_atk_pct', 0.0)))
    perm_spell_pct = max(0.0, float(p_specs.get('perm_frag_spell_pct', 0.0)))
    perm_def_pct = max(0.0, float(p_specs.get('perm_frag_def_pct', 0.0)))
    perm_crit_flat = max(0.0, float(p_specs.get('perm_frag_crit_flat', 0.0)))
    frag_atk_mult = 1.0 + frag.get('atk_pct', 0.0) + perm_atk_pct
    frag_spell_mult = 1.0 + frag.get('spell_pct', 0.0) + perm_spell_pct
    frag_def_reduct = min(0.55, frag.get('def_pct', 0.0) + perm_def_pct)
    frag_crit_bonus = frag.get('crit_flat', 0.0) + perm_crit_flat

    def _finalize_fight():
        if frag_active:
            _consume_next_combat_charge(player)

    poison_turns=0
    p_specs['bonus_crit'] = float(p_specs.get('spell_crit', 0.0)) + frag_crit_bonus
    p_specs['frag_spell_mult'] = frag_spell_mult
    combat_state = {
        'enemy_weaken_turns': 0,
        'enemy_weaken_amount': 0,
        'enemy_def_shred_turns': 0,
        'enemy_def_shred_amount': 0,
        'monster_id': mdef.get('id'),
    }
    turn_idx = 0

    def _summon_strike():
        sm = _active_summon(player)
        if not sm or not monster.is_alive():
            return
        if not bool(sm.get('can_attack', True)) or int(sm.get('atk', 0)) <= 0:
            return
        dummy = Character(sm.get('name', 'Invocation'), max(1, int(sm.get('hp', 1))), int(sm.get('atk', 1)), int(sm.get('defense', 0)), crit=float(sm.get('crit', 0.03)))
        dummy.max_hp = max(1, int(sm.get('max_hp', dummy.hp)))
        s_pen = combat_state.get('enemy_def_shred_amount', 0) if combat_state.get('enemy_def_shred_turns', 0) > 0 else 0
        s_dmg, s_crit = compute_damage(dummy, monster, {'bonus_crit': 0.0, 'flat_def_pen': s_pen})
        if s_dmg > 0:
            monster.take_damage(s_dmg)
            msg = f"Invocation ({sm.get('name','?')}) inflige {s_dmg} dégâts."
            if s_crit:
                msg += " Critique !"
            print(c(msg, Ansi.BRIGHT_CYAN))

    while player.is_alive() and monster.is_alive():
        turn_idx += 1
        took_damage_this_turn = False
        used_conso = False
        summon = _active_summon(player)
        _combat_panel(player, monster, mdef['name'], sprite_m, depth, summon=summon)
        cmd=input('> ').strip().lower()
        if cmd=='1':
            atk_specs = dict(p_specs)
            if combat_state.get('enemy_def_shred_turns', 0) > 0:
                atk_specs['flat_def_pen'] = combat_state.get('enemy_def_shred_amount', 0)
            dmg_roll, crit_hit = compute_damage(player, monster, atk_specs)
            dmg = dmg_roll + player.temp_buffs['atk']
            dmg = int(max(1, round(dmg * frag_atk_mult)))
            # Berserk : si PV <= 50%, bonus multiplicatif
            if player.hp <= player.max_hp // 2:
                bz = p_specs.get('berserk', 0.0)  # ex: 0.5 = +50%
                if bz:
                    dmg = int(dmg * (1.0 + bz))
            monster.take_damage(dmg); print(c(f"Vous infligez {dmg} dégâts.", Ansi.BRIGHT_GREEN))
            if crit_hit:
                print(c("Coup critique !", Ansi.BRIGHT_YELLOW))
            if p_specs.get('lifesteal'): player.heal(int(dmg* p_specs['lifesteal']))
            if p_specs.get('poison_on_hit'): poison_turns = max(poison_turns, 2)
            _summon_strike()
        elif cmd=='2':
            base_cost = max(1, player.max_hp//8 + 2)  # ou ton coût actuel/plus punitif
            cost_mult = p_specs.get("special_cost_mult", 1.0)
            if getattr(player, 'klass', '') == 'Mage':
                pouv_coeff = float(BALANCE.get('mage_special_pouv_coeff', 0.015))
                class_mult = float(BALANCE.get('mage_special_damage_mult', 0.78))
            else:
                pouv_coeff = 0.03
                class_mult = 1.0
            dmg_mult  = p_specs.get("special_dmg_mult", 1.0) * (1.0 + _spell_pouv(player) * pouv_coeff) * class_mult

            cost = int(base_cost * cost_mult)
            if player.hp > cost:
                player.take_damage(cost)
                burst = int(((player.atk + player.temp_buffs['atk']) * 2 + random.randint(0,6)) * dmg_mult)
                burst = int(max(1, round(burst * frag_atk_mult)))
                monster.take_damage(burst)
                print(c(f"Spéciale ! -{cost} PV, {burst} dégâts.", Ansi.BRIGHT_MAGENTA))
                _summon_strike()
            else:
                print("Pas assez de PV pour la spéciale.")
                time.sleep(0.6)
                continue
        elif cmd=='3':
            casted, _spell_flash, spell_action = _cast_combat_spell(player, monster, depth, p_specs, combat_state)
            if not casted:
                continue
            if spell_action == 'damage':
                _summon_strike()
        elif cmd=='4':
            if used_conso:
                print("Vous avez déjà utilisé un consommable ce tour."); time.sleep(0.6)
            else:
                conso_result = _use_combat_consumable(player)
                if conso_result == 'fled':
                    _finalize_fight()
                    return 'fled'
                if conso_result is True:
                    used_conso = True
                else:
                    continue
        elif cmd=='q':
            if random.random()<0.5:
                print('Vous fuyez.'); time.sleep(0.6)
                _finalize_fight()
                return 'fled'
            else: print('Fuite ratée !')
        else:
            print('Choix invalide.')
            time.sleep(0.6)
            continue
        # DOT poison
        if poison_turns>0 and monster.is_alive():
            dot = max(1, 1 + depth//2)
            monster.take_damage(dot); poison_turns-=1
            print(f"Poison inflige {dot} dégâts.")
        # Riposte
        if monster.is_alive():
            mdmg, _mcrit = compute_damage(monster, player)
            if combat_state.get('enemy_weaken_turns', 0) > 0:
                mdmg = max(0, mdmg - combat_state.get('enemy_weaken_amount', 0))
            mdmg = max(0, mdmg - int(p_specs.get('spell_defense', 0)))
            if frag_def_reduct > 0:
                mdmg = max(0, int(round(mdmg * (1.0 - frag_def_reduct))))
            if random.random() < p_specs.get('dodge', 0.0):
                print('Vous esquivez !'); mdmg = 0
            sm = _active_summon(player)
            if mdmg > 0 and sm:
                guard_ratio = max(0.0, min(1.0, float(sm.get('guard_ratio', 0.5))))
                absorb_raw = max(1, int(math.ceil(mdmg * guard_ratio)))
                player_part = max(0, mdmg - absorb_raw)
                absorb_real = max(0, absorb_raw - int(sm.get('defense', 0)))
                sm['hp'] = max(0, int(sm.get('hp', 0)) - absorb_real)
                mdmg = player_part
                print(c(f"{sm.get('name','Invocation')} intercepte {absorb_raw} dégâts ({absorb_real} subis).", Ansi.BRIGHT_CYAN))
                if int(sm.get('hp', 0)) <= 0:
                    print(c(f"{sm.get('name','Invocation')} est détruite.", Ansi.BRIGHT_RED))
                    player.summon = None
            player.take_damage(mdmg)
            if mdmg > 0: took_damage_this_turn = True
            print(c(f"{mdef['name']} inflige {mdmg} dégâts.", Ansi.BRIGHT_RED))
            if p_specs.get('thorns', 0) and mdmg > 0:
                monster.take_damage(p_specs['thorns'])
                print(f"Épines renvoient {p_specs['thorns']} dégâts.")
        # Effets temporaires        
        if player.temp_buffs['turns'] > 0:
            player.temp_buffs['turns'] -= 1
            if player.temp_buffs['turns'] == 0:
                player.temp_buffs['atk'] = 0
        if combat_state.get('enemy_weaken_turns', 0) > 0:
            combat_state['enemy_weaken_turns'] -= 1
            if combat_state['enemy_weaken_turns'] == 0:
                combat_state['enemy_weaken_amount'] = 0
        if combat_state.get('enemy_def_shred_turns', 0) > 0:
            combat_state['enemy_def_shred_turns'] -= 1
            if combat_state['enemy_def_shred_turns'] == 0:
                combat_state['enemy_def_shred_amount'] = 0
        # Régénération    
        raw_rg = int(p_specs.get('regen', 0))
        if raw_rg > 0:
            # cadence : 1 = chaque tour, 2 = un tour sur deux, etc.
            if turn_idx % max(1, BALANCE.get('regen_every_n_turns', 1)) == 0:
                cap_flat = int(BALANCE.get('regen_cap_flat', 5))
                cap_frac = int(player.max_hp * BALANCE.get('regen_cap_frac', 0.05))
                cap = max(1, min(cap_flat, cap_frac))
                rg = min(raw_rg, cap)
                if took_damage_this_turn:
                    rg = int(rg * BALANCE.get('regen_on_hit_mult', 0.5))  # grave wounds
                if rg > 0 and player.is_alive():
                    before = player.hp
                    player.heal(rg)
                    healed = player.hp - before
                    if healed > 0:
                        print(f"Régénération +{healed} PV.")

        time.sleep(0.6)

        if monster.hp <= 0:
            print(c('Victoire !', Ansi.BRIGHT_GREEN))
            xp_gain   = int((mdef['xp']   + monster.max_hp//4) * BALANCE['combat_xp_mult'])
            gold_gain = int((mdef['gold'] + random.randint(0, max(1, monster.max_hp//6))) * BALANCE['combat_gold_mult'])
            player.gain_xp(xp_gain)
            player.gold += gold_gain
            # greed bonus
            greed = p_specs.get('greed', 0.0)  # ex: 0.30 = +30%
            gold_gain = int(gold_gain * (1.0 + greed))
            # Affichage des gains
            print(
                f"+{color_val('XP', xp_gain)} {color_label('XP')}, "
                f"+{color_val('OR', gold_gain)} {color_label('OR')}"
            )
            # Drop d'objet (indépendant)
            if random.random() < _combat_item_drop_chance(depth):
                item = random_item(depth, player)
                print('Butin:', item_summary(item))
                if len(player.inventory) < player.inventory_limit:
                    player.inventory.append(item)

            # Drop de consommable (indépendant de l'objet)
            if random.random() < _combat_cons_drop_chance(depth):
                cons = random_consumable(depth, source='loot')
                print('Butin:', item_summary(cons))
                _add_consumable(player, cons, qty=1)

            spell_drop_chance = BALANCE.get('spell_drop_base_chance', 0.01) + depth * BALANCE.get('spell_drop_depth_bonus', 0.001)
            spell_drop_cap = 0.08
            if getattr(player, 'klass', '') == 'Mage':
                spell_drop_chance *= float(BALANCE.get('mage_spell_drop_mult', 1.55))
                spell_drop_cap = float(BALANCE.get('mage_spell_drop_cap', 0.12))
            if random.random() < min(spell_drop_cap, spell_drop_chance):
                sid_list = _pick_spell_ids(depth, set(player.spell_scrolls), count=1, source='loot')
                if sid_list:
                    sid = sid_list[0]
                    sp = _spell_by_id(sid)
                    player.spell_scrolls.append(sid)
                    print(c(f"Butin rare: parchemin {sp.name}.", Ansi.BRIGHT_BLUE))

            if boss:
                player.boss_keys += 1
                print(c("Clé de coffre de boss obtenue.", Ansi.BRIGHT_MAGENTA))
                _try_grant_normal_key(player, depth, bonus_chance=0.10)
            else:
                _try_grant_normal_key(player, depth)

            pause()
            _finalize_fight()
            return ('win', mdef['id'])
    _finalize_fight()
    return 'dead'

# ========================== QUÊTES ==========================
NPC_NAMES = ['Alia','Borin','Cedric','Dara','Elio','Fara','Gunnar','Hilda','Ilan','Jora']

def make_quest(kind, player_level, giver_pos, giver_name, giver_floor):
    qid = random.randint(1000,9999)
    if kind=='slay':
        target = random.choice(['goblin','skeleton','esprit','slime','diable']); amount = random.randint(2,4)
        reward_xp = 12 + 4*amount + player_level*2; reward_gold = 10 + 5*amount + player_level*2
    else:
        target = 'combats'; amount = random.randint(2,3)
        reward_xp = 14 + 6*amount + player_level*2; reward_gold = 12 + 4*amount + player_level*2
    reward_xp   = int(reward_xp   * BALANCE['quest_xp_mult'])
    reward_gold = int(reward_gold * BALANCE['quest_gold_mult'])
    return Quest(qid, kind, target, amount, 0, giver_floor, giver_pos, giver_name, reward_xp, reward_gold, 'Active')

def maybe_autocomplete_quests(player):
    completed=[]
    for q in list(player.quests_active):
        if q.type in ('slay','survive') and q.progress >= q.amount:
            player.gain_xp(q.reward_xp)
            player.gold += q.reward_gold
            completed.append(q)
    if completed:
        for q in completed:
            player.quests_done.append(q)
            player.quests_active = [qq for qq in player.quests_active if qq.qid != q.qid]
        lines=[f"[{q.qid}] récompense: +{q.reward_xp} XP, +{q.reward_gold} or" for q in completed]
        draw_box('Quêtes terminées', lines, width=72); pause()

# ========================== JOURNAL ==========================
def journal(player):
    rows=[]
    if not player.quests_active and not player.quests_done:
        rows.append('(aucune quête)')
    if player.quests_active:
        rows.append('-- Actives --')
        for q in player.quests_active:
            where = f"Étage {q.giver_floor}"
            if q.type=='slay': rows.append(f"[{q.qid}] Chasse: {q.progress}/{q.amount} {q.target}(s) — {where}")
            else: rows.append(f"[{q.qid}] Survie: {q.progress}/{q.amount} combats — {where}")
    if player.quests_done:
        rows.append('')
        rows.append('-- Terminées --')
        for q in player.quests_done:
            rows.append(f"[{q.qid}] ✔ {q.reward_xp} XP, {q.reward_gold} or (Donneur étage {q.giver_floor})")
    clear_screen(); draw_box('Journal de quêtes', rows, width=max(MAP_W, 80)); pause()

# ========================== CARTE & ÉTAGES ==========================
def _monsters_per_floor(depth):
    # Nombre de monstres aléatoire par étage, avec une plage qui monte doucement.
    low = max(4, 5 + depth // 2)
    high = max(low + 1, 8 + depth + depth // 2)
    return random.randint(low, high)

def _map_items_per_floor(depth):
    # Les étages initiaux restent sobres; la densité d'objets monte ensuite.
    return _tiered_value(depth, [
        (0, BALANCE.get('map_items_per_floor', 2)),
        (4, 3),
        (10, 4),
    ])

class Floor:
    def __init__(self,depth):
        self.depth=depth
        # Génération "Zelda‑like" : pièces + couloirs droits
        self.grid = [[WALL for _ in range(MAP_W)] for _ in range(MAP_H)]
        self._carve_rooms_and_corridors(room_attempts=18, min_size=4, max_size=8)
        # Start dans la 1ère pièce
        self.start = self._first_room_center
        occ=set([self.start])
        # Escaliers écartés
        self.up = None if depth==0 else self._far_floor_pos(self.start, min_dist=18, occupied=occ)
        if self.up: occ.add(self.up)
        self.down = self._far_floor_pos(self.up or self.start, min_dist=20, occupied=occ); occ.add(self.down)

        # PNJ avec quêtes
        self.npcs = {}
        npc_count = random.randint(BALANCE['npcs_min'], BALANCE['npcs_max'])
        for _ in range(npc_count):
            pos = self._random_floor_pos(occ); occ.add(pos)
            name = random.choice(NPC_NAMES); kind = random.choice(['slay','survive'])
            self.npcs[pos] = {'name': name, 'quest': make_quest(kind, depth, pos, name, depth)}
        self.sages = set()
        sage_start = BALANCE.get('spell_sage_start_depth', 3)
        sage_every = max(1, BALANCE.get('spell_sage_every', 5))
        if depth >= sage_start and ((depth - sage_start) % sage_every == 0):
            spos = self._far_floor_pos(self.start, min_dist=12, occupied=occ)
            if spos:
                self.sages.add(spos)
                occ.add(spos)

        # Shops
        self.shops=set()
        if random.random()<0.5 or depth%2==0:
            s=self._random_floor_pos(occ); self.shops.add(s); occ.add(s)
        # Monstres & Items
        self.monsters=set()
        for _ in range(_monsters_per_floor(depth)):
            pos=self._random_floor_pos(occ); occ.add(pos); self.monsters.add(pos)
        self.items = set()
        # Items aléatoires, au moins 1 par étage
        for _ in range(_map_items_per_floor(depth)):
            pos = self._random_floor_pos(occ); occ.add(pos); self.items.add(pos)

        # Trésors
        self.treasures = set()
        self.boss_treasures = set()
        self.treasure_types = {}

        # Salles verrouillées
        self.locked_doors = {}
        for _ in range(BALANCE.get('locked_rooms_per_floor', 1)):
            self._add_locked_room(occ, chest_type='normal')
        boss_room = (depth > 0 and depth % 5 == 0) or (random.random() < BALANCE.get('boss_locked_room_chance', 0.0))
        if boss_room:
            self._add_locked_room(occ, chest_type='boss')

        # Trésors additionnels (au moins 1 par étage)
        tpos = self._far_floor_pos(self.start, min_dist=10, occupied=occ)
        if tpos:
            self.treasures.add(tpos)
            self.treasure_types[tpos] = 'normal'
            occ.add(tpos)
        if random.random()<0.25:
            t2 = self._random_floor_pos(occ)
            self.treasures.add(t2)
            self.treasure_types[t2] = 'normal'
            occ.add(t2)
        # Fog & POIs vus
        self.discovered=set(); self.visible=set()
        self.seen_shops=set(); self.seen_npcs=set(); self.seen_stairs=set(); self.seen_treasures=set()
        self.seen_altars=set(); self.seen_casinos=set(); self.seen_sages=set()
        self.elites = set()
        if depth > 0 and depth % 5 == 0:
            epos = self._far_floor_pos(self.start, min_dist=14, occupied=occ)
            if epos:
                self.elites.add(epos)
                occ.add(epos)

        # Sanctuaires / Autels
        self.altars = set()
        altar_chance = BALANCE['altar_on_boss_floor_chance'] if depth > 0 and depth % 5 == 0 else BALANCE['altar_spawn_chance']
        if random.random() < altar_chance:
            apos = self._random_floor_pos(occ)
            self.altars.add(apos)
            occ.add(apos)

        # Casino: tous les 5 étages
        self.casinos = set()
        if depth > 0 and depth % 5 == 0:
            cpos = self._far_floor_pos(self.start, min_dist=8, occupied=occ)
            if cpos:
                self.casinos.add(cpos)
                occ.add(cpos)

        def _pick_theme(depth):
        # Variante simple : cycler selon la profondeur
            return THEMES[depth % len(THEMES)]

        self.theme = _pick_theme(depth)

    def _add_locked_room(self, occupied, chest_type='normal'):
        # Petite salle 3x3 derrière une porte verrouillée.
        for _ in range(400):
            w, h = 3, 3
            x = random.randint(2, MAP_W - w - 3)
            y = random.randint(2, MAP_H - h - 3)
            if any(self.grid[yy][xx] == FLOOR for yy in range(y-1, y+h+1) for xx in range(x-1, x+w+1)):
                continue

            # Choisir une case murale voisine d'un sol existant qui servira de porte
            border_candidates = []
            for xx in range(x, x+w):
                border_candidates.extend([(xx, y-1), (xx, y+h)])
            for yy in range(y, y+h):
                border_candidates.extend([(x-1, yy), (x+w, yy)])
            random.shuffle(border_candidates)

            door = None
            for bx, by in border_candidates:
                if not (1 <= bx < MAP_W-1 and 1 <= by < MAP_H-1):
                    continue
                # Adjacent à du sol existant pour que le joueur puisse tenter l'ouverture.
                around = [(bx+1,by), (bx-1,by), (bx,by+1), (bx,by-1)]
                if any(self.grid[ay][ax] == FLOOR for ax, ay in around if 0 <= ax < MAP_W and 0 <= ay < MAP_H):
                    door = (bx, by)
                    break
            if not door:
                continue

            # Creuse la salle (fermée par la porte verrouillée)
            for yy in range(y, y+h):
                for xx in range(x, x+w):
                    self.grid[yy][xx] = FLOOR
                    occupied.add((xx, yy))

            dx, dy = door
            self.grid[dy][dx] = WALL
            self.locked_doors[door] = chest_type

            # Récompense au centre de la salle.
            prize = (x + w//2, y + h//2)
            if prize not in occupied:
                occupied.add(prize)
            self.treasures = getattr(self, 'treasures', set())
            self.treasures.add(prize)
            self.treasure_types[prize] = chest_type
            if chest_type == 'boss':
                self.boss_treasures.add(prize)
            return True
        return False

    def _carve_rooms_and_corridors(self, room_attempts=16, min_size=4, max_size=8):
        rooms=[]
        for _ in range(room_attempts):
            w = random.randint(min_size, max_size)
            h = random.randint(min_size, max_size)
            x = random.randint(1, MAP_W-w-2)
            y = random.randint(1, MAP_H-h-2)
            rect=(x,y,w,h)
            # collision simple
            if any(not (x+w < rx or rx+rw < x or y+h < ry or ry+rh < y) for rx,ry,rw,rh in rooms):
                continue
            for yy in range(y, y+h):
                for xx in range(x, x+w):
                    self.grid[yy][xx]=FLOOR
            rooms.append(rect)
        centers=[(rx+rw//2, ry+rh//2) for rx,ry,rw,rh in rooms]
        if not centers:
            # fallback : grand plus
            for yy in range(2, MAP_H-2): self.grid[yy][MAP_W//2]=FLOOR
            for xx in range(2, MAP_W-2): self.grid[MAP_H//2][xx]=FLOOR
            self._first_room_center=(MAP_W//2, MAP_H//2); return
        centers.sort()
        self._first_room_center=centers[0]
        for i in range(1, len(centers)):
            x1,y1=centers[i-1]; x2,y2=centers[i]
            if i%2==0:
                for x in range(min(x1,x2), max(x1,x2)+1): self.grid[y1][x]=FLOOR
                for y in range(min(y1,y2), max(y1,y2)+1): self.grid[y][x2]=FLOOR
            else:
                for y in range(min(y1,y2), max(y1,y2)+1): self.grid[y][x1]=FLOOR
                for x in range(min(x1,x2), max(x1,x2)+1): self.grid[y2][x]=FLOOR

    def _far_floor_pos(self, ref, min_dist=16, occupied=None):
        occupied = occupied or set()
        best=None; bestd=-1
        for _ in range(8000):
            x,y=random.randrange(1,MAP_W-1), random.randrange(1,MAP_H-1)
            if self.grid[y][x]==FLOOR and (x,y) not in occupied:
                d = 0 if ref is None else abs(x-ref[0])+abs(y-ref[1])
                if d>=min_dist and d>bestd:
                    best=(x,y); bestd=d
        return best or self._random_floor_pos(occupied)

    def _random_floor_pos(self,occupied):
        for _ in range(6000):
            x,y=random.randrange(1,MAP_W-1), random.randrange(1,MAP_H-1)
            if self.grid[y][x]==FLOOR and (x,y) not in occupied: return (x,y)
        return (MAP_W//2, MAP_H//2)

# ========================== RENDU & FOG ==========================
def box_sprite(sprite_lines):
    if not sprite_lines:
        return []
    w = max((visible_len(line) for line in sprite_lines), default=0)
    top = c('┌' + '─'*w + '┐', Ansi.BRIGHT_WHITE)
    bot = c('└' + '─'*w + '┘', Ansi.BRIGHT_WHITE)
    body = [c('│', Ansi.BRIGHT_WHITE) + _pad_ansi_right(line, w) + c('│', Ansi.BRIGHT_WHITE) for line in sprite_lines]
    return [top] + body + [bot]

def _visible_cells(floor: Floor, player_pos, radius=8):
    px,py = player_pos
    vis=set()
    for y in range(max(1,py-radius), min(MAP_H-1, py+radius+1)):
        for x in range(max(1,px-radius), min(MAP_W-1, px+radius+1)):
            if abs(x-px)+abs(y-py) <= radius:
                vis.add((x,y))
    return vis

# Alias compat si du code appelle visible_cells()
visible_cells = _visible_cells

def interaction_hint(floor, player_pos):
    x, y = player_pos
    pos = (x, y)
    if floor.up and pos == floor.up and floor.depth > 0:
        return "Escalier montant détecté — appuyez sur E."
    if pos == floor.down:
        return "Escalier descendant détecté — appuyez sur E."
    if pos in getattr(floor, 'shops', set()):
        return "Marchand présent — appuyez sur E."
    if pos in getattr(floor, 'casinos', set()):
        return "Casino présent — appuyez sur E."
    if pos in getattr(floor, 'altars', set()):
        return "Sanctuaire présent — appuyez sur E."
    if pos in getattr(floor, 'npcs', {}):
        return "PNJ présent — appuyez sur E."
    if pos in getattr(floor, 'sages', set()):
        return "Le Sorcier vous attend — appuyez sur E."
    # Hint contextuel pour les portes verrouillées adjacentes.
    for dx, dy in ((1,0), (-1,0), (0,1), (0,-1)):
        door_pos = (x + dx, y + dy)
        dtype = getattr(floor, 'locked_doors', {}).get(door_pos)
        if dtype == 'boss':
            return "Porte de boss à proximité — nécessite une clé de boss."
        if dtype == 'normal':
            return "Porte verrouillée à proximité — nécessite une clé normale."
    return None

def render_map(floor, player_pos, player):
    global MAP_FRAME_ACTIVE
    # maj visibilité
    base_radius = 8
    bonus = player.all_specials().get('fov_bonus', 0)
    visible = _visible_cells(floor, player_pos, radius=base_radius + bonus)
    floor.visible = visible
    floor.discovered |= visible

    # mémoriser les POIs vus pour rester visibles ensuite
    if floor.up and floor.up in visible:
        floor.seen_stairs.add(floor.up)
    if floor.down in visible:
        floor.seen_stairs.add(floor.down)
    for p in floor.shops:
        if p in visible:
            floor.seen_shops.add(p)
    for p in floor.npcs.keys():
        if p in visible:
            floor.seen_npcs.add(p)
    for p in getattr(floor, 'treasures', set()):
        if p in visible:
            floor.seen_treasures.add(p)
    for p in getattr(floor, 'altars', set()):
        if p in visible:
            floor.seen_altars.add(p)
    for p in getattr(floor, 'casinos', set()):
        if p in visible:
            floor.seen_casinos.add(p)
    for p in getattr(floor, 'sages', set()):
        if p in visible:
            floor.seen_sages.add(p)

    # entête et bordures
    T = floor.theme
    if MAP_FRAME_ACTIVE:
        begin_frame_redraw()
    else:
        clear_screen()
    border_left = c('│', T['border'])
    border_right = c('│', T['border'])
    print(c('┌' + '─' * MAP_W + '┐', T['border']))
    title = f" Donjon — Étage {floor.depth} "
    pad = max(0, MAP_W - len(title))
    print(border_left + c(title + ' ' * pad, T['title']) + border_right)
    print(c('├' + '─' * MAP_W + '┤', T['border']))

    # pré-calcul sprite latéral (évite de recalculer chaque ligne)
    side_lines = []
    side_blank = ""
    top_off = 0
    if SHOW_SIDE_SPRITE:
        spr = player.sprite if getattr(player, 'sprite', None) else SPRITES.get('knight', [])
        spr_colored = colorize_sprite_by_hp(spr, player.hp, player.max_hp)
        summon = _active_summon(player)
        if summon and int(summon.get('hp', 0)) > 0:
            s_spr = summon.get('map_sprite') or summon.get('sprite', [])
            if bool(summon.get('use_hp_tint', True)):
                s_col = colorize_sprite_by_hp(s_spr, int(summon.get('hp', 1)), int(summon.get('max_hp', 1)))
            else:
                s_col = s_spr[:]
            h_side = max(len(spr_colored), len(s_col))
            p_w = max((visible_len(x) for x in spr_colored), default=0)
            s_w = max((visible_len(x) for x in s_col), default=0)
            for i in range(h_side):
                pl = spr_colored[i] if i < len(spr_colored) else (" " * p_w)
                sl = s_col[i] if i < len(s_col) else (" " * s_w)
                side_lines.append(_pad_ansi_right(pl, p_w) + "  " + _pad_ansi_right(sl, s_w))
        else:
            p_w = max((visible_len(x) for x in spr_colored), default=0)
            side_lines = [_pad_ansi_right(line, p_w) for line in spr_colored]
        spr_h = len(side_lines)
        spr_w = max((visible_len(x) for x in side_lines), default=0)
        top_off = max(0, (MAP_H - spr_h) // 2)
        side_blank = '  ' + (' ' * spr_w)

    # cache local pour réduire les lookups en boucle
    discovered = floor.discovered
    grid = floor.grid
    up = floor.up
    down = floor.down
    seen_stairs = floor.seen_stairs
    shops = floor.shops
    seen_shops = floor.seen_shops
    npcs = floor.npcs
    seen_npcs = floor.seen_npcs
    treasures = getattr(floor, 'treasures', set())
    boss_treasures = getattr(floor, 'boss_treasures', set())
    seen_treasures = floor.seen_treasures
    altars = getattr(floor, 'altars', set())
    seen_altars = floor.seen_altars
    casinos = getattr(floor, 'casinos', set())
    seen_casinos = floor.seen_casinos
    sages = getattr(floor, 'sages', set())
    seen_sages = floor.seen_sages
    elites = getattr(floor, 'elites', set())
    locked_doors = getattr(floor, 'locked_doors', {})
    floor_dot = c('·', T['floor'])
    wall_hash = c('#', T['wall'])

    px, py = player_pos
    for y in range(MAP_H):
        row_parts = []
        for x in range(MAP_W):
            pos = (x, y)
            is_vis = pos in visible
            is_disc = pos in discovered
            if not is_disc:
                row_parts.append(' ')
                continue
            if x == px and y == py and is_vis:
                p_icon = getattr(player, 'map_icon', PLAYER_ICON) or PLAYER_ICON
                row_parts.append(c(p_icon, T['player']))
            elif up and pos == up and (is_vis or pos in seen_stairs):
                row_parts.append(c(STAIR_UP, T['up']))
            elif pos == down and (is_vis or pos in seen_stairs):
                row_parts.append(c(STAIR_DOWN, T['down']))
            elif pos in shops and (is_vis or pos in seen_shops):
                row_parts.append(c(SHOP_ICON, T['shop']))
            elif pos in npcs and (is_vis or pos in seen_npcs):
                row_parts.append(c(NPC_ICON, T['npc']))
            elif pos in sages and (is_vis or pos in seen_sages):
                row_parts.append(c(SAGE_ICON, Ansi.BRIGHT_BLUE))
            elif pos in treasures and (is_vis or pos in seen_treasures):
                if pos in boss_treasures:
                    row_parts.append(c(TREASURE_BOSS_ICON, T['elite']))
                else:
                    row_parts.append(c(TREASURE_ICON, T['item']))
            elif pos in altars and (is_vis or pos in seen_altars):
                row_parts.append(c(ALTAR_ICON, T.get('down', Ansi.BRIGHT_MAGENTA)))
            elif pos in casinos and (is_vis or pos in seen_casinos):
                row_parts.append(c(CASINO_ICON, T.get('shop', Ansi.BRIGHT_YELLOW)))
            elif pos in elites:
                row_parts.append(c(ELITE_ICON, T['elite']))
            elif pos in locked_doors and (is_vis or is_disc):
                row_parts.append(c(LOCKED_DOOR_ICON, T['shop']))
            else:
                row_parts.append(floor_dot if grid[y][x] == FLOOR else wall_hash)

        side = ''
        if SHOW_SIDE_SPRITE:
            if top_off <= y < top_off + len(side_lines):
                side = '  ' + side_lines[y - top_off]
            else:
                side = side_blank
        print(border_left + ''.join(row_parts) + border_right + side)
    print(c('└' + '─' * MAP_W + '┘', T['border']))
    print(c(HUD_CONTROLS, Ansi.BRIGHT_BLACK))
    print(player.stats_summary())
    hint = interaction_hint(floor, player_pos)
    if hint:
        print(c(hint, Ansi.BRIGHT_YELLOW))
    if SUPPORTS_ANSI:
        # Nettoie les éventuels résidus d'une frame précédente plus grande.
        sys.stdout.write("\x1b[J")
        sys.stdout.flush()
    MAP_FRAME_ACTIVE = True

# ========================== COFFRE ==========================
def open_treasure_choice(player, depth, chest_type='normal'):
    """
    Coffre : propose 3 objets (jamais de consommables ici pour éviter l'ambiguïté).
    Retourne True si le joueur a pris quelque chose, False sinon.
    N'affiche que des messages, ne touche pas aux trésors de l'étage (la boucle d'explo s'en charge).
    """
    try:
        def chest_item_label(it):
            return item_brief_stats(it)

        # Les coffres de boss proposent plus d'options et un niveau de loot plus élevé.
        pick_count = 4 if chest_type == 'boss' else 3
        depth_bonus = 2 if chest_type == 'boss' else 0

        # Tirages d'objets d'équipement uniquement
        choices = []
        for _ in range(pick_count):
            if chest_type == 'boss':
                it = random_boss_item(depth + depth_bonus, player)
            else:
                it = random_item(depth + depth_bonus, player)
            # si jamais random_item renvoie un consommable (selon ton implémentation), re-roll en item
            if isinstance(it, Consumable):
                # relance jusqu'à obtenir un "Item" (avec garde-fou)
                for __ in range(6):
                    if chest_type == 'boss':
                        it = random_boss_item(depth + depth_bonus, player)
                    else:
                        it = random_item(depth + depth_bonus, player)
                    if not isinstance(it, Consumable):
                        break
            choices.append(it)

        # fallback: si malgré tout on a un consommable, on le convertit en item communs
        if chest_type == 'boss':
            boss_pool = [it for it in ALL_ITEMS if isinstance(it, Item) and it.rarity in ('Rare', 'Épique', 'Légendaire')]
            choices = [it if not isinstance(it, Consumable) else random.choice(boss_pool) for it in choices]
        else:
            choices = [it if not isinstance(it, Consumable) else random.choice(COMMON_ITEMS) for it in choices]
        rarity_xp = {'Commun': 0, 'Rare': 1, 'Épique': 3, 'Légendaire': 6, 'Étrange': 2}
        rarity_score = sum(rarity_xp.get(getattr(it, 'rarity', 'Commun'), 0) for it in choices)

        while True:
            rows = []
            for i, it in enumerate(choices):
                if isinstance(it, Item):
                    line = f"{i+1}) {item_compact_header(it)} | {preview_delta(player,it)}"
                    rows.append(c(line, item_display_color(it)))
                else:
                    rows.append(f"{i+1}) {chest_item_label(it)}")
            rows += ["", f"Choisissez 1-{pick_count}, ou 'q' pour ignorer"]
            clear_screen()
            # Si tu as des thèmes d'étage, passe theme=floor.theme ici via l'appelant
            chest_title = 'Coffre de boss !' if chest_type == 'boss' else 'Trésor !'
            draw_box(chest_title, rows, width=max(140, MAP_W + 24))

            cmd = input('> ').strip().lower()
            if cmd in ('q',''):
                base_xp = 2 + depth + (2 if chest_type == 'boss' else 0)
                rarity_bonus = int(round(rarity_score * (1.15 if chest_type == 'boss' else 1.0)))
                xp_gain = max(1, base_xp + rarity_bonus)
                player.gain_xp(xp_gain)
                draw_box('Trésor', [f"Vous laissez le coffre. Sagesse prudente: +{xp_gain} XP."], width=112)
                time.sleep(0.6)
                return False

            if cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < len(choices):
                    it = choices[idx]
                    # Ajout dans le bon sac
                    if isinstance(it, Consumable):
                        # Par sécurité, mais en principe on n'en a pas ici
                        if _add_consumable(player, it, qty=1) > 0:
                            draw_box('Trésor', [f"Vous prenez: {item_summary(it)} (consommable)"], width=140)
                            pause()
                            return True
                        else:
                            draw_box('Trésor', ["Sac de consommables plein."], width=112)
                            pause()
                            return False
                    else:
                        if len(player.inventory) < player.inventory_limit:
                            player.inventory.append(it)
                            draw_box('Trésor', [f"Vous prenez: {c(chest_item_label(it), item_display_color(it))}"], width=140)
                            pause()
                            return True
                        else:
                            draw_box('Trésor', ["Inventaire plein."], width=112)
                            pause()
                            return False
                # sinon, on reboucle
    except Exception as e:
        # garde-fou: pas de crash jeu si une anomalie survient
        draw_box('Erreur coffre', [repr(e)], width=112)
        pause()
        return False

# ========================== MARCHAND (double panneau) ==========================
def shop_stock_for_depth(depth):
    stock=[random_consumable(depth, source='shop') for _ in range(3)]

    # Emplacements dédiés aux "nouveaux" consommables pour garantir leur présence en boutique.
    common_frags = [fr for fr in GEM_FRAGMENT_POOL if fr.rarity == 'Commun']
    advanced_frags = [fr for fr in GEM_FRAGMENT_POOL if fr.rarity != 'Commun']
    if depth >= 10:
        # À partir de l'étage 10, au moins un fragment avancé + un premium achetable.
        if advanced_frags:
            stock.append(random.choice(advanced_frags))
        if HIGH_TIER_POTIONS:
            stock.append(random.choice(HIGH_TIER_POTIONS))
    else:
        # Avant l'étage 10, on garantit au moins un fragment commun.
        if common_frags:
            stock.append(random.choice(common_frags))

    for _ in range(3+depth//2): stock.append(random_item(depth, DummyPlayer()))
    return stock
    
def open_shop(player, depth):
    BOX_W  = max(156, MAP_W + 48)
    stock = shop_stock_for_depth(depth)
    normal_key_stock = 1
    normal_key_price = BALANCE.get('normal_key_shop_price', 70) + depth * 6
    shop_spell_sid = None
    spell_min_depth = BALANCE.get('spell_shop_min_depth', 8)
    spell_offer_chance = float(BALANCE.get('spell_shop_offer_chance', 0.6))
    if getattr(player, 'klass', '') == 'Mage':
        spell_offer_chance += float(BALANCE.get('mage_spell_shop_offer_bonus', 0.22))
        spell_offer_chance = min(float(BALANCE.get('mage_spell_shop_offer_cap', 0.92)), spell_offer_chance)
    if depth >= spell_min_depth and random.random() < spell_offer_chance:
        offer = _pick_spell_ids(depth, set(player.spell_scrolls), count=1, source='shop')
        if offer:
            shop_spell_sid = offer[0]

    while True:
        # ==== SECTION VENDEUR (achats) ====
        seller_rows = []
        seller_rows.append(f"{c('Marchand', Ansi.BRIGHT_WHITE)} — Étage {depth}")
        seller_rows.append(f"Or dispo : {c(str(player.gold), Ansi.YELLOW)}")
        seller_rows.append('')
        if not stock:
            seller_rows.append(c('(Rupture de stock)', Ansi.BRIGHT_BLACK))
        else:
            for i, it in enumerate(stock, 1):
                price = price_of(it)
                if not isinstance(it, Consumable):
                    label = f"{item_compact_header(it)} | {preview_delta(player, it)}"
                    label = c(label, item_display_color(it))
                    seller_rows.append(f"{i:>2}) {label}  — {price} or")
                else:
                    label = item_brief_stats(it)
                    seller_rows.append(f"{i:>2}) {label}  — {price} or")
        seller_rows.append('')
        seller_rows.append(c("Commandes :", Ansi.BRIGHT_WHITE))
        seller_rows.append(" - <num> : acheter l’item du vendeur")
        seller_rows.append(f" - k : acheter 1 clé normale ({normal_key_price} or) [stock: {normal_key_stock}]")
        if shop_spell_sid:
            sp = _spell_by_id(shop_spell_sid)
            sp_price = _spell_scroll_price(sp, depth)
            seller_rows.append(f" - p : acheter parchemin {sp.name} ({sp_price} or)")
        seller_rows.append(" - v<num> : vendre VOTRE item (voir encadré du bas)")
        seller_rows.append(" - va : vendre TOUS vos objets équipables")
        seller_rows.append(" - s<num> : détails de VOTRE item (voir encadré du bas)")
        seller_rows.append(" - q : quitter la boutique")

        # ==== SECTION JOUEUR (ventes) ====
        player_rows = []
        player_rows.append(c('Vos objets vendables', Ansi.BRIGHT_MAGENTA))
        if not player.inventory:
            player_rows.append(c('(Aucun objet vendable dans l’inventaire)', Ansi.BRIGHT_BLACK))
        else:
            for i, pit in enumerate(player.inventory, 1):
                val = max(5, price_of(pit)//2)
                player_rows.append(f"{i:>2}) {item_summary(pit)}  — vend: {val} or")

        # (Optionnel) Afficher vos consommables en lecture seule
        if getattr(player, 'consumables', None):
            player_rows.append('')
            player_rows.append(c('Vos consommables (non vendables)', Ansi.BRIGHT_CYAN))
            cons = _consumable_stacks(player)
            if not cons:
                player_rows.append(c('(Vide)', Ansi.BRIGHT_BLACK))
            else:
                for st in cons:
                    player_rows.append(f" • {item_summary(st['item'])} x{st['qty']}")

        # ==== Rendu : deux boîtes l’une sous l’autre ====
        clear_screen()
        draw_box(f"Vendeur (Étage {depth})", seller_rows, width=BOX_W)
        print()  # petite marge visuelle
        draw_box("Vos objets (vendre: v<num>/va  •  détails: s<num>)", player_rows, width=BOX_W)

        # ==== Commandes ====
        cmd = input('> ').strip().lower()
        if cmd == 'q':
            break
        if cmd == 'k':
            if normal_key_stock <= 0:
                print("Le marchand n'a plus de clé pour cet étage."); time.sleep(0.8); continue
            if player.gold < normal_key_price:
                print("Or insuffisant."); time.sleep(0.8); continue
            player.gold -= normal_key_price
            normal_key_stock -= 1
            player.normal_keys += 1
            print("Vous achetez une clé normale."); time.sleep(0.8)
            continue
        if cmd == 'p' and shop_spell_sid:
            sp = _spell_by_id(shop_spell_sid)
            sp_price = _spell_scroll_price(sp, depth)
            if player.gold < sp_price:
                print("Or insuffisant pour ce parchemin."); time.sleep(0.8); continue
            player.gold -= sp_price
            player.spell_scrolls.append(shop_spell_sid)
            draw_box("Marchand", [f"Vous achetez le parchemin: {sp.name}."], width=76)
            shop_spell_sid = None
            time.sleep(0.8)
            continue
        # ACHAT — numéro simple (liste du vendeur)
        if cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(stock):
                it = stock[idx]
                price = price_of(it)
                if player.gold < price:
                    print('Or insuffisant.'); time.sleep(0.8); continue

                if isinstance(it, Consumable):
                    # sac dédié aux consommables (non vendables)
                    if _add_consumable(player, it, qty=1) <= 0:
                        print('Sac de consommables plein.'); time.sleep(0.8); continue
                    player.gold -= price
                    stock.pop(idx)
                else:
                    # inventaire normal
                    if len(player.inventory) >= player.inventory_limit:
                        print('Inventaire plein.'); time.sleep(0.8); continue
                    player.gold -= price
                    player.inventory.append(it)
                    stock.pop(idx)
            else:
                print("Numéro invalide."); time.sleep(0.6)
            continue
        # VENTE — v<num> (votre inventaire uniquement)
        if cmd == 'va':
            if not player.inventory:
                print("Aucun objet à vendre."); time.sleep(0.6); continue
            total = sum(max(5, price_of(it)//2) for it in player.inventory)
            sold = len(player.inventory)
            player.inventory.clear()
            player.gold += total
            draw_box("Vente groupée", [f"{sold} objets vendus", f"+{total} or"], width=60)
            time.sleep(0.8)
            continue
        if cmd.startswith('v') and cmd[1:].isdigit():
            idx = int(cmd[1:]) - 1
            if 0 <= idx < len(player.inventory):
                it = player.inventory.pop(idx)
                gain = max(5, price_of(it)//2)
                player.gold += gain
            else:
                print("Numéro invalide pour la vente."); time.sleep(0.6)
            continue
        # DÉTAILS — s<num> (votre inventaire)
        if cmd.startswith('s') and cmd[1:].isdigit():
            idx = int(cmd[1:]) - 1
            if 0 <= idx < len(player.inventory):
                it = player.inventory[idx]
                print(item_summary(it))
                print(preview_delta(player, it))
                pause('Entrée...')
            else:
                print("Numéro invalide pour les détails."); time.sleep(0.6)
            continue
        print('Commande inconnue.'); time.sleep(0.6)

# ========================== TITRE ==========================
def title_menu():
    art = [
        r"  $$$$$$$\   $$$$$$\   $$$$$$\  $$\      $$\ $$$$$$\ $$\   $$\  $$$$$$\  $$\       ",
        r"  $$  __$$\ $$  __$$\ $$  __$$\ $$$\    $$$ |\_$$  _|$$$\  $$ |$$  __$$\ $$ |      ",
        r"  $$ |  $$ |$$ /  $$ |$$ /  \__|$$$$\  $$$$ |  $$ |  $$$$\ $$ |$$ /  $$ |$$ |      ",
        r"  $$$$$$$  |$$ |  $$ |$$ |$$$$\ $$\$$\$$ $$ |  $$ |  $$ $$\$$ |$$$$$$$$ |$$ |      ",
        r"  $$  __$$< $$ |  $$ |$$ |\_$$ |$$ \$$$  $$ |  $$ |  $$ \$$$$ |$$  __$$ |$$ |      ", 
        r"  $$ |  $$ |$$ |  $$ |$$ |  $$ |$$ |\$  /$$ |  $$ |  $$ |\$$$ |$$ |  $$ |$$ |      ",
        r"  $$ |  $$ | $$$$$$  |\$$$$$$  |$$ | \_/ $$ |$$$$$$\ $$ | \$$ |$$ |  $$ |$$$$$$$$\ ",
        r"  \__|  \__| \______/  \______/ \__|     \__|\______|\__|  \__|\__|  \__|\________|",
        r"                               R O G M I N A L                                     ",
        r"                                                                                   ",
    ]
    lines = []
    lines.extend(art)
    lines.append("")
    lines.append("But : descendre les étages, survivre et devenir surpuissant grâce au loot.")
    lines.append("Fonctionnalités : quêtes PNJ, marchand, casino, autels, salles verrouillées, Sorcier & grimoire.")
    lines.append(MENU_CONTROLS)
    lines.append("Astuce : entre un nombre + direction (ex: 5d) ou '.' pour répéter le dernier pas.")
    clear_screen(); draw_box('ROGMINAL — Menu', lines, width=100); pause("Appuyez sur Entrée pour jouer...")

# ========================== ÉVÉNEMENTS ==========================
def maybe_trigger_event(player, depth):
    # Petits événements qui rythment l'exploration
    roll = random.random()
    base = 0.05 + depth*0.005
    if roll < base:
        e = random.random()
        if e < 0.10:
            dmg = max(1, 2 + depth)
            player.take_damage(dmg)
            draw_box('Événement', [f"Un piège ! Vous perdez {dmg} PV."], width=50); pause()
        elif e < 0.30:
            heal = max(3, 5 + depth)
            player.heal(heal)
            draw_box('Événement', [f"Une source claire... Vous récupérez {heal} PV."], width=56); pause()
        elif e < 0.50:
            g = random.randint(3, 8+depth)
            player.gold += g
            draw_box('Événement', [f"Vous trouvez une bourse: +{g} or."], width=50); pause()
        else:
            draw_box('Événement', ["Vous avez un mauvais pressentiment..."], width=60); pause()
            return 'fight'
    return None

def _normalize_fight_result(result):
    if isinstance(result, tuple):
        return result[0], result[1] if len(result) > 1 else None
    return result, None

def _apply_combat_quest_progress(player, status, kill_id):
    updated = []
    for i, q in enumerate(list(player.quests_active)):
        if q.type == 'slay' and status == 'win' and kill_id == q.target:
            q = q._replace(progress=min(q.amount, q.progress + 1))
            updated.append(q)
            player.quests_active[i] = q
        elif q.type == 'survive' and status == 'win':
            q = q._replace(progress=min(q.amount, q.progress + 1))
            updated.append(q)
            player.quests_active[i] = q
    if updated:
        maybe_autocomplete_quests(player)

def ask_restart_after_death():
    draw_box("Game Over", [
        "Votre héros est tombé.",
        "",
        "Relancer une nouvelle partie ? (o/n)"
    ], width=62)
    while True:
        cmd = input("> ").strip().lower()
        if cmd in ("o", "y"):
            return True
        if cmd in ("n", "q", "x", ""):
            return False
        print("Réponse invalide (o/n).")

def choose_player_class():
    rows = [
        "Choisissez votre classe de départ :",
        "1) Chevalier — robuste, équilibré, progression martiale.",
        "2) Mage — grimoire + 1 sort aléatoire dès le début, POUV élevé, ATK/DEF plus faibles.",
        "",
        "Entrée vide = Chevalier.",
    ]
    draw_box("Classe", rows, width=96)
    while True:
        cmd = input("> ").strip().lower()
        if cmd in ("", "1", "c", "chevalier"):
            return "Chevalier"
        if cmd in ("2", "m", "mage"):
            return "Mage"
        print("Choix invalide (1/2).")

# ========================== BOUCLE PRINCIPALE ==========================
def game_loop():
    enable_windows_ansi()
    if '--test' in sys.argv:
        run_tests(); return 'tests_ok'
    title_menu()
    chosen_class = choose_player_class()
    player=Player('Héros', klass=chosen_class)
    if '--debug-all-spells' in sys.argv or '--all-spells' in sys.argv:
        player.spellbook_unlocked = True
        player.spell_scrolls = [sp.sid for sp in SPELLS]
        draw_box("Debug", ["Mode debug activé: tous les sorts ont été ajoutés au grimoire."], width=92)
        time.sleep(0.8)
    floors=[Floor(0)]; cur=0; pos=floors[0].start
    while True:
        f = floors[cur]
        render_map(f, pos, player)
        kind, payload = read_command(player.last_move)
        act = None  # Initialisation pour éviter UnboundLocalError
        if kind == 'action':
            act = payload
        if kind == 'quick_spell':
            slot = int(payload) - 1
            if not player.spellbook_unlocked:
                print("Vous ne possédez pas encore de grimoire."); time.sleep(0.7); continue
            if not (0 <= slot < len(player.spell_scrolls)):
                print(f"Aucun sort assigné au raccourci {payload}."); time.sleep(0.7); continue
            sid = player.spell_scrolls[slot]
            pos, _ = _cast_explore_spell(player, sid, f, pos)
            continue
        if act == 'x':
            print('Au revoir !'); return 'quit'
        if act == 'j':
            journal(player); continue
        if act == 'i':
            open_inventory(player); continue
        if act == 'c':
            open_stats_interface(player); continue
        if act == 'm':
            pos = open_spellbook(player, f.depth, f, pos); continue
        if act == 'e':
            if f.up and pos == f.up and cur > 0:
                target = choose_floor_destination(cur, direction=-1)
                if target is not None:
                    cur = target
                    f = floors[cur]
                    pos = f.down if f.down else f.start
                    player.reset_floor_magic()
                    draw_box('Étage', [f"Vous remontez à l'étage {cur}."], width=44); time.sleep(0.5)
            elif pos == f.down:
                target = choose_floor_destination(cur, direction=1)
                if target is not None:
                    while target >= len(floors):
                        floors.append(Floor(len(floors)))
                    cur = target
                    f = floors[cur]
                    pos = f.up if f.up else f.start
                    player.reset_floor_magic()
                    draw_box('Étage', [f"Vous descendez à l'étage {cur}."], width=44); time.sleep(0.5)
            elif pos in f.shops:
                uses = player.shop_access_count.get(cur, 0)
                if uses == 0:
                    open_shop(player, f.depth)
                    player.shop_access_count[cur] = 1
                elif uses == 1:
                    if player.gold < 10:
                        draw_box('Boutique', ["Accès bonus: 10 or requis.", "Vous n'avez pas assez d'or."], width=72)
                        pause()
                    else:
                        ask = input("Payer 10 or pour réutiliser la boutique une fois ? (o/n) ").strip().lower()
                        if ask in ('o', 'y'):
                            player.gold -= 10
                            open_shop(player, f.depth)
                            player.shop_access_count[cur] = 2
                else:
                    draw_box('Boutique', [f"Boutique de l'étage {cur} épuisée (accès bonus déjà utilisé)."], width=76)
                    pause()
            elif pos in f.npcs:
                npc=f.npcs[pos]; q=npc['quest']
                clear_screen(); draw_box(f"{npc['name']} (Étage {q.giver_floor})", [
                    (f"Tuer {q.amount} {q.target}(s)." if q.type=='slay' else
                     f"Ramène: {q.target}." if q.type=='fetch' else
                     f"Survis à {q.amount} combats."),
                    f"Récompense: {q.reward_xp} XP, {q.reward_gold} or."
                ], width=80)
                existing = next((qq for qq in player.quests_active if qq.qid==q.qid), None)
                if existing is None and all(qq.qid!=q.qid for qq in player.quests_done):
                    if input('Accepter ? (o/n) ').strip().lower() in ('o','y'):
                        player.quests_active.append(q); draw_box('Quête', ['Quête acceptée !'], width=36); pause()
                else:
                    draw_box('Quête', ['Rien à remettre pour le moment.'], width=40); pause()
            elif pos in getattr(f, 'sages', set()):
                if f.depth in player.sage_depths_visited:
                    draw_box("Sorcier", ["Le Sorcier se détourne.", "« Un seul parchemin par étage. »"], width=72)
                    pause()
                else:
                    sage_uses = int(player.sage_access_count.get(cur, 0))
                    if sage_uses == 0:
                        _picked = open_sage_spell_offer(player, f.depth)
                        player.sage_access_count[cur] = 1
                    elif sage_uses == 1:
                        reroll_cost = int(BALANCE.get('sage_reroll_cost_base', 240) + f.depth * BALANCE.get('sage_reroll_cost_depth_mult', 20))
                        if player.gold < reroll_cost:
                            draw_box("Sorcier", [f"Reroll indisponible: {reroll_cost} or requis.", "Vous n'avez pas assez d'or."], width=82)
                            pause()
                        else:
                            ask = input(f"Payer {reroll_cost} or pour un reroll unique du Sorcier ? (o/n) ").strip().lower()
                            if ask in ('o', 'y'):
                                player.gold -= reroll_cost
                                _picked = open_sage_spell_offer(player, f.depth)
                                player.sage_access_count[cur] = 2
                    else:
                        draw_box("Sorcier", ["Le Sorcier reste silencieux.", "Reroll déjà consommé pour cet étage."], width=78)
                        pause()
            elif pos in getattr(f, 'casinos', set()):
                open_casino(player, f.depth)
            elif pos in getattr(f, 'altars', set()):
                used = open_altar(player, f.depth)
                if used:
                    f.altars.discard(pos)
            else:
                print("Rien d'interactif ici."); time.sleep(0.5)
            continue
    
        # Déplacements
        if kind == 'move':
            n, (dx,dy) = payload
            for _ in range(max(1, n)):
                nx, ny = pos[0] + dx, pos[1] + dy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and f.grid[ny][nx] != WALL:
                    pos = (nx, ny)
                    player.last_move = (dx, dy)

                    # Boss sur la case actuelle ? Prioritaire sur les rencontres normales.
                    if pos in f.elites:
                        status, _ = _normalize_fight_result(fight(player, f.depth, boss=True))
                        if status == 'dead':
                            return 'dead'
                        if status == 'win':
                            f.elites.discard(pos)  # boss vaincu
                        if status == 'fled':
                            continue

                    # Événements / Rencontres
                    ev = maybe_trigger_event(player, f.depth)
                    meet = (ev == 'fight') or (pos in f.monsters and random.random() < (0.30 + 0.02*f.depth))
                    if meet:
                        status, kill_id = _normalize_fight_result(fight(player, f.depth))
                        if status == 'dead':
                            return 'dead'

                        if status != 'fled' and pos in f.monsters:
                            f.monsters.discard(pos)

                        _apply_combat_quest_progress(player, status, kill_id)

                    # Ramassage d'ITEMS (indépendant des trésors)
                    if pos in f.items:
                        it = random_item(f.depth, player) if random.random() < 0.65 else random_consumable(f.depth, source='loot')
                        msg = 'Vous trouvez: ' + item_summary(it)
                        if isinstance(it, Consumable):
                            if _add_consumable(player, it, qty=1) > 0:
                                lines = [msg, "Ajouté aux consommables."]
                            else:
                                lines = [msg, "Sac de consommables plein."]
                        else:
                            if len(player.inventory) < player.inventory_limit:
                                player.inventory.append(it)
                                lines = [msg, "Ajouté à l'inventaire."]
                            else:
                                lines = [msg, "Inventaire plein."]

                        # Ces trois lignes doivent être hors des branches conso/objet
                        draw_box('Trouvaille', lines, width=84)
                        maybe_autocomplete_quests(player)
                        f.items.discard(pos)
                        time.sleep(0.4)

                    # Trésors (⚠️ en-dehors du bloc items !)
                    if hasattr(f, 'treasures') and pos in f.treasures:
                        chest_type = getattr(f, 'treasure_types', {}).get(pos, 'normal')
                        open_treasure_choice(player, f.depth, chest_type=chest_type)
                        if chest_type == 'boss':
                            f.boss_treasures.discard(pos)
                        f.treasure_types.pop(pos, None)
                        f.treasures.discard(pos)
                        # (optionnel) progression de quêtes "survive" après un choix :
                        maybe_autocomplete_quests(player)
                else:
                    # Porte verrouillée : ouverture avec la bonne clé.
                    door_type = getattr(f, 'locked_doors', {}).get((nx, ny))
                    if door_type:
                        if door_type == 'boss':
                            if player.boss_keys <= 0:
                                draw_box("Porte verrouillée", ["Il faut une clé de boss pour ouvrir cette porte."], width=88)
                                time.sleep(0.6)
                                break
                            player.boss_keys -= 1
                            door_label = "clé de boss"
                        else:
                            if player.normal_keys <= 0:
                                draw_box("Porte verrouillée", ["Il faut une clé normale pour ouvrir cette porte."], width=88)
                                time.sleep(0.6)
                                break
                            player.normal_keys -= 1
                            door_label = "clé normale"

                        f.locked_doors.pop((nx, ny), None)
                        f.grid[ny][nx] = FLOOR
                        pos = (nx, ny)
                        draw_box("Porte ouverte", [f"Vous utilisez une {door_label}. La salle est accessible."], width=88)
                        time.sleep(0.5)
                        continue
                    break
            continue

    return 'quit'

# ========================== MAIN ==========================
def _bfs_path_exists(grid, start, goal):
    H,W=len(grid),len(grid[0])
    q=deque([start]); seen={start}
    while q:
        x,y=q.popleft()
        if (x,y)==goal: return True
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx,ny=x+dx,y+dy
            if 0<=nx<W and 0<=ny<H and grid[ny][nx]==FLOOR and (nx,ny) not in seen:
                seen.add((nx,ny)); q.append((nx,ny))
    return False

def run_tests():
    print('Tests: génération de carte & utilitaires...')
    f=Floor(1)
    assert f.grid[f.start[1]][f.start[0]]==FLOOR, 'Start doit être sur du sol'
    assert f.down is not None, 'Escalier bas manquant'
    assert _bfs_path_exists(f.grid, f.start, f.down), 'Chemin start→down requis'
    # Fog visible
    vis=_visible_cells(f, f.start, radius=5)
    assert f.start in vis, 'La case joueur doit être visible'
    # Résumé stats
    p=Player('Test'); s=_ansi_re.sub('', p.stats_summary())
    assert 'HP:' in s and 'ATK:' in s and 'DEF:' in s and 'CRIT:' in s, 'stats_summary format invalide'
    # Normalisation du résultat de combat (régression)
    assert _normalize_fight_result(('win', 'slime')) == ('win', 'slime')
    assert _normalize_fight_result('fled') == ('fled', None)
    # Upgrade item
    it = Item('Lame test', 'weapon', 0, 4, 0, 0.02, 'Rare', 'Test.', None)
    it2 = upgrade_item(it)
    assert it2.atk_bonus > it.atk_bonus and it2.crit_bonus >= it.crit_bonus, 'upgrade_item invalide'
    # Caps d'upgrade casino
    it_common = Item('Dague commune', 'weapon', 0, 2, 0, 0.00, 'Commun', 'Test.', None)
    it_rare1 = Item('Dague rare +1', 'weapon', 0, 3, 0, 0.01, 'Rare', 'Test.', None)
    it_epi1 = Item('Dague épique +1', 'weapon', 0, 5, 0, 0.02, 'Épique', 'Test.', None)
    it_cursed = Item('Lame maudite +7', 'weapon', 0, 6, -1, 0.03, 'Étrange', 'Test.', {'cursed': True})
    assert _can_upgrade_item(it_common) is False, 'Commun ne doit pas être améliorable'
    assert _can_upgrade_item(it_rare1) is False, 'Rare +1 ne doit plus être améliorable'
    assert _can_upgrade_item(it_epi1) is True, 'Épique +1 doit encore être améliorable'
    assert _item_upgrade_limit(it_cursed) is None, 'Cursed doit être illimité'
    assert _upgrade_break_chance_for_item(it_cursed, 0.10) > 0.10, 'Cursed doit avoir plus de risque de casse'
    # Régression casino: cap bloqué ne doit pas consommer d'or
    pcap = Player('CapTest')
    pcap.gold = 123
    pcap.equip(it_rare1)
    before_gold = pcap.gold
    res_cap = _casino_upgrade_equipped_item(pcap, 'weapon', upgrade_cost=40, upgrade_break_chance=0.10, use_fragment_guard=False)
    assert res_cap.get('status') == 'blocked_cap', 'Upgrade capé doit être bloqué'
    assert pcap.gold == before_gold, 'Upgrade capé ne doit pas consommer d or'
    # Structures étage étendues
    assert hasattr(f, 'locked_doors') and hasattr(f, 'altars') and hasattr(f, 'casinos'), 'Attributs d étage manquants'
    # Magie: génération sage + sélection de parchemin
    f3 = Floor(BALANCE.get('spell_sage_start_depth', 3))
    assert hasattr(f3, 'sages'), 'Attribut sages manquant'
    picked = _pick_spell_ids(8, set(), count=2, source='sage')
    assert len(picked) >= 1 and all(pid in SPELLS_BY_ID for pid in picked), 'Sélection de parchemins invalide'
    # Nouveaux sorts debuff + invocation défensive
    assert _spell_by_id('withering_hex') is not None and _spell_by_id('sunder_ward') is not None, 'Sorts de debuff manquants'
    assert _summon_spell_cooldown_for_sid('summon_afterimage') == 2, 'Cooldown image rémanante invalide'
    sm_after = _summon_from_spell(p, 'summon_afterimage')
    assert sm_after and sm_after.get('can_attack') is False and abs(float(sm_after.get('guard_ratio', 0.0)) - 0.80) < 1e-9, 'Invocation image rémanante invalide'
    # Horde de squelettes (Appel des morts)
    assert _spell_by_id('call_of_dead') is not None, 'Sort Appel des morts manquant'
    h = _create_horde(p, count=2)
    assert h.get('id') == 'horde' and int(h.get('horde_count', 0)) == 2, 'Création de horde invalide'
    before = int(h.get('horde_count', 0))
    _horde_add_member(p, h, add=1)
    assert int(h.get('horde_count', 0)) == before + 1, 'Ajout à la horde invalide'
    c1 = _horde_conversion_chance(p, 1)
    c6 = _horde_conversion_chance(p, 6)
    assert c1 > c6, 'La conversion doit devenir plus difficile avec une grande horde'
    p.passive_specials['pouv'] = 999
    ccap = _horde_conversion_chance(p, 1)
    assert ccap <= float(BALANCE.get('horde_conversion_cap', 0.60)) + 1e-9, 'Le premier squelette doit respecter le cap de conversion'
    # Consommables stackés
    p2 = Player('StackTest')
    heal = CONSUMABLE_POOL[0]
    assert _add_consumable(p2, heal, qty=1) == 1
    assert _add_consumable(p2, heal, qty=1) == 1
    assert _add_consumable(p2, heal, qty=1) == 1
    assert _consumable_slots_used(p2) == 1 and _consumable_total_count(p2) == 3, 'Stack x3 attendu'
    assert _add_consumable(p2, heal, qty=1) == 1
    assert _consumable_slots_used(p2) == 2 and _consumable_total_count(p2) == 4, 'Nouveau slot attendu au 4e exemplaire'
    _consume_consumable_at(p2, 0)
    assert _consumable_total_count(p2) == 3, 'Consommation d unité invalide'
    # Fragments: stack max 5 + conversion en permanent (valeur d'un fragment, pas x5)
    p3 = Player('FragTest')
    frag = GEM_FRAGMENT_POOL[0]  # frag_atk_pct (0.06, 2)
    for _ in range(5):
        assert _add_consumable(p3, frag, qty=1) == 1
    stacks3 = _consumable_stacks(p3)
    assert all(not (st['item'] == frag and st['qty'] >= 5) for st in stacks3), 'Stack fragment 5 doit se convertir'
    assert abs(float(p3.passive_specials.get('perm_frag_atk_pct', 0.0)) - 0.06) < 1e-9, 'Permanent fragment invalide'
    # Deux types différents ne doivent pas se sommer en "un même fragment"
    frag2 = GEM_FRAGMENT_POOL[1]  # frag_def_pct
    for _ in range(3):
        assert _add_consumable(p3, frag2, qty=1) == 1
    assert abs(float(p3.passive_specials.get('perm_frag_def_pct', 0.0))) < 1e-9, 'Conversion ne doit pas dépendre de la somme inter-types'
    # Classe mage: grimoire de départ + scaling POUV
    pm = Player('MageTest', klass='Mage')
    assert pm.klass == 'Mage' and pm.spellbook_unlocked and len(pm.spell_scrolls) >= 1, 'Mage: démarrage grimoire/sort invalide'
    assert pm.max_hp == 24 and pm.atk == 6 and int(pm.defense) == 2, 'Mage: stats de départ invalides (24/6/2 attendu)'
    assert _spell_cast_limit(pm) >= 3, 'Mage: 3 emplacements de sort attendus dès le départ'
    assert pm.sprite == SPRITES.get('mage', []), 'Mage: sprite invalide'
    assert _spell_pouv(pm) >= 3, 'Mage: POUV de base invalide (>=3 attendu)'
    pm_pouv_before = _spell_pouv(pm)
    pm.gain_xp(BALANCE['level_xp_threshold'])
    assert _spell_pouv(pm) >= pm_pouv_before, 'Mage: POUV doit progresser avec le niveau'
    pm.level = 6
    assert _spell_cast_limit(pm) >= 5, 'Mage: +1 emplacement tous les 2 niveaux attendu au niveau 6'
    # Sorts de buff: doivent scaler avec la POUV
    p_low = Player('BuffLow', klass='Chevalier')
    p_hi = Player('BuffHi', klass='Chevalier')
    p_hi.passive_specials['pouv'] = 30
    low_def = int(_explore_stat_spell_values(p_low, 'warding_mist').get('spell_defense', 0))
    hi_def = int(_explore_stat_spell_values(p_hi, 'warding_mist').get('spell_defense', 0))
    low_focus = _explore_stat_spell_values(p_low, 'focus_sigil')
    hi_focus = _explore_stat_spell_values(p_hi, 'focus_sigil')
    assert hi_def >= low_def, 'Buff DEF magique doit augmenter avec la POUV'
    assert float(hi_focus.get('spell_crit', 0.0)) >= float(low_focus.get('spell_crit', 0.0)), 'Buff CRIT magique doit augmenter avec la POUV'
    assert float(hi_focus.get('spell_power', 0.0)) >= float(low_focus.get('spell_power', 0.0)), 'Buff puissance magique doit augmenter avec la POUV'
    print('OK')

if __name__=='__main__':
    try:
        if '--test' in sys.argv:
            game_loop()
        else:
            while True:
                result = game_loop()
                if result == 'dead':
                    if ask_restart_after_death():
                        continue
                    print("Merci d'avoir joué. À bientôt !")
                break
    except KeyboardInterrupt:
        print('\nInterrompu. Au revoir !'); sys.exit(0)
