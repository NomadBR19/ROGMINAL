""""""
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

import os, sys, time, random, re, ctypes
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
      ('move', (n, (dx,dy)))  ou  ('action', 'e'|'b'|'i'|'j'|'c'|'x'|None)
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

        if ch in ('e','b','i','j','c','x'):
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

# ========================== PARAMÈTRES ==========================
MAP_W, MAP_H = 48, 20
FLOOR, WALL = '·', '#'
PLAYER_ICON, NPC_ICON, MON_ICON, ITEM_ICON, SHOP_ICON = '@','N','M','*','$'
STAIR_DOWN, STAIR_UP = '>', '<'
TREASURE_ICON = 'T'
ELITE_ICON = 'Ω'

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

    # PNJ par étage (peut être 0)
    'npcs_min': 0,
    'npcs_max': 1,              # anciennement 2 fixes

    # NIVEAUX
    'level_xp_threshold': 40,   # au lieu de 30 (plus lent)
    'level_hp_gain': 3,         # au lieu de 6
    'level_atk_gain': 1,        # au lieu de 2
    'level_def_gain': 0,        # au lieu de 1

    # QUÊTES (récompenses)
    'quest_xp_mult':   0.70,
    'quest_gold_mult': 0.70,

    # Scaling par NIVEAU du joueur et par PROFONDEUR (étage)
    'mon_per_level':  {'hp': 0.12, 'atk': 0.08, 'def': 0.06},   # +12% PV, +8% ATK, +6% DEF / niveau
    'mon_per_depth':  {'hp': 0.18, 'atk': 0.12, 'def': 0.08},   # +18% PV, +12% ATK, +8% DEF / étage

    # Soft cap : au-delà d’un certain niveau, la progression ennemie ralentit
    'mon_softcap_level': 8,
    'mon_softcap_mult':  0.45,  # après le softcap, les % sont multipliés par 0.45

    # Bonus des élites (en plus du scaling de base)
    'elite_bonus': {'hp': 0.40, 'atk': 0.25, 'def': 0.20},

    # Garde-fous de jouabilité (post-ajustement)
    'mon_max_atk_vs_player_hp': 0.45,  # ATK monstre ≤ 45% des PV max du joueur
    'mon_max_def_vs_player_atk': 0.85, # DEF monstre ≤ 85% de l’ATK du joueur (sinon combats trop longs)
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
        "     / \'._   (\_/)   _.'/ \\",
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
        " <>=======()"
        "(/\___   /|\\          ()==========<>_",
        "      \_/ | \\        //|\   ______/ \)",
        "        \_|  \\      // | \_/",
        "          \|\/|\_   //  /\/",
        "           (oo)\ \_//  /",
        "          //_/\_\/ /  |",
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
    Consumable('Pierre de rappel','flee','', 'Rare', 'Permet de fuir un combat.'),
]

RARITY_WEIGHTS_BASE = {'Commun':72,'Rare':18,'Épique':7,'Légendaire':1,'Étrange':1}
RARITY_ORDER = ['Commun','Rare','Épique','Légendaire','Étrange']

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
        for it in self.equipment.values():
            if it and it.special:
                for k,v in it.special.items():
                    if isinstance(v,(int,float)): specs[k]=specs.get(k,0)+v
                    else: specs[k]=True
        return specs
    def stats_summary(self):
        eq = {k: (v.name if v else '—') for k,v in self.equipment.items()}
        return (
            f"Niv:{self.level} HP:{self.hp}/{self.max_hp} ATK:{self.atk+self.temp_buffs['atk']} "
            f"DEF:{self.defense} CRIT:{self.crit:.2f} Or:{self.gold}\n"
            f"Equip: W:{eq['weapon']} A:{eq['armor']} Acc:{eq['accessory']}"
        )
    def gain_xp(self, amount):
        self.xp += amount
        while self.xp >= BALANCE['level_xp_threshold']:
            self.xp -= BALANCE['level_xp_threshold']
            self.level += 1
            self.max_hp += BALANCE['level_hp_gain']
            self.atk    += BALANCE['level_atk_gain']
            self.defense+= BALANCE['level_def_gain']
            self.hp = self.max_hp
            print(c(f"*** Niveau {self.level}! Stats +HP:{BALANCE['level_hp_gain']} +ATK:{BALANCE['level_atk_gain']} +DEF:{BALANCE['level_def_gain']} ***", Ansi.BRIGHT_YELLOW))
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

