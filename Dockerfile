FROM python:3.11-slim

WORKDIR /app

# Copy the requirements file and install Streamlit
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your actual tracking script into the container
COPY . .

# Expose the standard port that web traffic uses
EXPOSE 8501

# Force Streamlit to run your specific file name on the right port
CMD ["streamlit", "run", "gemini-code-1783515619944.py", "--server.port=8501", "--server.address=0.0.0.0"]
