# Detecto frontend: build the React app, serve it with nginx (which also proxies /api to the backend).
# Build from frontend/:  docker build -t detecto-frontend .

# --- 1) Build static files ---------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# The browser calls the API on the same origin; nginx forwards /api to the backend
ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

# --- 2) Serve ---------------------------------------------------------------
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