def random_consumable(): return random.choice(CONSUMABLE_POOL)

def price_of(it):
    if isinstance(it, Consumable):
        return {'Commun':12,'Rare':55,'Épique':90,'Légendaire':180,'Étrange':70}.get(it.rarity,20)
    score = it.hp_bonus*1.2 + it.atk_bonus*4 + it.def_bonus*3 + it.crit_bonus*60
    rar = {'Commun':1.0,'Rare':2.7,'Épique':3.5,'Légendaire':4.5,'Étrange':2.7}.get(it.rarity,1.0)
    spec = 1.0 + (0.3*(len(it.special) if it.special else 0))
    return int(max(8, score*rar*spec))

# ========================== INVENTAIRE ==========================

def effect_str(special):
    if not special: return ''
    parts=[]
    for k,v in special.items(): parts.append(f"{k}={v}" if not isinstance(v,bool) else k)
    return ' | Effets: ' + ', '.join(parts)

def item_summary(it):
    if it is None: return '—'
    if isinstance(it, Consumable): return f"{it.name} [{it.rarity}] — {it.description}"
    return (f"{it.name} [{it.rarity}] — {it.description} | "
            f"HP+{it.hp_bonus} ATK+{it.atk_bonus} DEF+{it.def_bonus} CRIT+{it.crit_bonus:.2f}" + effect_str(it.special))

def preview_delta(player, it):
    if isinstance(it, Consumable): return '(consommable)'
    cur = player.equipment.get(it.slot)
    def tup(obj): return (0,0,0,0) if not obj else (obj.hp_bonus,obj.atk_bonus,obj.def_bonus,obj.crit_bonus)
    ch = tuple(a-b for a,b in zip(tup(it),tup(cur)))
    return f"Δ HP:{ch[0]:+} ATK:{ch[1]:+} DEF:{ch[2]:+} CRIT:{ch[3]:+.2f}"

def open_inventory(player):
    while True:
        rows = []
        # --- SECTION OBJETS (équipables & divers) ---
        rows.append(c("Objets", Ansi.BRIGHT_WHITE))
        if not player.inventory:
            rows.append("  (aucun)")
        else:
            for i, it in enumerate(player.inventory, 1):
                label = item_summary(it)
                if not isinstance(it, Consumable):
                    label = c(label, rarity_color(it.rarity))
                rows.append(f"{i:>2}) {label}  {preview_delta(player, it)}")

        # --- SECTION CONSOMMABLES (sac dédié) ---
        rows.append("")
        rows.append(c("Consommables (non vendables)", Ansi.BRIGHT_WHITE))
        if not player.consumables:
            rows.append("  (aucun)")
        else:
            for i, cns in enumerate(player.consumables, 1):
                rows.append(f"c{i:>2}) {item_summary(cns)}")

        # --- Équipement actuel ---
        rows.append("")
        rows.append("Équipement:")
        for slot, it in player.equipment.items():
            rows.append(f"{slot}: {item_summary(it) if it else '—'}")

        # --- Aide commandes ---
        rows.append("")
        rows.append("Actions : e<num> équiper  | d<num> jeter  | uc<num> utiliser conso  | dc<num> jeter conso  | q retour")
        clear_screen(); draw_box("Inventaire", rows, width=max(MAP_W, 110))
        cmd = input("> ").strip().lower()

        if cmd == 'q':
            break

        # Équiper / jeter OBJETS
        if len(cmd) >= 2 and cmd[1:].isdigit() and cmd[0] in ('e','d'):
            idx = int(cmd[1:]) - 1
            if 0 <= idx < len(player.inventory):
                it = player.inventory[idx]
                if cmd[0] == 'e' and not isinstance(it, Consumable):
                    player.equip(it); player.inventory.pop(idx)
                elif cmd[0] == 'd':
                    player.inventory.pop(idx)
            continue

        # Utiliser / jeter CONSOMMABLES (préfixe 'uc' / 'dc')
        if (cmd.startswith('uc') or cmd.startswith('dc')) and cmd[2:].isdigit():
            idx = int(cmd[2:]) - 1
            if 0 <= idx < len(player.consumables):
                cns = player.consumables[idx]
                if cmd.startswith('uc'):
                    if cns.effect == 'heal':
                        player.heal(cns.power)
                    elif cns.effect == 'buff_atk':
                        player.temp_buffs['atk'] += cns.power; player.temp_buffs['turns'] = 3
                    elif cns.effect == 'flee':
                        print("Vous utilisez un fumigène pour fuir le combat.")
                        return 'fled'
                    player.consumables.pop(idx)
                else:  # 'dc'
                    player.consumables.pop(idx)
            continue

