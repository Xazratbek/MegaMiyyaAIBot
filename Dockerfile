# Use an official Python runtime as the base image
FROM python:3.9

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port your app will run on
EXPOSE $PORT

# Command to run the application
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:$PORT", "bot:app"]
