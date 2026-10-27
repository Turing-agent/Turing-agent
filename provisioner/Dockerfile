FROM node:20-alpine

# Install Docker CLI so the provisioner can communicate with the mounted Docker daemon
RUN apk add --no-cache docker-cli

WORKDIR /app

# Copy root context for tinyfish adapter access
COPY provisioner/package*.json ./provisioner/
WORKDIR /app/provisioner
RUN npm install --omit=dev

WORKDIR /app
COPY provisioner/ ./provisioner/
COPY tinyfish/ ./tinyfish/

WORKDIR /app/provisioner
EXPOSE 4000

CMD ["node", "server.js"]
