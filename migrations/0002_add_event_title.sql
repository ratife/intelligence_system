-- Sépare l'intitulé de l'événement de sa description.
--
-- Jusqu'ici `description` portait deux rôles qui s'excluent : elle servait
-- d'intitulé (titre des cartes du catalogue, en-tête de la fiche, titre des
-- résultats de recherche) tout en étant censée décrire. Plus elle décrivait,
-- moins elle nommait. `title` reprend le rôle d'intitulé ; `description`
-- redevient un texte libre, facultatif.
--
-- REJOUABLE, contrainte non négociable : ce fichier est appliqué par
-- docker-entrypoint-initdb.d sur un volume neuf, par `make migrate` sur une
-- base existante, et par les tests à chaque module d'intégration comme à chaque
-- test e2e. Toute instruction ajoutée ici doit rester sans effet si elle a déjà
-- été appliquée.
--
-- Aucun « : » dans ce fichier : SQLAlchemy y verrait un paramètre lié.

-- En trois temps plutôt qu'en une colonne à DEFAULT : un ADD COLUMN NOT NULL
-- échoue sur une table non vide, mais un DEFAULT permanent graverait dans le
-- schéma la possibilité d'un événement sans intitulé — ce que toute la
-- fonctionnalité vise à interdire. La colonne naît donc nullable, se remplit,
-- puis se ferme.
ALTER TABLE events ADD COLUMN IF NOT EXISTS title TEXT;

-- Reprise des lignes existantes : leur description tenait lieu d'intitulé,
-- c'est donc elle qui devient le titre. Première ligne seulement et longueur
-- bornée, une description pouvant désormais être un paragraphe entier.
-- Le repli sur l'identifiant couvre les descriptions vides — sans lui, le
-- SET NOT NULL ci-dessous échouerait sur ces lignes. La garde WHERE rend
-- l'instruction rejouable et laisse intacts les titres déjà saisis.
UPDATE events
   SET title = COALESCE(
           NULLIF(btrim(left(split_part(description, chr(10), 1), 200)), ''),
           'Événement ' || id
       )
 WHERE title IS NULL;

ALTER TABLE events ALTER COLUMN title SET NOT NULL;

-- La description devient facultative à l'écriture. Elle reste NOT NULL : une
-- absence de description se dit par une chaîne vide, ce qui évite de propager
-- un type nullable jusqu'aux schémas HTTP et aux modèles TypeScript.
ALTER TABLE events ALTER COLUMN description SET DEFAULT '';

COMMENT ON COLUMN events.title IS 'Intitule court affiche. description porte le texte long.';
