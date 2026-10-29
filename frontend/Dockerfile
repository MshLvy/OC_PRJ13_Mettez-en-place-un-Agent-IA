# syntax=docker/dockerfile:1
FROM node:22.14.0-bookworm-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=npm_ca \
    if [ -f /run/secrets/npm_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/npm_ca; fi; \
    npm ci --strict-ssl=true --no-audit --no-fund
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build
USER node
EXPOSE 5173
CMD ["./node_modules/.bin/vite", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]
