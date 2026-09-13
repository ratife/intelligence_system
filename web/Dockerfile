# syntax=docker/dockerfile:1

# Image du front : build Angular puis service des fichiers statiques par nginx.
# Le contexte de build est `web/`, pas la racine du dépôt :
#
#   docker build -t facereco-web web/
#
# nginx sert aussi de reverse proxy vers l'API sous /api/. Ce n'est pas une
# commodité : le navigateur émet alors des requêtes de même origine, ce qui
# supprime le CORS du chemin de production (`cors_allowed_origins` ne concerne
# plus que le serveur de dev Angular sur :4200) et évite d'exposer l'API sur un
# port public séparé.

ARG NODE_IMAGE=node:22-bookworm-slim
ARG NGINX_IMAGE=nginx:1.29-alpine


# ---------------------------------------------------------------------------
# Build Angular.
# ---------------------------------------------------------------------------
# Base glibc et non Alpine : package-lock.json ne référence que les binaires
# `@esbuild/linux-*` glibc (aucune entrée `-musl`), et `npm ci` — qui installe
# strictement le verrou — laisserait esbuild sans binaire sur Alpine.
FROM ${NODE_IMAGE} AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY . .

# `api-config.ts` code l'URL de l'API en dur pour le dev (http://localhost:8000).
# Elle est réécrite ici avant compilation plutôt que retouchée dans le bundle
# généré : Angular inline la constante à travers tout le code, et la chaîne
# apparaît aussi dans des messages d'erreur affichés à l'écran — un sed sur le
# JS minifié réécrirait ces messages au passage.
# Par défaut vide : les appels deviennent relatifs (/api/v1/...) et passent par
# le proxy ci-dessous. Fournir une URL absolue si l'API est jointe directement.
ARG API_BASE_URL=""
RUN sed -i "s|^export const API_BASE_URL = .*|export const API_BASE_URL = '${API_BASE_URL}';|" \
        src/app/api-config.ts \
    && grep -q "export const API_BASE_URL = '${API_BASE_URL}';" src/app/api-config.ts \
    && npm run build


# ---------------------------------------------------------------------------
# Service statique.
# ---------------------------------------------------------------------------
FROM ${NGINX_IMAGE} AS runtime

# L'entrypoint officiel de l'image applique envsubst aux *.template au démarrage :
# l'amont de l'API se règle au `docker run`, sans reconstruire le front.
ENV API_UPSTREAM=http://api:8000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Le builder `@angular/build:application` produit dist/<projet>/browser.
COPY --from=builder /app/dist/web/browser /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --spider http://127.0.0.1/index.html || exit 1
