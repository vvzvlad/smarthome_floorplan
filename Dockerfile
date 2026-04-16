# Stage 1: build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Python server
FROM python:3.11-slim
WORKDIR /app

COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/main.py .
COPY server/src/ ./src/

# Copy built frontend into static/ so FastAPI can serve it
COPY --from=frontend-build /app/dist ./static/

VOLUME ["/data"]

CMD ["python", "main.py"]
