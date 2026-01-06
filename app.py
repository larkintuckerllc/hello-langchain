import os

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

@app.command("/agent")
def handle_agent_command(ack, command, client):
    ack()
    channel_id = command["channel_id"]
    prompt = command.get("text", "")
    client.conversations_join(channel=channel_id)
    client.chat_postMessage(
        channel=channel_id,
        text=f"Working on the prompt... {prompt}"
    )

if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
