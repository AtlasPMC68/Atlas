# Development stage
FROM node:20-alpine AS development

WORKDIR /app

# Évite de copier node_modules depuis ta machine
COPY package*.json ./
RUN npm install

# Copie le reste
COPY . .

# Expose le port Vite (5173)
EXPOSE 5173

# Hot reload pour l’extérieur du conteneur + fixer réseau
CMD ["npm", "run", "dev", "--", "--host", "--port", "5173"]
