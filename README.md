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

In `app.py`:

```python
GROQ_API_KEY = "your_key"
```

> Replace with your actual Groq API key before running.


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


## Future Enhancements

* Persistent ChromaDB storage
* Multi-document querying
* Authentication & user sessions
* Streaming LLM responses
* Hybrid retrieval (keyword + vector)


## License

This project is licensed under the **MIT License**.