# ========================== COMBAT ==========================

def _combat_panel(player, monster, mname, sprite_m, depth):
    lines=[]
    lines.append(f"{player.name} vs {mname}")
    h = max(len(SPRITES['knight']), len(sprite_m))
    left = SPRITES['knight'] + [' '*len(SPRITES['knight'][0])]*(h-len(SPRITES['knight']))
    right= sprite_m + [' '*len(sprite_m[0])]*(h-len(sprite_m))
    for la, rb in zip(left, right): lines.append(f"{la:20}    {rb}")
    lines.append(f"Vous: {player.hp}/{player.max_hp} PV    Ennemi: {monster.hp}/{monster.max_hp} PV")
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

def fight(player, depth):
    mdef = random.choice(MONSTER_DEFS).copy()
    mdef = scale_monster(mdef, player, depth, elite=False)
    monster = Character(mdef['name'], mdef['hp'], mdef['atk'], mdef['def'], mdef['crit'])
    monster.max_hp = mdef['hp']
    sprite_m = mdef['sprite']
    p_specs = player.all_specials(); poison_turns=0
    
    while player.is_alive() and monster.is_alive():
        used_conso = False
        _combat_panel(player, monster, mdef['name'], sprite_m, depth)
        cmd=input('> ').strip()
        defend=False
        if cmd=='1':
            dmg = compute_damage(player, monster, p_specs) + player.temp_buffs['atk']
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
            if defend: mdmg//=2
            if random.random() < p_specs.get('dodge',0): print('Vous esquivez !'); mdmg=0
            player.take_damage(mdmg); print(c(f"{mdef['name']} inflige {mdmg} dégâts.", Ansi.BRIGHT_RED))
            if p_specs.get('thorns',0)>0 and mdmg>0:
                thorn = p_specs['thorns']; monster.take_damage(thorn); print(f"Épines renvoient {thorn} dégâts.")
        if player.temp_buffs['turns']>0:
            player.temp_buffs['turns']-=1
            if player.temp_buffs['turns']==0: player.temp_buffs['atk']=0
        time.sleep(0.6)

        if monster.hp <= 0:
            print(c('Victoire !', Ansi.BRIGHT_GREEN))
            xp_gain   = int((mdef['xp']   + monster.max_hp//4) * BALANCE['combat_xp_mult'])
            gold_gain = int((mdef['gold'] + random.randint(0, max(1, monster.max_hp//6))) * BALANCE['combat_gold_mult'])
            player.gain_xp(xp_gain)
            player.gold += gold_gain
            print(f"+{xp_gain} XP, +{gold_gain} or")

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
        self.items=set()
        self.items = set()
        # Items aléatoires, au moins 1 par étage
        for _ in range(BALANCE['map_items_per_floor']):
            pos = self._random_floor_pos(occ); occ.add(pos); self.items.add(pos)

        # Trésors (au moins 1 par étage)
        self.treasures=set()
        tpos = self._far_floor_pos(self.start, min_dist=10, occupied=occ)
        if tpos: self.treasures.add(tpos); occ.add(tpos)
        if random.random()<0.25:
            t2 = self._random_floor_pos(occ); self.treasures.add(t2); occ.add(t2)
        # Fog & POIs vus
        self.discovered=set(); self.visible=set()
        self.seen_shops=set(); self.seen_npcs=set(); self.seen_stairs=set(); self.seen_treasures=set()
        self.elites = set()
        self.seen_elites = set()  # pas indispensable si on les affiche tout le temps
        if random.random() < max(0.10, 0.05 + 0.02*self.depth):  # rare, un peu plus profond = un peu plus fréquent
            epos = self._far_floor_pos(self.start, min_dist=14, occupied=occ)
            if epos:
                self.elites.add(epos)
                occ.add(epos)

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

def render_map(floor, player_pos, player, fatigue):
    # maj visibilité
    extra_fov = player.all_specials().get("fov_bonus", 0)
    floor.visible = _visible_cells(floor, player_pos, radius=8 + int(extra_fov))
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
    clear_screen()
    print(c('┌' + '─'*MAP_W + '┐', Ansi.BRIGHT_WHITE))
    title = f" Donjon — Étage {floor.depth} | Fatigue {fatigue} "
    pad = max(0, MAP_W - len(title))
    print(c('│', Ansi.BRIGHT_WHITE) + c(title + ' '*pad, Ansi.BRIGHT_YELLOW) + c('│', Ansi.BRIGHT_WHITE))
    print(c('├' + '─'*MAP_W + '┤', Ansi.BRIGHT_WHITE))
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
                row += c(PLAYER_ICON, Ansi.BRIGHT_GREEN)
            elif floor.up and (x,y)==floor.up and (is_vis or (x,y) in floor.seen_stairs):
                row += c(STAIR_UP, Ansi.BRIGHT_CYAN)
            elif (x,y)==floor.down and (is_vis or (x,y) in floor.seen_stairs):
                row += c(STAIR_DOWN, Ansi.BRIGHT_MAGENTA)
            elif (x,y) in floor.shops and (is_vis or (x,y) in floor.seen_shops):
                row += c(SHOP_ICON, Ansi.BRIGHT_YELLOW)
            elif (x,y) in floor.npcs and (is_vis or (x,y) in floor.seen_npcs):
                row += c(NPC_ICON, Ansi.BRIGHT_CYAN)
            elif (x,y) in getattr(floor,'treasures',set()) and (is_vis or (x,y) in floor.seen_treasures):
                row += c(TREASURE_ICON, Ansi.BRIGHT_YELLOW)
            elif (x,y) in getattr(floor,'elites',set()):  # toujours visible
                row += c(ELITE_ICON, Ansi.BRIGHT_RED)
            elif is_vis:
                # on NE MONTRE PAS les monstres volontairement pour garder la surprise
                row += c('·', Ansi.DIM) if ch==FLOOR else c('#', Ansi.BRIGHT_BLACK)
            else:
                # zone connue mais non visible : terrain seulement, en atténué
                row += (c('·', Ansi.DIM) if ch==FLOOR else c('#', Ansi.BRIGHT_BLACK))
        print(c('│', Ansi.BRIGHT_WHITE) + row + c('│', Ansi.BRIGHT_WHITE))
    print(c('└' + '─' * MAP_W + '┘', Ansi.BRIGHT_WHITE))
    print(c('[ZQSD/WASD] déplacer • E parler/valider • B boutique (sur $) • J journal • I inventaire • X quitter', Ansi.BRIGHT_BLACK))
    print(player.stats_summary())

# ========================== MARCHAND (double panneau) ==========================

def shop_stock_for_depth(depth):
    stock=[random_consumable() for _ in range(3)]
    for _ in range(3+depth//2): stock.append(random_item(depth, DummyPlayer()))
    return stock

def open_treasure_choice(player, depth):
    # Choisir 1 objet parmi 3
    choices = [random_item(depth, player) for _ in range(3)]
    while True:
        rows = [f"{i+1}) {item_summary(it)}  {preview_delta(player,it)}" for i,it in enumerate(choices)]
        rows += ["", "Choisissez 1-3 ou q pour ignorer"]
        clear_screen(); draw_box('Trésor !', rows, width=max(84, MAP_W))
        cmd = input('> ').strip().lower()
        if cmd in ('q',''): return False
        if cmd in ('1','2','3'):
            idx=int(cmd)-1
            if 0<=idx<len(choices):
                it=choices[idx]
                if isinstance(it, Consumable):
                    if len(player.consumables) < player.consumables_limit:
                        player.consumables.append(it)
                    else:
                        draw_box('Trésor', ["Sac de consommables plein."], width=84); pause(); return True
                else:
                    if len(player.inventory) < player.inventory_limit:
                        player.inventory.append(it)
                    else:
                        draw_box('Trésor', ["Inventaire plein."], width=84); pause(); return True
                return True


def open_shop(player, depth):

    LEFT_W = 92        # largeur colonne vendeur
    BOX_W  = 160       # largeur totale de l'encadré

    stock = shop_stock_for_depth(depth)
    while True:
        rows=[]
        left_title = c('Vendeur', Ansi.BRIGHT_WHITE)
        right_title= c(f'Vous (or: {player.gold})', Ansi.BRIGHT_WHITE)
        rows.append(f"{left_title:<{LEFT_W}}{right_title}")
        rows.append('-'*BOX_W)
        max_rows = max(len(stock), len(player.inventory)) or 1
        for i in range(max_rows):
            l = ''
            if i < len(stock):
                it = stock[i]; price = price_of(it)
                label = item_summary(it)
                if not isinstance(it, Consumable): label = c(label, rarity_color(it.rarity))
                l = f"{i+1:>2}) {label}  — {price} or"
            r = ''
            if i < len(player.inventory):
                pit = player.inventory[i]; val = max(5, price_of(pit)//2)
                r = f"{i+1:>2}) {item_summary(pit)}  — vend: {val} or"
            rows.append(f"{l:<{LEFT_W}} | {r}")
        rows.append('')
        rows.append('Commandes: numéro = acheter à gauche • v<num> = vendre votre item • s<num> = détails votre item • q = quitter')
        clear_screen(); draw_box(f"Marchand (Étage {depth})", rows, width=BOX_W)
        cmd=input('> ').strip().lower()
        if cmd=='q': break
        if cmd.isdigit():
            idx=int(cmd)-1
            if 0 <= idx < len(stock):
                    it = stock[idx]
                    price = price_of(it)
                    if player.gold < price:
                        print('Or insuffisant.'); time.sleep(0.8); continue

                    if isinstance(it, Consumable):
                        # sac dédié aux consommables
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
        elif cmd.startswith('v') and cmd[1:].isdigit():
            idx=int(cmd[1:])-1
            if 0<=idx<len(player.inventory):
                it=player.inventory.pop(idx); gain=max(5, price_of(it)//2); player.gold+=gain
        elif cmd.startswith('s') and cmd[1:].isdigit():
            idx=int(cmd[1:])-1
            if 0<=idx<len(player.inventory):
                it=player.inventory[idx]; print(item_summary(it)); print(preview_delta(player,it)); pause('Entrée...')

# ========================== ENTRÉE UTILISATEUR ==========================

def parse_move(cmd, last_dir):
    if cmd=='.' and last_dir!=(0,0): return 1, last_dir
    num=''; i=0
    while i<len(cmd) and cmd[i].isdigit(): num+=cmd[i]; i+=1
    n=int(num) if num else 1
    key = cmd[i:i+1]
    if key in DIR_KEYS: return n, DIR_KEYS[key]
    return None, (0,0)

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
    lines.append("Fonctionnalités : quêtes PNJ, marchand, objets rares/étranges, difficulté progressive.")
    lines.append("Commandes : ZQSD/WASD se déplacer • E parler • B boutique • I inventaire • J journal • X quitter")
    lines.append("Astuce : entre un nombre + direction (ex: 5d) ou '.' pour répéter le dernier pas.")
    clear_screen(); draw_box('ROGMINAL — Menu', lines, width=100); pause("Appuyez sur Entrée pour jouer...")

# ========================== ÉVÉNEMENTS ==========================

def maybe_trigger_event(player, depth):
    # Petits événements qui rythment l'exploration
    roll = random.random()
    base = 0.05 + depth*0.005
    if roll < base:
        e = random.random()
        if e < 0.30:
            dmg = max(1, 2 + depth)
            player.take_damage(dmg)
            draw_box('Événement', [f"Un piège ! Vous perdez {dmg} PV."], width=50); pause()
        elif e < 0.55:
            heal = max(3, 5 + depth)
            player.heal(heal)
            draw_box('Événement', [f"Une source claire... Vous récupérez {heal} PV."], width=56); pause()
        elif e < 0.80:
            g = random.randint(3, 8+depth)
            player.gold += g
            draw_box('Événement', [f"Vous trouvez une bourse: +{g} or."], width=50); pause()
        else:
            draw_box('Événement', ["Vous avez un mauvais pressentiment..."], width=60); pause()
            return 'fight'
    return None

# ========================== BOUCLE PRINCIPALE ==========================

def game_loop():
    enable_windows_ansi()
    if '--test' in sys.argv:
        run_tests(); return
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
            print('Au revoir !'); break
        if act == 'j':
            journal(player); continue
        if act == 'i':
            open_inventory(player); continue
        if act == 'c':
            clear_screen(); print(player.stats_summary()); pause(); continue
        if act == 'e':
            if pos in f.npcs:
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
            else:
                print('Personne à qui parler ici.'); time.sleep(0.5)
            continue
        if act == 'b' and pos in f.shops:
            open_shop(player, f.depth); continue
    
        # Déplacements
        if kind == 'move':
            n, (dx,dy) = payload
            for _ in range(max(1, n)):
                nx, ny = pos[0] + dx, pos[1] + dy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and f.grid[ny][nx] != WALL:
                    pos = (nx, ny)
                    player.last_move = (dx, dy)

                    # Escaliers
                    if f.up and pos==f.up and cur>0:
                        cur-=1; f=floors[cur]; pos=f.down; fatigue=0
                        draw_box('Étage', [f"Vous montez à l'étage {cur}."], width=40); time.sleep(0.5); break
                    if pos==f.down:
                        cur+=1
                        if cur>=len(floors): floors.append(Floor(cur))
                        f=floors[cur]; pos=f.up if f.up else f.start; fatigue=0
                        draw_box('Étage', [f"Vous descendez à l'étage {cur}."], width=44); time.sleep(0.5); break
                    
                    # Événements / Rencontres
                    ev = maybe_trigger_event(player, f.depth)
                    meet = (ev == 'fight') or (pos in f.monsters and random.random() < (0.30 + 0.02*f.depth + min(0.15, fatigue*0.01)))
                    if meet:
                        res = fight(player, f.depth)
                        if res == 'dead':
                            print('Game over.'); return
                        if res != 'fled' and pos in f.monsters:
                            f.monsters.discard(pos)

                        # progression quêtes (slay/survive)
                        status, kill_id = (res if isinstance(res, tuple) else (res, None))

                        if status == 'dead':
                            print('Game over.'); return

                        if status != 'fled' and pos in f.monsters:
                            f.monsters.discard(pos)

                        # progression quêtes (slay/survive)
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
                        took = open_treasure_choice(player, f.depth)
                        f.treasures.discard(pos)
                        # (optionnel) progression de quêtes "survive" après un choix :
                        maybe_autocomplete_quests(player)
                    if pos in f.shops: print('Un marchand est là. Appuyez sur B pour commercer.')
                    # Élite sur la case actuelle ?
                    if pos in f.elites:
                        res = fight(player, f.depth)
                        if res == 'dead':
                            return  # fin de partie
                        if res == 'win':
                            f.elites.discard(pos)  # élite vaincue
                        # si le joueur a fui, on laisse l'élite
                else:
                    break
            continue

# ========================== TESTS ==========================

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
    p=Player('Test'); s=p.stats_summary()
    assert 'HP:' in s and 'ATK:' in s and 'DEF:' in s and 'CRIT:' in s, 'stats_summary format invalide'
    print('OK ✅')

if __name__=='__main__':
    try:
        game_loop()
    except KeyboardInterrupt:
        print('\nInterrompu. Au revoir !'); sys.exit(0)


