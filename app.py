import os
import threading

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.memory import InMemorySaver
from langchain.messages import HumanMessage
from langchain.tools import tool
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
bot_user_id = None
thinking_threads = []
thinking_threads_lock = threading.Lock()

def get_bot_user_id(client):
    global bot_user_id
    if bot_user_id is None:
        bot_user_id = client.auth_test()["user_id"]
    return bot_user_id

@tool
def square_root(x: float) -> float:
    """
    Calculate the square root of a number.
    """
    return x ** 0.5

agent = create_agent(
    checkpointer=InMemorySaver(), 
    middleware=[
        SummarizationMiddleware(
            model="gpt-5-nano",
            trigger=("tokens", 10000),
            keep=("messages", 4)
        )
    ],
    model="gpt-5-nano",
    tools=[square_root],
)

def thinking(prompt, client, channel_id, thread_ts):
    try:
        response = agent.invoke(
            {"messages": [HumanMessage(content=prompt)],},
            config = {"configurable": {"thread_id": f"{channel_id}_{thread_ts}"}}
        )
        client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=response["messages"][-1].content)
    finally:
        with thinking_threads_lock:
            thinking_threads.remove(f"{channel_id}_{thread_ts}")

def is_thinking_thread(channel_id, thread_ts):
    with thinking_threads_lock:
        return f"{channel_id}_{thread_ts}" in thinking_threads

def is_app_thread(client, channel_id, thread_ts):
    try:
        result = client.conversations_replies(channel=channel_id, ts=thread_ts, limit=1)
        messages = result.get("messages", [])
        if messages:
            return messages[0].get("user") == get_bot_user_id(client)
        return False
    except SlackApiError:
        return False

@app.event("message")
def handle_message_in_thread(event, client):
    if event.get("bot_id") or event.get("subtype"):
        return
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return
    channel_id = event.get("channel")
    if not is_app_thread(client, channel_id, thread_ts):
        return
    if is_thinking_thread(channel_id, thread_ts):
        client.reactions_add(channel=channel_id, timestamp=event.get("ts"), name="no_entry_sign")
        client.chat_postEphemeral(channel=channel_id, thread_ts=thread_ts, user=event.get("user"), text="I'm already thinking about this. Please wait for me to finish.")
        return
    prompt = event.get("text", "")
    with thinking_threads_lock:
        thinking_threads.append(f"{channel_id}_{thread_ts}")
    client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text="Thinking...")
    threading.Thread(target=thinking, args=(prompt, client, channel_id, thread_ts)).start()

@app.command("/agent")
def handle_agent_command(ack, command, client, respond):
    ack()
    channel_id = command["channel_id"]
    prompt = command.get("text", "")
    message = f"Prompt: {prompt}"
    try:
        result = client.chat_postMessage(channel=channel_id, text=message)
        with thinking_threads_lock:
            thinking_threads.append(f"{channel_id}_{result['ts']}")
        client.chat_postMessage(channel=channel_id, thread_ts=result["ts"], text="Thinking...")
        threading.Thread(target=thinking, args=(prompt, client, channel_id, result["ts"])).start()
    except SlackApiError as e:
        error = e.response["error"]
        if error == "not_in_channel":
            try:
                client.conversations_join(channel=channel_id)
                result = client.chat_postMessage(channel=channel_id, text=message)
                with thinking_threads_lock:
                    thinking_threads.append(f"{channel_id}_{result['ts']}")
                client.chat_postMessage(channel=channel_id, thread_ts=result["ts"], text="Thinking...")
                threading.Thread(target=thinking, args=(prompt, client, channel_id, result["ts"])).start()
            except SlackApiError as join_error:
                respond(f"Something went wrong: {join_error.response['error']}")
        elif error == "channel_not_found":
            respond("I don't have access to this channel. Please invite me by typing `/invite @Hello LangChain` and try again.")
        else:
            respond(f"Something went wrong: {error}")

if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
