import os
import json
import traceback
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from groq import Groq
from langchain_community.document_loaders import PyPDFLoader, CSVLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# ---------------- GLOBAL RETRIEVER ----------------
retriever = None

# ---------------- GROQ CLIENT ----------------
GROQ_API_KEY = "your_api"
client = Groq(api_key=GROQ_API_KEY)

# ---------------- RAG SETUP ----------------
def setup_rag_pipeline(file_path):
    if file_path.endswith(".pdf"):
        loader = PyPDFLoader(file_path)
    elif file_path.endswith(".csv"):
        loader = CSVLoader(file_path=file_path, encoding="latin1")
    else:
        raise ValueError("Only PDF or CSV supported")

    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=750,
        chunk_overlap=100
    )
    docs = splitter.split_documents(documents)

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    db = Chroma.from_documents(docs, embeddings)
    return db.as_retriever()

# ---------------- VIEWS ----------------
def index(request):
    return render(request, "index.html")

@csrf_exempt
def upload_file(request):
    global retriever

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "No file uploaded"}, status=400)

    try:
        file_path = os.path.join(settings.MEDIA_ROOT, file.name)

        with open(file_path, "wb+") as f:
            for chunk in file.chunks():
                f.write(chunk)

        retriever = setup_rag_pipeline(file_path)

        return JsonResponse({
            "success": "File uploaded and processed successfully"
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
def chat(request):
    global retriever

    if retriever is None:
        return JsonResponse({"error": "Upload a file first"}, status=400)

    if request.method != "POST":
        return JsonResponse({"error": "POST method required"}, status=400)

    try:
        data = json.loads(request.body)
        user_query = data.get("message")

        docs = retriever.invoke(user_query)   # ✅ FIXED HERE
        context = "\n".join(d.page_content for d in docs)

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"Answer ONLY from this context:\n{context}"},
                {"role": "user", "content": user_query}
            ],
            temperature=0
        )

        return JsonResponse({
            "response": completion.choices[0].message.content
        })

    except Exception:
        traceback.print_exc()
        return JsonResponse({"error": "Chat failed"}, status=500)
