# Utilise Node.js v18 comme image de base
FROM node:18

# Crée le dossier de travail dans le conteneur
WORKDIR /app

# Copie les fichiers de dépendances
COPY package*.json ./

# Installe les dépendances
RUN npm install

# Copie tout le reste du projet
COPY . .

# Expose le port utilisé par Vite (5173 par défaut)
EXPOSE 5173

# Démarre le serveur de développement avec hot reload
CMD ["npm", "run", "dev", "--", "--host"]