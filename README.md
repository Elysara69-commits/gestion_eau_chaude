# Gestion eau chaude — intégration Home Assistant

Pilotage du chauffe-eau (surplus solaire le jour, heures creuses l'hiver) avec un
panneau dédié dans la barre latérale (« Eau chaude »).

<img width="1631" height="944" alt="image" src="https://github.com/user-attachments/assets/f3095862-a4e1-4264-8316-5a7117d23a7a" />


## Installation
1. Copier le dossier `custom_components/gestion_eau_chaude` dans `/config/custom_components/`.
2. Redémarrer Home Assistant.
3. Paramètres -> appareils et services -> bouton ajouter une intégration : gestion eau chaude
4. inscrire les entités correspondantes et les information de puissance de periode heure creuse etc ..
5. Web Hook discord facultatif pour les notification
4. Si le panneau n'apparaît pas : recharger la page avec Ctrl+F5.

## Entités créées
- `switch` Marche forcée
- `sensor` État, Énergie du jour, Énergie solaire du jour, Énergie batterie du jour, Énergie réseau du jour, Énergie heures creuses du jour, Surplus solaire
- `binary_sensor` A chauffé au solaire aujourd'hui, Chauffe heures creuses prévue, Cycle de chauffe terminé

## Origine de l'énergie consommée (solaire / batterie / réseau)
La consommation du jour est répartie selon la **source réelle**, quel que soit le mode (solaire, heures creuses ou marche forcée) :
- **Réseau** : import réseau mesuré ;
- **Solaire** : production consommée directement par la maison (le solaire passe avant la batterie) ;
- **Batterie** : le reste de la consommation de la maison.

Le chauffe-eau est considéré alimenté dans la même proportion que l'ensemble de la maison (répartition au prorata, à chaque cycle de 5 s).
Aucun capteur supplémentaire n'est nécessaire : production, import réseau et consommation maison suffisent.
Le découpage par mode de chauffe reste affiché en rappel sous la carte.

## Réglages
Paramètres → Appareils et services → Gestion eau chaude → Configurer
(entités, seuils, plages horaires, webhook Discord).
