FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# NEXT_PUBLIC_* values are inlined at build time: the browser must be able to reach this URL.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app/package.json /app/package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/.next ./.next
COPY --from=build /app/next.config.mjs ./
USER node
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
