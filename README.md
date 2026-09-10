# ContextIQ 🧠  

**Retrieval-Augmented Generation (RAG) Document Q&A System**

ContextIQ is a **RAG-based web application** that allows users to upload documents (PDF / CSV) and ask questions that are answered **strictly using the uploaded content**.  
It combines **LangChain**, **ChromaDB**, **HuggingFace embeddings**, and **Groq-hosted LLaMA models** into a complete end-to-end GenAI pipeline.


## Key Features

-  Upload PDF or CSV documents
-  Automatic text chunking for efficient retrieval
-  Semantic search using vector embeddings
-  Context-aware answers using an LLM
-  ChromaDB vector store
-  Ultra-low latency LLM inference using Groq
-  Strong error handling and logging


## RAG Pipeline Overview

This project follows the **Retrieval-Augmented Generation (RAG)** architecture:

1. **Document Ingestion**  
   Uploaded documents are loaded using LangChain document loaders.

2. **Text Chunking**  
   Large documents are split into overlapping chunks to preserve context.

3. **Embedding Generation**  
   Each chunk is converted into a semantic vector using HuggingFace embeddings.

4. **Vector Storage (ChromaDB)**  
   Vectors are stored in a Chroma vector database for similarity search.

5. **Query-Time Retrieval**  
   Relevant chunks are retrieved based on semantic similarity.

6. **LLM Response Generation**  
   Retrieved context is passed to a Groq-hosted LLaMA model to generate grounded responses.

## Tech Stack

| Layer | Technology |
|-----|-----------|
| Backend | Flask (Python) |
| LLM | Groq – LLaMA-3.3-70B |
| RAG Framework | LangChain |
| Vector Database | ChromaDB |
| Embeddings | HuggingFace (`all-MiniLM-L6-v2`) |
| Frontend | HTML, CSS, JavaScript |
| CORS | Flask-CORS |


## Project Structure

```

ContextIQ/
├── app.py                 # Main Flask app and RAG pipeline
├── uploads/               # Uploaded documents
├── templates/
│   └── index.html         # Frontend UI
├── static/                # CSS and JS assets
├── requirements.txt       # Python dependencies
└── README.md

````



## Installation & Setup

### Clone the Repository
```bash
git clone https://github.com/dogiemagi/ContextIQ.git
cd ContextIQ
````

### Create Virtual Environment (Recommended)

```bash
python -m venv venv
source venv/bin/activate   # Linux / macOS
venv\Scripts\activate      # Windows
```

### Install Dependencies

```bash
pip install -r requirements.txt
```


## API Key Configuration

This project uses **Groq API** for LLM inference.

1. Create a `.env` file in the project root (copy from `.env.example`):
   ```bash
   cp .env.example .env
   ```

2. Get your Groq API key from [console.groq.com](https://console.groq.com)

3. Add your key to `.env`:
   ```
   GROQ_API_KEY=your_actual_groq_api_key_here
   ```

4. The application will read this automatically


## Running the Application

```bash
python app.py
```

The server will start at:

```
http://localhost:5000
```



## API Endpoints

### `/upload` (POST)

* Uploads a PDF or CSV file
* Builds embeddings
* Initializes the ChromaDB retriever

### `/chat` (POST)

* Accepts a user query
* Retrieves relevant document chunks
* Generates a grounded LLM response



## Error Handling

* Full traceback logging for debugging
* Clear user-friendly error responses
* Validation for:

  * Missing uploads
  * Unsupported file formats
  * Empty queries



## Why This Project Matters

This project demonstrates **real-world GenAI engineering skills**, including:

* Practical use of **RAG architecture**
* Vector search with **ChromaDB**
* Prompt-controlled LLM grounding
* Backend API design
* Production-ready debugging practices

It reflects how **modern AI applications are built in industry**, not just theory.


## Deployment on Render

### Prerequisites

1. A GitHub account with this repository
2. A [Render.com](https://render.com) account (free tier available)
3. A [Groq API key](https://console.groq.com) from https://console.groq.com

### Step-by-Step Deployment

1. **Create a New Web Service on Render**
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New" → "Web Service"
   - Connect your GitHub repository

2. **Configure Environment Variables**
   - In the Render dashboard, go to **Environment** tab
   - Add the following environment variable:
     - Key: `GROQ_API_KEY`
     - Value: `your_actual_groq_api_key`

3. **Build and Deploy**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Instance Type: Free tier is sufficient for testing

4. **Monitor Deployment**
   - Check Logs tab for any errors
   - Visit `https://<your-service>.onrender.com` to access the app
   - Health check: `https://<your-service>.onrender.com/health`

### Important Notes

⚠️ **File Storage Limitation**: Uploaded documents are stored in an ephemeral `/uploads` directory. Files will be **lost when the service restarts** or after 15 minutes of inactivity on the free tier. For production, consider:
- Using Render Persistent Disks
- S3/Cloud Storage integration
- Database-backed file storage

✅ **Production-Ready Features**:
- Auto-scaling with Gunicorn
- Error logging to stdout
- Health check endpoint
- Environment variable configuration
- Python 3.11 runtime

### Troubleshooting

| Issue | Solution |
|-------|----------|
| "GROQ_API_KEY not set" | Verify environment variable in Render dashboard |
| Port binding error | Ensure PORT env var is correctly passed (Render does this automatically) |
| Timeout errors | Groq API may be slow; increase timeout in production settings |
| Vector store errors | Clear `/uploads` folder by restarting the service |


## Future Enhancements

* Persistent ChromaDB storage
* Multi-document querying
* Authentication & user sessions
* Streaming LLM responses
* Hybrid retrieval (keyword + vector)


## License

This project is licensed under the **MIT License**.

