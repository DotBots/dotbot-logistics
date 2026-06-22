# Implémentation Python vs. Okumura 2022 — Points de comparaison et limites

## Ce que le papier permet de valider

### Algorithme fidèle (Algorithm 1)
L'implémentation `algo/pibt.py` suit Algorithm 1 point par point :
- Décrémentation des priorités à chaque pas, remise à `-inf` quand l'agent est sur son but ✓
- Tri des candidats par distance au but (Manhattan, équivalent à BFS sur grille sans obstacle) ✓
- Filtre anti-swap : exclusion de la position du parent lors de la récursion ✓
- Héritage de priorité : `priorities[occupant] = priorities[agent] + ε` ✓
- Backtracking : si PIBT(k) retourne invalide, l'agent i retire sa réservation et essaie un autre candidat ✓

### Métriques comparables à la Table 2 (Appendix B)
Le papier publie des résultats sur une grille `empty-8×8` (64 cellules) à haute densité :

| \|A\| | Success rate | Runtime/step |
|---|---|---|
| 40 | 0.96 | 0.21 ms |
| 50 | 0.84 | 1.43 ms |
| 60 | 1.00 | 2.16 ms |
| 64 | 1.00 | 3.16 ms |

`bench_pibt.py` produit les mêmes métriques (success rate, makespan, sum-of-costs) sur la même grille 8×8 — une comparaison directe jusqu'à N=32 (limite du générateur de scénario, voir §Limites) est possible. Le runtime Python sera plus lent, mais le **taux de succès et la qualité de solution** (ratio detour) doivent être cohérents avec ces valeurs de référence.

### Grille rectangulaire = condition biconnexe satisfaite
Le papier prouve la *reachability* uniquement si tout couple de nœuds adjacents appartient à un cycle simple (graphe biconnexe). Une grille 4-connexe rectangulaire sans obstacle satisfait cette condition — la garantie théorique s'applique donc dans nos trois configurations (4×4, 5×5, 8×8).

---

## Limites et écarts par rapport au papier

### 1. Pas de PIBT' (rotation-free)
La Section 4.6 introduit PIBT', une variante qui interdit les rotations (3+ agents en permutation circulaire en un seul pas). Sur robots physiques, une rotation est techniquement difficile. L'implémentation actuelle évite uniquement les *swap conflicts* (2 agents), pas les rotations générales. **Impact : sur robots réels, des collisions ou désynchronisations peuvent apparaître dans des configurations circulaires.**

### 2. Générateur de scénario limité à ρ = 0.5
`make_scenario` tire `2N` cellules distinctes (starts + goals disjoints au sens ensembliste). Cela plafonne N à `cells // 2`, soit ρ = 0.5. Le papier teste jusqu'à ρ = 1.0 (Table 2, N=64 sur 64 cellules), ce qui nécessite d'autoriser qu'un start coïncide avec le goal d'un autre agent.

### 3. Pas de PIBT+
Le papier propose PIBT+ (Algorithm 2) — PIBT pré-positionne les agents proches du but, puis un solveur complémentaire (ex. Push&Swap) résout les cas résiduels. Non implémenté. **Impact : sur les scénarios denses où PIBT seul livelocke, le taux d'échec sera plus élevé qu'avec PIBT+.**

### 4. Distance Manhattan ≠ BFS en présence d'obstacles
Le papier utilise une table de distances BFS précalculée (`O(|A|·|E|)` overhead). L'implémentation utilise la distance Manhattan, correcte sur grille ouverte mais **fausse dès qu'un obstacle est introduit** — l'heuristique deviendrait inadmissible et l'ordre de priorité se dégraderait.

### 5. Tie-breaking des priorités
Okumura utilise des `ε_i` distincts par agent, fixés une fois pour tous (`ε_i ∈ [0,1)`, uniques). L'implémentation utilise un seul `EPSILON = 1e-3` pour tous les héritages, sans garantie d'unicité des priorités entre agents de même ancienneté. Cela peut créer des ambiguïtés d'ordonnancement dans des cas limites très denses.

---

## Pistes d'amélioration

| Priorité | Amélioration |
|---|---|
| Haute | Implémenter PIBT' : dans `_pibt()`, filtrer les candidats qui créent une rotation (cycle de 3+ agents réservant leurs positions mutuelles) |
| Haute | Relâcher `make_scenario` pour autoriser départs == arrivées inter-agents → accès à ρ > 0.5 et comparaison avec Table 2 complète |
| Moyenne | Précalculer une table BFS depuis chaque but avant `plan()` → exactitude en présence d'obstacles + accélération |
| Basse | Ajouter un check de biconnectivité avant la simulation → avertir si la garantie de reachability ne s'applique pas (ex. couloir en I) |
| Basse | Implémenter PIBT+ avec un solveur complémentaire minimal pour les instances où PIBT seul dépasse `MAX_STEPS` |
