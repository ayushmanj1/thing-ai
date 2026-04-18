# Nemo AI

Nemo is a powerful, lightweight, text-only AI assistant designed for headless cloud deployment. It features real-time web search capabilities and an aesthetic, high-energy web interface.

## ✨ Features
- **Real-time Search**: Powered by DuckDuckGo and Google Search for up-to-the-minute information.
- **Dynamic UI**: A "Cinema Gloss" black/grey/yellow theme with haptic-styled interactions.
- **Cloud Optimized**: Designed for headless cloud providers like Render, Railway, or Vercel.
- **Fast & Precise**: Uses advanced LLMs (Groq/Cohere) for lightning-fast, high-quality responses.

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- API Keys for **Groq** and **Cohere**.

### Installation
1. Clone the repository (or download the files).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory:
   ```env
   GROQ_API_KEY=your_key_here
   COHERE_API_KEY=your_key_here
   Username=YourName
   Assistantname=Nemo
   ```
4. Run the application:
   ```bash
   python WebMain.py
   ```
5. Open `http://localhost:8000` in your browser.

## 🛠 Tech Stack
- **Backend**: Flask, Groq SDK, Cohere SDK.
- **Frontend**: HTML5, Vanilla CSS3, JavaScript.

## 📝 License
This project is open-source and free to utilize for personal use.
