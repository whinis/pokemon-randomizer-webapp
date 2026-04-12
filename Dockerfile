# Use a lightweight Python image as the base
FROM python:3.9-slim

# Install OpenJDK 21 (Compatible with most Java 8 applications)
RUN apt-get update && \
    apt-get install -y openjdk-21-jre-headless && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install Python dependencies
RUN pip install --no-cache-dir flask

# Copy the rest of the application code
COPY . .

# Expose the port that Flask will use (5000)
EXPOSE 5000

# Set the default command to run your Flask application
CMD ["python", "app.py"]
