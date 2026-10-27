FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install --omit=dev

COPY . .

ARG APP_VERSION=v1.0.0
ENV APP_VERSION=${APP_VERSION}
ENV PORT=80

EXPOSE 80

CMD ["node", "server.js"]
