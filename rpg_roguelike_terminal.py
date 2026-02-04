"""
RPG / Roguelike terminal — Quêtes + Marchand bi‑panneau + Difficulté progressive
- Déplacements **ZQSD/WASD uniquement** (➜ pas de diagonales)
- **PNJ** avec **quêtes** (chasse/collecte/survie) et **journal (J)**
- **Marchand ($)** avec interface **double** : stock du vendeur ⟷ inventaire du joueur (achat/vente en parallèle)
- Carte procédurale **Zelda‑like** (pièces + couloirs), **contour blanc** et **fog of war**
- Combats : **compteur PV** "19/20 PV" (pas de barre)
- Sprites blocs & couleurs conservés

Lancez : python rpg_roguelike_terminal.py
Options : --test (lance des tests rapides)
"""

import os, sys, time, random, re, ctypes, math
from collections import namedtuple, deque

if os.name == 'nt':
    import msvcrt

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
      ('move', (n, (dx,dy)))  ou  ('action', 'e'|'i'|'j'|'c'|'x'|None)
    """
    digits = ''
    while True:
        ch = _getch_blocking().lower()

        # ignorer retours chariot/escapes
        if ch in ('\r', '\n', '\x1b'):
            digits = ''
            continue

        if ch.isdigit():
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

        if ch in ('e','i','j','c','x'):
            return ('action', ch)

        # (optionnel) support flèches sous Windows
        if os.name == 'nt' and ch == '\xe0':
            k = _getch_blocking()
            arrow_map = {'H':'z','P':'s','K':'q','M':'d'}  # ↑ ↓ ← →
            if k in arrow_map:
                n = int(digits) if digits else 1
                return ('move', (n, DIR_KEYS[arrow_map[k]]))
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

def wrap_ansi(s: str, width: int) -> list[str]:
    # wrap doux sans couper les codes ANSI
    out, cur = [], ""
    vlen = 0
    for ch in s:
        cur += ch
        if ch == "\x1b":  # laisser passer la séquence ANSI complète
            # on ne compte pas dans vlen, visible_len gère
            pass
        else:
            vlen = visible_len(cur)
            if vlen >= width:
                out.append(cur)
                cur, vlen = "", 0
    if cur:
        out.append(cur)
    return out

def draw_box(title: str, lines, width: int | None = None):
    if isinstance(lines, (str, bytes)):
        lines = [str(lines)]
    lines = [str(x) for x in lines]

    # largeur mini/maxi + calcul auto selon contenu visible
    content_w = max((visible_len(l) for l in lines), default=0)
    title_text = f" {title} "
    target = max(60, content_w, visible_len(title_text), 100)
    width = max(60, min(200, width or target))  # ← max 200

    top = '┌' + '─'*width + '┐'
    mid = '├' + '─'*width + '┤'
    bot = '└' + '─'*width + '┘'
    print(c(top, Ansi.BRIGHT_WHITE))
    pad = max(0, width - visible_len(title_text))
    print(c('│', Ansi.BRIGHT_WHITE) + c(title_text + ' '*pad, Ansi.BRIGHT_YELLOW) + c('│', Ansi.BRIGHT_WHITE))
    print(c(mid, Ansi.BRIGHT_WHITE))
    for ln in lines:
        for part in wrap_ansi(ln, width):
            pad = max(0, width - visible_len(part))
            print(c('│', Ansi.BRIGHT_WHITE) + part + ' '*pad + c('│', Ansi.BRIGHT_WHITE))
    print(c(bot, Ansi.BRIGHT_WHITE))

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
HUD_CONTROLS = '[ZQSD/WASD] déplacer • E interagir • I inventaire • C stats • J journal • X quitter'
MENU_CONTROLS = "Commandes : ZQSD/WASD se déplacer • E interagir (PNJ/boutique/autel/casino) • I inventaire • C stats • J journal • X quitter"

# ========================== BALANCE ==========================
BALANCE = {
    # COMBAT
    'combat_xp_mult':   0.60,   # % de l'XP habituelle
    'combat_gold_mult': 0.70,   # % de l'or habituel

    # LOOT après combat
    'loot_item_chance': 0.45,   
    'loot_cons_chance': 0.35,   

    # CARTE
    'map_items_per_floor': 3,   # au lieu de 6
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
    'mon_per_level':  {'hp': 0.12, 'atk': 0.10, 'def': 0.06},   # +12% PV, +10% ATK, +6% DEF / niveau
    'mon_per_depth':  {'hp': 0.18, 'atk': 0.15, 'def': 0.08},   # +18% PV, +15% ATK, +8% DEF / étage

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
    'mage': [
        '   ▄█▄   ', '  ▄███▄  ', ' █▓███▓█ ', '   ▓█▓   ', '   ▓█▓   ', '   ▓ ▓   ', '  ▓   ▓  ', '  ▓   ▓  ', '  ▓   ▓  '
    ],
    'slime': [
    "       ,,",
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
    'bat':   [
        "    =/\                 /\=",
        "    /  \'._ (\_/)   _.'/ \\",
        "   / .''._'--(o.o)--'_.''. \\",
        "  /.' _/ |`'=/   \\='`| \\_ `.\\",
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
]
CURSED_ODDITIES = [
    Item('Anneau maudit','accessory',-12,5,0,0.00,'Étrange','Puissant mais dangereux.',{'cursed':True}),
    Item('Amulette du sang','accessory',-5,0,0,0.08,'Étrange','Le sang appelle le sang.',{'vampirism':8}),
    Item('Talisman toxique','accessory',0,0,0,0.00,'Étrange','Chaque coup empoisonne.',{'poison_on_hit':2}),
    Item('Écaille noire','armor',6,0,2,0.0,'Étrange','Difficile à retirer.',{'cursed':True,'dodge':0.03}),
    Item('Bourse maudite','accessory',6,0,-2,-0.02,'Étrange',"L’or coule... mais la chance te fuit.",{'greed':0.30,'unlucky':0.08}),
    Item('Cape de brume','armor',-6,0,2,0.00,'Étrange','Tu vois plus loin à travers la brume.',{'fov_bonus':2,'unlucky':0.05}),
    Item('Épine noire','accessory',-4,0,0,0.00,'Étrange','Blesse ceux qui te frappent. Prix du sang.',{'thorns':5,'bleed_self':2}),
    Item('Sceau du pacte','accessory',0,2,0,0.00,'Étrange','Ta compétence dévore tes PV, mais ravage l’ennemi.',{'special_cost_mult':1.8,'special_dmg_mult':1.4}),
    Item('Masque triste','accessory',-6,3,0,0.00,'Étrange','Force mélancolique.',{'unlucky':0.05}),
    Item('Bottes ferrées','accessory',8,0,3,-0.05,'Étrange','Chaque pas résonne.',{'heavy':True}),
    Item('Lame sanglante','weapon',-4,9,0,0.00,'Étrange','Réclame un tribut.',{'bleed_self':3}),
    Item('Cape souillée','armor',-8,0,3,0.00,'Étrange','Repousse les rares fortunes.',{'unlucky':0.1}),
    Item('Anneau du paria','accessory',-5,2,0,0.06,'Étrange','Acéré mais maudit.',{'unlucky':0.08}),
    Item('Sablier fêlé','accessory',-6,0,0,0.00,'Étrange','Temps contre toi.',{'special_cost_mult':1.4,'special_dmg_mult':1.2}),
    Item('Parchemin de rage','accessory',-8,4,0,0.00,'Étrange','Furie contrôlée.',{'berserk':0.5}),
    Item('Lanterne brumeuse','accessory',-4,0,0,0.00,'Étrange','Vois mais perds la chance.',{'fov_bonus':2,'unlucky':0.06}),
    Item('Gantelet d’épines','armor',-2,0,4,0.00,'Étrange','Blesse qui frappe.',{'thorns':4}),
    Item('Pacte gris','accessory',0,3,0,0.00,'Étrange','Puissance à crédit.',{'special_cost_mult':1.6,'special_dmg_mult':1.3}),
    Item('Talisman de peste','accessory',-6,0,0,0.00,'Étrange','Tout coup infecte.',{'poison_on_hit':3}),
    Item('Amulette de l’avare','accessory',-2,0,0,-0.04,'Étrange','L’or ou la chance ?',{ 'greed':0.4,'unlucky':0.12 }),
]
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

RARITY_WEIGHTS_BASE = {'Commun':72,'Rare':10,'Épique':4,'Légendaire':0.5,'Étrange':8}
RARITY_ORDER = ['Commun','Rare','Épique','Légendaire','Étrange']

# === Couleurs pour les stats ===
STAT_COLORS = {
    'HP':   Ansi.BRIGHT_GREEN,
    'ATK':  Ansi.BRIGHT_RED,
    'DEF':  Ansi.BRIGHT_CYAN,
    'CRIT': Ansi.BRIGHT_MAGENTA,
    'XP':   Ansi.BRIGHT_YELLOW,
    'OR':   Ansi.YELLOW,
}

def color_label(name):
    return c(name, STAT_COLORS.get(name, Ansi.WHITE))

def color_val(name, text):
    return c(str(text), STAT_COLORS.get(name, Ansi.WHITE))

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
        # PV de base réduits pour une difficulté plus élevée
        base = dict(name=name,hp=36,atk=10,defense=5,crit=0.06)
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
        self.blessings_count = 0
        self.curses_count = 0
        self.normal_keys = 1
        self.boss_keys = 0
        self.altar_history = []
        self.passive_specials = {}
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
    def all_specials(self):
        specs={}
        for k,v in self.passive_specials.items():
            specs[k] = specs.get(k, 0) + v if isinstance(v, (int, float)) else v
        for it in self.equipment.values():
            if it and it.special:
                for k,v in it.special.items():
                    if isinstance(v,(int,float)): specs[k]=specs.get(k,0)+v
                    else: specs[k]=True
        return specs
    
    def stats_summary(self):
        parts = [
            f"Niv:{self.level}",
            f"{color_label('HP')}:{hp_gauge_text(self.hp, self.max_hp)}",
            f"{color_label('ATK')}:{color_val('ATK', self.atk + self.temp_buffs['atk'])}",
            f"{color_label('DEF')}:{color_val('DEF', self.defense)}",
            f"{color_label('CRIT')}:{color_val('CRIT', f'{self.crit:.2f}')}",
            f"{color_label('OR')}:{color_val('OR', self.gold)}",
            f"{color_label('XP')}:{color_val('XP', f'{self.xp}/30')}",
            f"Clés N/B:{self.normal_keys}/{self.boss_keys}",
            f"Bénédictions:{self.blessings_count}",
            f"Malédictions:{self.curses_count}",
        ]
        line1 = "  ".join(parts)
        return line1
        
    def gain_xp(self, amount):
        self.xp += amount
        while self.xp >= BALANCE['level_xp_threshold']:
            self.xp -= BALANCE['level_xp_threshold']
            self.level += 1
            self.max_hp += BALANCE['level_hp_gain']
            self.atk    += BALANCE['level_atk_gain']
            self.defense+= BALANCE['level_def_gain']

            # Soin partiel à chaque montée de niveau
            heal = int(self.max_hp * BALANCE.get('level_heal_ratio', 0.50))
            self.hp = min(self.max_hp, self.hp + heal)

            print(c(f"*** Niveau {self.level}! +HP:{BALANCE['level_hp_gain']} "f"+ATK:{BALANCE['level_atk_gain']} +DEF:{BALANCE['level_def_gain']}"f"(+{heal} PV) ***", Ansi.BRIGHT_YELLOW))
            time.sleep(0.6)

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
def clear_screen(): os.system('cls' if os.name=='nt' else 'clear')

def pause(msg='Appuyez sur Entrée pour continuer...'): input(msg)

def rarity_color(r):
    return {
        'Commun': Ansi.BRIGHT_WHITE,
        'Rare': Ansi.BRIGHT_CYAN,
        'Épique': Ansi.BRIGHT_MAGENTA,
        'Légendaire': Ansi.BRIGHT_YELLOW,
        'Étrange': Ansi.BRIGHT_GREEN,
    }.get(r, Ansi.WHITE)

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

    # Multiplicateurs séparés par stat
    mult_hp  = _scaled_fraction(1.0, L, pl['hp'],  capL, softM) * (1.0 + depth * pd['hp'])
    mult_atk = _scaled_fraction(1.0, L, pl['atk'], capL, softM) * (1.0 + depth * pd['atk'])
    mult_def = _scaled_fraction(1.0, L, pl['def'], capL, softM) * (1.0 + depth * pd['def'])

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
    def __init__(self): self.equipment={'weapon':None,'armor':None,'accessory':None}
    def all_specials(self): return {}

def weighted_choice_by_rarity(depth, unlucky):
    # Probabilités de base plus conservatrices pour les objets rares/épiques
    w = RARITY_WEIGHTS_BASE.copy()
    # Progression douce avec profondeur
    w['Rare']        += max(0, depth*1)
    w['Épique']      += max(0, (depth-1)//2)
    w['Légendaire']  += max(0, depth//3)
    w['Étrange']     += max(0, (depth-3)//3)
    # Malchance réduit la probabilité des meilleures raretés
    if unlucky:
        w['Épique'] = max(0, w['Épique']-2)
        w['Légendaire'] = max(0, w['Légendaire']-1)
    total = sum(w.values()); r = random.uniform(0,total); acc = 0
    for k in RARITY_ORDER:
        acc += w[k]
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

    return random.choice(pool)

def random_boss_item(depth, player):
    # Coffres de boss: uniquement Rare -> Légendaire.
    target_rarities = ['Rare', 'Épique', 'Légendaire']
    lucky = max(0, depth)
    weights = {
        'Rare': max(15, 60 - lucky * 2),
        'Épique': 28 + lucky * 2,
        'Légendaire': 8 + lucky,
    }

    roll_pool = []
    for rar in target_rarities:
        roll_pool.extend([rar] * max(1, weights[rar]))
    picked_rarity = random.choice(roll_pool) if roll_pool else 'Rare'

    pool = [it for it in ALL_ITEMS if isinstance(it, Item) and getattr(it, 'rarity', None) == picked_rarity]
    if not pool:
        pool = [it for it in ALL_ITEMS if isinstance(it, Item) and getattr(it, 'rarity', None) in target_rarities]
    if not pool:
        return random_item(depth, player)
    return random.choice(pool)

def random_consumable(): return random.choice(CONSUMABLE_POOL)

def price_of(it):
    if isinstance(it, Consumable):
        return {'Commun':12,'Rare':55,'Épique':90,'Légendaire':180,'Étrange':70}.get(it.rarity,20)
    score = it.hp_bonus*1.2 + it.atk_bonus*4 + it.def_bonus*3 + it.crit_bonus*60
    rar = {'Commun':1.0,'Rare':2.7,'Épique':3.5,'Légendaire':4.5,'Étrange':2.7}.get(it.rarity,1.0)
    spec = 1.0 + (0.3*(len(it.special) if it.special else 0))
    return int(max(8, score*rar*spec))

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

def open_casino(player, depth):
    BOX_W = max(140, MAP_W + 44)
    gamble_cost = BALANCE['casino_gamble_cost_base'] + depth * 2
    upgrade_cost = BALANCE['casino_upgrade_cost_base'] + player.level * 5
    while True:
        equipped = [(slot, it) for slot, it in player.equipment.items() if it]

        main_rows = [
            f"Or disponible : {c(str(player.gold), Ansi.YELLOW)}",
            f"Étage : {depth}  |  Niveau : {player.level}",
            "",
            f"1) Miser {gamble_cost} or pour un item aléatoire",
            f"2) Upgrader un objet équipé ({upgrade_cost} or)",
            "q) Quitter",
        ]

        equip_rows = [c("Objets équipés (upgrade)", Ansi.BRIGHT_MAGENTA)]
        if not equipped:
            equip_rows.append(c("(Aucun objet équipé)", Ansi.BRIGHT_BLACK))
        else:
            for i, (slot, it) in enumerate(equipped, 1):
                equip_rows.append(f"{i:>2}) {slot}: {item_summary(it)}")
        equip_rows.append("")
        equip_rows.append(c("Upgrade disponible à tout niveau.", Ansi.BRIGHT_GREEN))
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
            player.gold -= upgrade_cost
            player._apply_modifiers(old, remove=True)
            new_item = upgrade_item(old)
            player.equipment[slot] = new_item
            player._apply_modifiers(new_item, remove=False)
            draw_box("Upgrade réussi", [f"{old.name} -> {new_item.name}"], width=BOX_W)
            pause()
            continue
        print("Commande inconnue."); time.sleep(0.6)

def open_altar(player, depth):
    rows = [
        "L'autel pulse d'une énergie instable.",
        "1) Bénédiction (bonus sûrs, en % sur vos stats)",
        "2) Malédiction (gros bonus + contre-coup en %)",
        "q) Ignorer",
    ]
    draw_box("Sanctuaire ancien", rows, width=88)
    cmd = input("> ").strip().lower()

    def _gain_int_pct(attr, pct, min_gain=1, floor_value=0):
        base = max(floor_value, int(round(getattr(player, attr))))
        delta = max(min_gain, int(round(base * pct)))
        setattr(player, attr, base + delta)
        return delta, base

    def _lose_int_pct(attr, pct, min_loss=1, floor_value=0):
        base = max(floor_value, int(round(getattr(player, attr))))
        delta = max(min_loss, int(round(base * pct)))
        new_val = max(floor_value, base - delta)
        real_loss = base - new_val
        setattr(player, attr, new_val)
        return real_loss, base

    def _gain_crit_pct(pct, min_gain=0.01):
        base = max(0.0, player.crit)
        delta = max(min_gain, base * pct)
        new_crit = min(0.9, round(base + delta, 3))
        real_gain = round(new_crit - base, 3)
        player.crit = new_crit
        return real_gain, base

    def _lose_crit_pct(pct, min_loss=0.01):
        base = max(0.0, player.crit)
        delta = max(min_loss, base * pct)
        new_crit = max(0.0, round(base - delta, 3))
        real_loss = round(base - new_crit, 3)
        player.crit = new_crit
        return real_loss, base

    if cmd == "1":
        blessing = random.choice([
            "vitalite", "puissance", "rempart", "precision",
            "clairvoyance", "vigueur", "duelliste", "prosperite"
        ])
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
        else:  # prosperite
            gold_gain = int(35 + depth * 12)
            player.gold += gold_gain
            atk_gain, atk_base = _gain_int_pct("atk", 0.06, min_gain=1, floor_value=1)
            msg = f"+{gold_gain} or, +{atk_gain} ATK (+6% de {atk_base})"
        player.blessings_count += 1
        player.altar_history.append(f"Étage {depth} — Bénédiction: {msg}")
        draw_box("Bénédiction", [msg], width=70)
        pause()
        return True
    if cmd == "2":
        # Intensité aléatoire: parfois très punitive, parfois "gérable"
        tier = random.choices(
            population=["moderee", "forte", "brutale"],
            weights=[45, 40, 15],
            k=1,
        )[0]
        mult = {"moderee": 0.85, "forte": 1.00, "brutale": 1.25}[tier]

        pact = random.choice(["verre", "acier", "ombre", "avidite", "sang", "ruine"])
        reward_lines = [f"Pacte {tier}: puissance accrue, prix à payer."]

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
            reward_lines += [f"Bonus: +{def_gain} DEF (+{int(24*mult)}% de {def_base})", f"Malus: -{atk_loss} ATK (-{int(10*mult)}% de {atk_base}), -{crit_loss:.2f} CRIT"]
            altar_log = f"Étage {depth} — Malédiction({tier}) Pacte d'acier: +{def_gain} DEF / -{atk_loss} ATK -{crit_loss:.2f} CRIT"
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
    # stats colorées
    s_hp   = f"{color_label('HP')}+{color_val('HP', it.hp_bonus)}"
    s_atk  = f"{color_label('ATK')}+{color_val('ATK', it.atk_bonus)}"
    s_def  = f"{color_label('DEF')}+{color_val('DEF', it.def_bonus)}"
    s_crit = f"{color_label('CRIT')}+{color_val('CRIT', f'{it.crit_bonus:.2f}')}"
    return (f"{it.name} [{slot_label}] [{it.rarity}] — {it.description} | "
            f"{s_hp} {s_atk} {s_def} {s_crit}" + effect_str(it.special))

def open_stats_interface(player):
    eq_items = [it for it in player.equipment.values() if it]
    eq_hp = sum(it.hp_bonus for it in eq_items)
    eq_atk = sum(it.atk_bonus for it in eq_items)
    eq_def = sum(it.def_bonus for it in eq_items)
    eq_crit = sum(it.crit_bonus for it in eq_items)

    core_rows = [
        c("Stats actuelles", Ansi.BRIGHT_WHITE),
        f"HP: {player.hp}/{_fmt_num(player.max_hp)}",
        f"ATK: {_fmt_num(player.atk)} (+temp {_fmt_num(player.temp_buffs['atk'])})",
        f"DEF: {_fmt_num(player.defense)}",
        f"CRIT: {_fmt_num(player.crit)}",
        f"OR: {_fmt_num(player.gold)}",
        "",
        c("Répartition (total = hors équipement + équipement)", Ansi.BRIGHT_CYAN),
        f"HP max: {_fmt_num(player.max_hp)} = {_fmt_num(player.max_hp - eq_hp)} + {_fmt_num(eq_hp)}",
        f"ATK: {_fmt_num(player.atk)} = {_fmt_num(player.atk - eq_atk)} + {_fmt_num(eq_atk)}",
        f"DEF: {_fmt_num(player.defense)} = {_fmt_num(player.defense - eq_def)} + {_fmt_num(eq_def)}",
        f"CRIT: {_fmt_num(player.crit)} = {_fmt_num(player.crit - eq_crit)} + {_fmt_num(eq_crit)}",
    ]

    equip_rows = [c("Sources équipement", Ansi.BRIGHT_MAGENTA)]
    if not eq_items:
        equip_rows.append(c("(Aucun objet équipé)", Ansi.BRIGHT_BLACK))
    else:
        for slot, it in player.equipment.items():
            if not it:
                continue
            slot_name = {"weapon":"Arme","armor":"Armure","accessory":"Accessoire"}.get(slot, slot)
            bonus = f"HP+{_fmt_num(it.hp_bonus)} ATK+{_fmt_num(it.atk_bonus)} DEF+{_fmt_num(it.def_bonus)} CRIT+{_fmt_num(it.crit_bonus)}"
            line = f"- {slot_name}: {it.name} [{it.rarity}] | {bonus}"
            equip_rows.append(c(line, rarity_color(it.rarity)))
            if it.special:
                equip_rows.append(f"  Effets: {effect_str(it.special).replace(' | Effets: ','')}")

    altar_rows = [c("Historique des autels", Ansi.BRIGHT_YELLOW)]
    if not player.altar_history:
        altar_rows.append(c("(Aucun effet d'autel appliqué)", Ansi.BRIGHT_BLACK))
    else:
        for i, entry in enumerate(player.altar_history, 1):
            altar_rows.append(f"{i:>2}) {entry}")

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
    draw_box("Stats — Autels & Effets", altar_rows + [""] + spec_rows, width=max(150, MAP_W + 50))
    pause()

def preview_delta(player, it):
    if isinstance(it, Consumable): return '(consommable)'
    cur = player.equipment.get(it.slot)
    def tup(obj): return (0,0,0,0) if not obj else (obj.hp_bonus,obj.atk_bonus,obj.def_bonus,obj.crit_bonus)
    dhp, datk, ddef, dcrit = tuple(a-b for a,b in zip(tup(it),tup(cur)))
    return ("Δ "
        f"{color_label('HP')}:{color_delta(dhp)} "
        f"{color_label('ATK')}:{color_delta(datk)} "
        f"{color_label('DEF')}:{color_delta(ddef)} "
        f"{color_label('CRIT')}:{color_delta_crit(dcrit)}")

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
            f"Sac Consommables : {len(getattr(player,'consumables',[]))}/{getattr(player,'consumables_limit',0)}"
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
                    label = c(label, rarity_color(it.rarity))
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
        cons = getattr(player, 'consumables', [])
        if not cons:
            conso_rows.append(c('(Vide)', Ansi.BRIGHT_BLACK))
        else:
            for i, cns in enumerate(cons, 1):
                conso_rows.append(f"{i:>2}) {item_summary(cns)}")

        conso_rows.append('')
        conso_rows.append(c('Actions consommables :', Ansi.BRIGHT_WHITE))
        conso_rows.append(" - uc<num> : utiliser le consommable")
        conso_rows.append(" - dc<num> : jeter le consommable")

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

        # CONSOMMABLES : utiliser / jeter (uc<num>, dc<num>)
        if (cmd.startswith('uc') or cmd.startswith('dc')) and cmd[2:].isdigit():
            idx = int(cmd[2:]) - 1
            cons = getattr(player, 'consumables', [])
            if 0 <= idx < len(cons):
                if cmd.startswith('uc'):
                    cns = cons.pop(idx)  # consommer tout de suite
                    if cns.effect == 'heal':
                        player.heal(cns.power); print(c(f"+{cns.power} PV", Ansi.GREEN))
                    elif cns.effect == 'buff_atk':
                        player.temp_buffs['atk'] += cns.power; player.temp_buffs['turns'] = 3
                        print(c(f"ATK +{cns.power} (3 tours)", Ansi.RED))
                    elif cns.effect == 'flee':
                        # en inventaire (hors combat) : on peut choisir d'ignorer/transformer
                        print("La pierre de rappel n’a d’effet qu’en combat."); time.sleep(0.8)
                    else:
                        print("Consommable utilisé."); time.sleep(0.6)
                else:  # dc<num>
                    cons.pop(idx); print("Consommable jeté."); time.sleep(0.6)
            else:
                print("Index de consommable invalide."); time.sleep(0.6)
            continue

        print('Commande inconnue.'); time.sleep(0.6)


# ========================== COMBAT ==========================
def _combat_panel(player, monster, mname, sprite_m, depth):
    lines=[]
    lines.append(f"{player.name} vs {mname}")
    h = max(len(SPRITES['knight']), len(sprite_m))
    left = SPRITES['knight'] + [' '*len(SPRITES['knight'][0])]*(h-len(SPRITES['knight']))
    right= sprite_m + [' '*len(sprite_m[0])]*(h-len(sprite_m))
    for la, rb in zip(left, right): lines.append(f"{la:20}    {rb}")
    # Affichage des PV
    lines.append(
        f"Vous: {hp_gauge_text(player.hp, player.max_hp)}    "
        f"Ennemi: {hp_gauge_text(monster.hp, monster.max_hp)}")
    lines.append('')
    lines.append('1) Attaquer  2) Défendre  3) Consommable  4) Spéciale  5) Fuir')
    clear_screen(); draw_box(f"Combat — Étage {depth}", lines, width=max(MAP_W, 80))

def compute_damage(attacker, defender, attacker_specs=None):
    attacker_specs = attacker_specs or {}
    base = max(0, attacker.atk - defender.defense)
    variance = random.randint(-2, 3)
    dmg = max(0, base + variance)
    if random.random() < max(0.0, attacker.crit + (0.05 if attacker_specs.get('glass') else 0.0)):
        dmg = max(1, int(dmg * 1.8))
    return dmg

def _try_grant_normal_key(player, depth, bonus_chance=0.0):
    key_chance = BALANCE.get('normal_key_drop_chance', 0.05) + bonus_chance + min(0.03, depth * 0.002)
    if random.random() < key_chance:
        player.normal_keys += 1
        print(c("Vous récupérez une clé normale.", Ansi.BRIGHT_YELLOW))

def fight(player, depth, boss=False):
    if boss:
        pool = [m for m in MONSTER_DEFS if m['id'] in ('diable', 'dragon')]
        mdef = random.choice(pool).copy()
    else:
        heavy_pool = [m for m in MONSTER_DEFS if m['id'] in ('diable', 'dragon')]
        normal_pool = [m for m in MONSTER_DEFS if m['id'] not in ('diable', 'dragon')]
        heavy_chance = BALANCE.get('nonboss_diable_dragon_chance', 0.04)
        # Pas de diable/dragon trop tôt, puis faible chance ensuite.
        if depth < 4:
            heavy_chance = 0.0
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
    p_specs = player.all_specials(); poison_turns=0
    turn_idx = 0

    while player.is_alive() and monster.is_alive():
        turn_idx += 1
        took_damage_this_turn = False
        used_conso = False
        _combat_panel(player, monster, mdef['name'], sprite_m, depth)
        cmd=input('> ').strip()
        defend=False
        if cmd=='1':
            dmg = compute_damage(player, monster, p_specs) + player.temp_buffs['atk']
            # Berserk : si PV <= 50%, bonus multiplicatif
            if player.hp <= player.max_hp // 2:
                bz = p_specs.get('berserk', 0.0)  # ex: 0.5 = +50%
                if bz:
                    dmg = int(dmg * (1.0 + bz))
            monster.take_damage(dmg); print(c(f"Vous infligez {dmg} dégâts.", Ansi.BRIGHT_GREEN))
            if p_specs.get('lifesteal'): player.heal(int(dmg* p_specs['lifesteal']))
            if p_specs.get('poison_on_hit'): poison_turns = max(poison_turns, 2)
        elif cmd=='2': defend=True; print('Vous vous mettez en garde.')
        elif cmd=='3':
            if used_conso:
                print("Vous avez déjà utilisé un consommable ce tour."); time.sleep(0.6)
            else:
                cons = player.consumables
                if not cons:
                    print('Aucun consommable.'); time.sleep(0.6)
                else:
                    # lister une seule fois puis lire l’entrée (ton code lisait "s" dans la boucle)
                    for i, cns in enumerate(cons, 1):
                        print(f"{i}) {item_summary(cns)}")
                    s = input('Numéro à utiliser: ').strip()
                    if s.isdigit():
                        i = int(s) - 1
                        if 0 <= i < len(cons):
                            cns = cons[i]
                            if cns.effect == 'heal':
                                player.heal(cns.power)
                            elif cns.effect == 'buff_atk':
                                player.temp_buffs['atk'] += cns.power
                                player.temp_buffs['turns'] = 3
                            elif cns.effect == 'flee':
                                cons.pop(i)
                                print("Vous utilisez une pierre de rappel : fuite réussie !")
                                return 'fled'
                            cons.pop(i)
                            used_conso = True          # ← verrouille pour ce tour
        elif cmd=='4':
            base_cost = max(1, player.max_hp//8 + 2)  # ou ton coût actuel/plus punitif
            cost_mult = p_specs.get("special_cost_mult", 1.0)
            dmg_mult  = p_specs.get("special_dmg_mult", 1.0)

            cost = int(base_cost * cost_mult)
            if player.hp > cost:
                player.take_damage(cost)
                burst = int(((player.atk + player.temp_buffs['atk']) * 2 + random.randint(0,6)) * dmg_mult)
                monster.take_damage(burst)
                print(c(f"Spéciale ! -{cost} PV, {burst} dégâts.", Ansi.BRIGHT_MAGENTA))
            else:
                print("Pas assez de PV pour la spéciale.")
        elif cmd=='5':
            if random.random()<0.5: print('Vous fuyez.'); time.sleep(0.6); return 'fled'
            else: print('Fuite ratée !')
        else: print('Choix invalide.')
        # DOT poison
        if poison_turns>0 and monster.is_alive():
            dot = max(1, 1 + depth//2)
            monster.take_damage(dot); poison_turns-=1
            print(f"Poison inflige {dot} dégâts.")
        # Riposte
        if monster.is_alive():
            mdmg = compute_damage(monster, player)
            if defend: mdmg //= 2
            if random.random() < p_specs.get('dodge', 0.0):
                print('Vous esquivez !'); mdmg = 0
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
            if random.random() < BALANCE['loot_item_chance']:
                item = random_item(depth, player)
                print('Butin:', item_summary(item))
                if len(player.inventory) < player.inventory_limit:
                    player.inventory.append(item)

            # Drop de consommable (indépendant de l'objet)
            if random.random() < BALANCE['loot_cons_chance']:
                cons = random_consumable()
                print('Butin:', item_summary(cons))
                if len(player.consumables) < player.consumables_limit:
                    player.consumables.append(cons)

            if boss:
                player.boss_keys += 1
                print(c("Clé de coffre de boss obtenue.", Ansi.BRIGHT_MAGENTA))
                _try_grant_normal_key(player, depth, bonus_chance=0.10)
            else:
                _try_grant_normal_key(player, depth)

            pause()
            return ('win', mdef['id'])
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

        # Shops
        self.shops=set()
        if random.random()<0.5 or depth%2==0:
            s=self._random_floor_pos(occ); self.shops.add(s); occ.add(s)
        # Monstres & Items
        self.monsters=set()
        for _ in range(8+depth*2): pos=self._random_floor_pos(occ); occ.add(pos); self.monsters.add(pos)
        self.items = set()
        # Items aléatoires, au moins 1 par étage
        for _ in range(BALANCE['map_items_per_floor']):
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
        self.seen_altars=set(); self.seen_casinos=set()
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
    w = len(sprite_lines[0])
    top = c('┌' + '─'*w + '┐', Ansi.BRIGHT_WHITE)
    bot = c('└' + '─'*w + '┘', Ansi.BRIGHT_WHITE)
    body = [c('│', Ansi.BRIGHT_WHITE) + line + c('│', Ansi.BRIGHT_WHITE) for line in sprite_lines]
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
    # Hint contextuel pour les portes verrouillées adjacentes.
    for dx, dy in ((1,0), (-1,0), (0,1), (0,-1)):
        door_pos = (x + dx, y + dy)
        dtype = getattr(floor, 'locked_doors', {}).get(door_pos)
        if dtype == 'boss':
            return "Porte de boss à proximité — nécessite une clé de boss."
        if dtype == 'normal':
            return "Porte verrouillée à proximité — nécessite une clé normale."
    return None

def render_map(floor, player_pos, player, fatigue):
    # maj visibilité
    base_radius = 8
    bonus = player.all_specials().get('fov_bonus', 0)
    floor.visible = _visible_cells(floor, player_pos, radius=base_radius + bonus)
    floor.discovered |= floor.visible
    # mémoriser les POIs vus pour rester visibles ensuite
    if floor.up and floor.up in floor.visible: floor.seen_stairs.add(floor.up)
    if floor.down in floor.visible: floor.seen_stairs.add(floor.down)
    for p in list(floor.shops):
        if p in floor.visible: floor.seen_shops.add(p)
    for p in list(floor.npcs.keys()):
        if p in floor.visible: floor.seen_npcs.add(p)
    for p in list(getattr(floor,'treasures',set())):
        if p in floor.visible: floor.seen_treasures.add(p)
    for p in list(getattr(floor,'altars',set())):
        if p in floor.visible: floor.seen_altars.add(p)
    for p in list(getattr(floor,'casinos',set())):
        if p in floor.visible: floor.seen_casinos.add(p)
    # entête et bordures
    T = floor.theme
    clear_screen()
    print(c('┌' + '─'*MAP_W + '┐', T['border']))
    title = f" Donjon — Étage {floor.depth} | Fatigue {fatigue} "
    pad = max(0, MAP_W - len(title))
    print(c('│', T['border']) + c(title + ' '*pad, T['title']) + c('│', T['border']))
    print(c('├' + '─'*MAP_W + '┤', T['border']))

    spr = player.sprite if getattr(player, 'sprite', None) else SPRITES.get('knight', [])
    spr_colored = colorize_sprite_by_hp(spr, player.hp, player.max_hp)
    spr_boxed   = box_sprite(spr_colored)
    spr_h = len(spr_boxed)

    treasures = getattr(floor, 'treasures', set())
    boss_treasures = getattr(floor, 'boss_treasures', set())
    altars = getattr(floor, 'altars', set())
    casinos = getattr(floor, 'casinos', set())
    elites = getattr(floor, 'elites', set())
    locked_doors = getattr(floor, 'locked_doors', {})

    for y in range(MAP_H):
        row=''
        for x in range(MAP_W):
            pos=(x,y)
            is_vis = pos in floor.visible
            is_disc = pos in floor.discovered
            ch = floor.grid[y][x]
            if not is_disc:
                row += ' '
                continue
            if (x,y)==player_pos and is_vis:
                row += c(PLAYER_ICON, T['player'])
            elif floor.up and (x,y)==floor.up and (is_vis or (x,y) in floor.seen_stairs):
                row += c(STAIR_UP, T['up'])
            elif (x,y)==floor.down and (is_vis or (x,y) in floor.seen_stairs):
                row += c(STAIR_DOWN, T['down'])
            elif (x,y) in floor.shops and (is_vis or (x,y) in floor.seen_shops):
                row += c(SHOP_ICON, T['shop'])
            elif (x,y) in floor.npcs and (is_vis or (x,y) in floor.seen_npcs):
                row += c(NPC_ICON, T['npc'])
            elif (x,y) in treasures and (is_vis or (x,y) in floor.seen_treasures):
                if (x, y) in boss_treasures:
                    row += c(TREASURE_BOSS_ICON, T['elite'])
                else:
                    row += c(TREASURE_ICON, T['item'])
            elif (x,y) in altars and (is_vis or (x,y) in floor.seen_altars):
                row += c(ALTAR_ICON, T.get('down', Ansi.BRIGHT_MAGENTA))
            elif (x,y) in casinos and (is_vis or (x,y) in floor.seen_casinos):
                row += c(CASINO_ICON, T.get('shop', Ansi.BRIGHT_YELLOW))
            elif (x,y) in elites:  # boss visible
                row += c(ELITE_ICON, T['elite'])
            elif (x,y) in locked_doors and (is_vis or is_disc):
                row += c(LOCKED_DOOR_ICON, T['shop'])
            elif is_vis:
                # on NE MONTRE PAS les monstres volontairement pour garder la surprise
                row += c('·', T['floor']) if ch==FLOOR else c('#', T['wall'])
            else:
                # zone connue mais non visible : terrain seulement, en atténué
                row += c('·', T['floor']) if ch==FLOOR else c('#', T['wall'])
            side = ''
        # Affichage du sprite du joueur à côté de la carte    
        if SHOW_SIDE_SPRITE:
            spr = player.sprite if getattr(player, 'sprite', None) else SPRITES.get('knight', [])
            spr_colored = colorize_sprite_by_hp(spr, player.hp, player.max_hp)
            spr_h = len(spr_colored)
            spr_w = len(spr_colored[0]) if spr_colored else 0
            # centrage vertical du sprite par rapport à la carte
            top_off = max(0, (MAP_H - spr_h) // 2)
            if top_off <= y < top_off + spr_h:
                side = '  ' + spr_colored[y - top_off]  # 2 espaces puis la ligne du sprite
            else:
                side = '  ' + ' ' * spr_w
        print(c('│', T['border']) + row + c('│', T['border'])+ (side if SHOW_SIDE_SPRITE else ''))
    print(c('└' + '─' * MAP_W + '┘', T['border']))
    print(c(HUD_CONTROLS, Ansi.BRIGHT_BLACK))
    print(player.stats_summary())
    hint = interaction_hint(floor, player_pos)
    if hint:
        print(c(hint, Ansi.BRIGHT_YELLOW))

# ========================== COFFRE ==========================
def open_treasure_choice(player, depth, chest_type='normal'):
    """
    Coffre : propose 3 objets (jamais de consommables ici pour éviter l'ambiguïté).
    Retourne True si le joueur a pris quelque chose, False sinon.
    N'affiche que des messages, ne touche pas aux trésors de l'étage (la boucle d'explo s'en charge).
    """
    try:
        def loot_label(it):
            if isinstance(it, Consumable):
                return item_summary(it)
            return c(item_summary(it), rarity_color(it.rarity))

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
            rows = [f"{i+1}) {loot_label(it)}  {preview_delta(player,it)}" for i,it in enumerate(choices)]
            rows += ["", f"Choisissez 1-{pick_count}, ou 'q' pour ignorer"]
            clear_screen()
            # Si tu as des thèmes d'étage, passe theme=floor.theme ici via l'appelant
            chest_title = 'Coffre de boss !' if chest_type == 'boss' else 'Trésor !'
            draw_box(chest_title, rows, width=max(172, MAP_W + 24))

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
                        if len(player.consumables) < player.consumables_limit:
                            player.consumables.append(it)
                            draw_box('Trésor', [f"Vous prenez: {item_summary(it)} (consommable)"], width=164)
                            pause()
                            return True
                        else:
                            draw_box('Trésor', ["Sac de consommables plein."], width=112)
                            pause()
                            return False
                    else:
                        if len(player.inventory) < player.inventory_limit:
                            player.inventory.append(it)
                            draw_box('Trésor', [f"Vous prenez: {loot_label(it)}"], width=164)
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
    stock=[random_consumable() for _ in range(3)]
    for _ in range(3+depth//2): stock.append(random_item(depth, DummyPlayer()))
    return stock
    
def open_shop(player, depth):
    BOX_W  = max(156, MAP_W + 48)
    stock = shop_stock_for_depth(depth)
    normal_key_stock = 1
    normal_key_price = BALANCE.get('normal_key_shop_price', 70) + depth * 6

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
                label = item_summary(it)
                if not isinstance(it, Consumable):
                    label = c(label, rarity_color(it.rarity))
                seller_rows.append(f"{i:>2}) {label}  — {price} or")
        seller_rows.append('')
        seller_rows.append(c("Commandes :", Ansi.BRIGHT_WHITE))
        seller_rows.append(" - <num> : acheter l’item du vendeur")
        seller_rows.append(f" - k : acheter 1 clé normale ({normal_key_price} or) [stock: {normal_key_stock}]")
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
            if not player.consumables:
                player_rows.append(c('(Vide)', Ansi.BRIGHT_BLACK))
            else:
                for cns in player.consumables:
                    player_rows.append(f" • {item_summary(cns)}")

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
                    if len(player.consumables) >= player.consumables_limit:
                        print('Sac de consommables plein.'); time.sleep(0.8); continue
                    player.gold -= price
                    player.consumables.append(it)
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
    lines.append("Fonctionnalités : quêtes PNJ, marchand, casino (tous les 5 étages), autels, salles verrouillées à clés.")
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

# ========================== BOUCLE PRINCIPALE ==========================
def game_loop():
    enable_windows_ansi()
    if '--test' in sys.argv:
        run_tests(); return 'tests_ok'
    title_menu()
    player=Player('Héros')
    floors=[Floor(0)]; cur=0; pos=floors[0].start
    fatigue=0
    while True:
        f = floors[cur]
        render_map(f, pos, player, fatigue)
        kind, payload = read_command(player.last_move)
        act = None  # Initialisation pour éviter UnboundLocalError
        if kind == 'action':
            act = payload
        if act == 'x':
            print('Au revoir !'); return 'quit'
        if act == 'j':
            journal(player); continue
        if act == 'i':
            open_inventory(player); continue
        if act == 'c':
            open_stats_interface(player); continue
        if act == 'e':
            if f.up and pos == f.up and cur > 0:
                target = choose_floor_destination(cur, direction=-1)
                if target is not None:
                    cur = target
                    f = floors[cur]
                    pos = f.down if f.down else f.start
                    fatigue = 0
                    draw_box('Étage', [f"Vous remontez à l'étage {cur}."], width=44); time.sleep(0.5)
            elif pos == f.down:
                target = choose_floor_destination(cur, direction=1)
                if target is not None:
                    while target >= len(floors):
                        floors.append(Floor(len(floors)))
                    cur = target
                    f = floors[cur]
                    pos = f.up if f.up else f.start
                    fatigue = 0
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
                    meet = (ev == 'fight') or (pos in f.monsters and random.random() < (0.30 + 0.02*f.depth + min(0.15, fatigue*0.01)))
                    if meet:
                        status, kill_id = _normalize_fight_result(fight(player, f.depth))
                        if status == 'dead':
                            return 'dead'

                        if status != 'fled' and pos in f.monsters:
                            f.monsters.discard(pos)

                        _apply_combat_quest_progress(player, status, kill_id)
                        fatigue = min(50, fatigue+1)

                    # Ramassage d'ITEMS (indépendant des trésors)
                    if pos in f.items:
                        it = random_item(f.depth, player) if random.random() < 0.65 else random_consumable()
                        msg = 'Vous trouvez: ' + item_summary(it)
                        if isinstance(it, Consumable):
                            if len(player.consumables) < player.consumables_limit:
                                player.consumables.append(it)
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
    # Structures étage étendues
    assert hasattr(f, 'locked_doors') and hasattr(f, 'altars') and hasattr(f, 'casinos'), 'Attributs d étage manquants'
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
