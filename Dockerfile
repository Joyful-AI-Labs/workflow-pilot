FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pilot ./pilot
COPY samples ./samples
RUN mkdir -p data/inbox
EXPOSE 8000
CMD ["python", "-m", "pilot"]
