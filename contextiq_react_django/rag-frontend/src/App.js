import { useState } from "react";
import "./App.css";

function App() {
  const [file, setFile] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploaded, setUploaded] = useState(false);

  // ---------- Upload ----------
  const uploadFile = async () => {
    if (!file) {
      alert("Please select a file first");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      setLoading(true);

      const res = await fetch("/upload/", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      setLoading(false);

      if (data.success) {
        setUploaded(true);
        setMessages([
          { role: "bot", text: "Document uploaded successfully. You can start chatting." }
        ]);
      } else {
        alert(data.error);
      }
    } catch (err) {
      setLoading(false);
      alert("Upload failed. Is backend running?");
      console.error(err);
    }
  };

  // ---------- Chat ----------
  const sendMessage = async () => {
    if (!input.trim()) return;

    setMessages(prev => [...prev, { role: "user", text: input }]);
    const userMessage = input;
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/chat/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMessage }),
      });

      const data = await res.json();
      setLoading(false);

      setMessages(prev => [
        ...prev,
        { 
  role: "bot", 
  text: (data.response || data.error)
  .replace(/\*\*/g, "")
  .replace(/\*/g, "")
  .replace(/(\d+)\.\s+/g, "\n$1. ")
  .trim()

}

      ]);
    } catch (err) {
      setLoading(false);
      alert("Chat failed. Is backend running?");
      console.error(err);
    }
  };

  return (
    <div className="container">

      {/* Upload */}
      <div className="card">
        <h2>1. Upload Your Document</h2>
        <p>Upload a CSV or PDF file to start chatting.</p>

        <div className="upload-row">
          <input type="file" onChange={(e) => setFile(e.target.files[0])} />
          <button onClick={uploadFile}>Upload & Process</button>
        </div>

        {loading && <p className="status">Uploading and processing...</p>}
      </div>

      {/* Chat */}
      <div className="chat-card">
        <div className="chat-header">2. Chat with Your Document</div>

        <div className="chat-body">
          {!uploaded && (
            <div className="bot-msg">
              Please upload a document to begin the conversation.
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "user-msg" : "bot-msg"}>
              {m.text}
            </div>
          ))}

          {loading && <div className="bot-msg">Thinking...</div>}
        </div>

        <div className="chat-input">
          <input
            placeholder="Type your message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={!uploaded}
          />
          <button onClick={sendMessage} disabled={!uploaded}>
            Send
          </button>
        </div>
      </div>

    </div>
  );
}

export default App;
