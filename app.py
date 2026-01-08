import os
import threading
import time

from langchain.chat_models import init_chat_model
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
model = init_chat_model(model="gpt-5-nano")

def thinking(prompt, client, channel_id, thread_ts):
    response = model.invoke(prompt)
    client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=response.content)

@app.command("/agent")
def handle_agent_command(ack, command, client, respond):
    ack()
    channel_id = command["channel_id"]
    prompt = command.get("text", "")
    message = f"Prompt: {prompt}"
    try:
        result = client.chat_postMessage(channel=channel_id, text=message)
        client.chat_postMessage(channel=channel_id, thread_ts=result["ts"], text="Thinking...")
        threading.Thread(target=thinking, args=(prompt,client, channel_id, result["ts"])).start()
    except SlackApiError as e:
        error = e.response["error"]
        if error == "not_in_channel":
            try:
                client.conversations_join(channel=channel_id)
                result = client.chat_postMessage(channel=channel_id, text=message)
                client.chat_postMessage(channel=channel_id, thread_ts=result["ts"], text="Thinking...")
                threading.Thread(target=thinking, args=(client, channel_id, result["ts"])).start()
            except SlackApiError as join_error:
                respond(f"Something went wrong: {join_error.response['error']}")
        elif error == "channel_not_found":
            respond("I don't have access to this channel. Please invite me by typing `/invite @Hello LangChain` and try again.")
        else:
            respond(f"Something went wrong: {error}")

if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
