FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY . .
RUN mkdir -p /app/instance
EXPOSE 3000
CMD ["python", "app.py"]
