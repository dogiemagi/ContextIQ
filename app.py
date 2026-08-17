import os
import warnings
import traceback

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from groq import Groq

from langchain_community.document_loaders import CSVLoader, PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

warnings.filterwarnings("ignore")

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

retriever = None

# -----------------------------
# Groq Configuration
# -----------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set.")

client = Groq(api_key=GROQ_API_KEY)


# -----------------------------
# RAG Pipeline
# -----------------------------
def setup_rag_pipeline(file_path):

    try:
        print(f"Processing file: {file_path}")

        if file_path.lower().endswith(".pdf"):
            loader = PyPDFLoader(file_path)

        elif file_path.lower().endswith(".csv"):
            loader = CSVLoader(
                file_path=file_path,
                csv_args={"delimiter": ","},
                encoding="latin1"
            )

        else:
            raise ValueError(
                "Unsupported file type. Please upload a CSV or PDF."
            )

        documents = loader.load()

        print(f"Loaded {len(documents)} documents.")

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=750,
            chunk_overlap=100
        )

        docs = text_splitter.split_documents(documents)

        print(f"Split into {len(docs)} chunks.")

        print("Loading embedding model...")

        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        print("Embedding model loaded.")

        print("Creating vector store...")

        db = Chroma.from_documents(
            documents=docs,
            embedding=embeddings
        )

        print("Vector store created successfully.")

        return db.as_retriever(search_kwargs={"k": 4})

    except Exception:
        print("\n--- ERROR IN RAG PIPELINE ---")
        traceback.print_exc()
        print("-----------------------------\n")
        raise


# -----------------------------
# Home
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")


# -----------------------------
# Upload
# -----------------------------
@app.route("/upload", methods=["POST"])
def upload_file():

    global retriever

    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = file.filename

    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )

    try:

        file.save(file_path)

        retriever = setup_rag_pipeline(file_path)

        return jsonify({
            "success": f"File '{filename}' uploaded and processed successfully."
        })

    except Exception as e:

        traceback.print_exc()

        return jsonify({
            "error": f"Processing failed: {str(e)}"
        }), 500


# -----------------------------
# Chat
# -----------------------------
@app.route("/chat", methods=["POST"])
def chat():

    global retriever

    if retriever is None:
        return jsonify({
            "error": "Document not uploaded or processed yet."
        }), 400

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "Invalid request."
        }), 400

    user_query = data.get("message")

    if not user_query:
        return jsonify({
            "error": "No message provided."
        }), 400

    try:

        docs = retriever.invoke(user_query)

        context = "\n\n".join(
            [doc.page_content for doc in docs]
        )

        completion = client.chat.completions.create(

            model="llama-3.3-70b-versatile",

            messages=[
                {
                    "role": "system",
                    "content": f"""
You are a document question-answering assistant.

Answer ONLY using the provided context.

If the answer is not present in the context,
say that you could not find the answer in the uploaded document.

Context:
{context}
"""
                },
                {
                    "role": "user",
                    "content": user_query
                }
            ],

            temperature=0
        )

        bot_response = completion.choices[0].message.content

        return jsonify({
            "response": bot_response
        })

    except Exception:

        print("\n--- ERROR IN CHAT ---")
        traceback.print_exc()
        print("---------------------\n")

        return jsonify({
            "error": "Failed to get a response. Check server logs."
        }), 500


# -----------------------------
# Render Entry Point
# -----------------------------
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
