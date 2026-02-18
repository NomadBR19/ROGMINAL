# R O G M I N A L                                                                                                                    

Roguelike RPG **100% terminal** en Python, avec exploration par étages, combats au tour par tour, loot, quêtes, autels, casino et magie.

## Aperçu
ROGMINAL est un dungeon crawler ASCII orienté progression:
- exploration procédurale par étages
- combats tactiques avec gestion de statistique, et choix d'orientation du style de jeu
- montée en puissance via équipement, consommables etc
- choix entre risque et récompense

<img width="951" height="482" alt="image" src="https://github.com/user-attachments/assets/ab9c42d0-29ea-42c5-a362-8be8bd3b5f0e" />

## Fonctionnalités
- 2 classes jouables: `Chevalier` et `Mage`
- Système de quêtes PNJ N(chasse / survie)
- Marchand $, Sorcier S, autel *, casino C
- Trésors normaux et coffres de boss T
- Raretés d'objets et effets spéciaux (crit, regen, thorns, dodge, magie...)
- Sorts de combat, d'exploration, de buff, d'invocation...

## Prérequis
- Full compatibilité Windows, Linux ou macOS via l'exe
- Aucune dépendance externe n'est requise.

## Contrôles
- `ZQSD` ou `WASD`: déplacement
- `E`: interagir
- `I`: inventaire
- `C`: stats détaillées
- `J`: journal de quêtes
- `M`: grimoire
- `1..0` ou rangée AZERTY `&é"'(-/è_çà`: raccourcis sorts
- `X`: quitter
- Astuce: `5d` pour avancer de 5 cases, `.` pour répéter le dernier déplacement

## Classes
- `Chevalier`: solide et polyvalent
- `Mage`: débute avec un grimoire et un sort aléatoire, se scale sur sa stats de magie (POUV) mais reste une brindille

## Astuces
- quitter un coffre sans choisir d'item attribuera au joueur une somme d'xp égale à la rareté des items proposés
- utiliser un sort d'invocation à un long cooldown, il faut bien choisir son moment
- les items rares et épics sont souvent préférables aux items légendaires, il ne peuvent toutefois pas être améliorable éternellement
- pensez à utiliser vos sorts et items de buff avant un boss !
- les clés communes sont achetables chez les marchands
- utiliser un fragment de pierre peut empêcher la destruction d'un item magique lors de son amélioration
- le marchand a plus tendance à vendre des parchemins au mage !

## Roadmap (idées)
- équilibrage fin des classes et du scaling
- plus d'événements narratifs
- sauvegarde/chargement de partie
- logs de combat exportables
