# Gestion eau chaude — intégration Home Assistant

Pilotage du chauffe-eau (surplus solaire le jour, heures creuses l'hiver) avec un
panneau dédié dans la barre latérale (« Eau chaude »).

<img width="1631" height="944" alt="image" src="https://github.com/user-attachments/assets/f3095862-a4e1-4264-8316-5a7117d23a7a" />


## Installation
1. Copier le dossier `custom_components/gestion_eau_chaude` dans `/config/custom_components/`.
2. Redémarrer Home Assistant.

5. Si le panneau n'apparaît pas : recharger la page avec Ctrl+F5.

## Entités créées
- `switch` Marche forcée
- `sensor` État, Énergie du jour, Énergie solaire du jour, Énergie heures creuses du jour, Surplus solaire
- `binary_sensor` A chauffé au solaire aujourd'hui, Chauffe heures creuses prévue, Cycle de chauffe terminé

## Réglages
Paramètres → Appareils et services → Gestion eau chaude → Configurer
(entités, seuils, plages horaires, webhook Discord).
