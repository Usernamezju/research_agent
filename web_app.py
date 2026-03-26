# web_app.py — Flask Web 界面，使用 SSE 实时推送

import json
import queue
import threading
import os
from flask import Flask, Response, render_template, request, stream_with_context
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/research", methods=["POST"])
def research():
    """接收调研主题，启动 Agent，通过 SSE 实时推送事件"""
    data = request.get_json()
    topic = (data or {}).get("topic", "").strip()

    if not topic:
        return {"error": "请输入调研主题"}, 400

    q = queue.Queue()

    def callback(event_type, event_data):
        q.put(json.dumps({"type": event_type, "data": event_data}, ensure_ascii=False))

    def run():
        try:
            from agent import run_research_agent
            run_research_agent(topic, callback=callback)
        except Exception as e:
            q.put(json.dumps({"type": "error", "data": str(e)}, ensure_ascii=False))
        finally:
            q.put(None)  # 终止信号

    t = threading.Thread(target=run, daemon=True)
    t.start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                yield "data: {\"type\": \"end\"}\n\n"
                break
            yield f"data: {item}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    port = int(os.environ.get("PORT", 5000))
    print(f"Research Agent Web started on port {port}")
    app.run(debug=False, threaded=True, host="0.0.0.0", port=port)
