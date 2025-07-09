import os
import json
import base64
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect, Say, Stream
from dotenv import load_dotenv
import logging
import aiohttp
import re
from typing import Optional


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


load_dotenv()
# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') # requires OpenAI Realtime API Access
PORT = int(os.getenv('PORT', 5050))


SYSTEM_MESSAGE = (
  "You are a helpful and bubbly AI assistant who answers any questions I ask"
)
VOICE = 'alloy'
LOG_EVENT_TYPES = [
  'response.content.done', 'rate_limits.updated', 'response.done',
  'input_audio_buffer.committed', 'input_audio_buffer.speech_stopped',
  'input_audio_buffer.speech_started', 'response.create', 'session.created'
]
SHOW_TIMING_MATH = False
app = FastAPI()
if not OPENAI_API_KEY:
  raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')


@app.get("/", response_class=HTMLResponse)
async def index_page():
    return "<html><body><h1>Twilio Media Stream Server is running!</h1></body></html>"
@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    logger.info("Received incoming call request from: %s", request.client.host)
    response = VoiceResponse()
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
    logger.info("Successfully created the TwiML response")
    return HTMLResponse(content=str(response), media_type="application/xml")


@app.api_route("/make-call", methods=["POST"])
async def make_outbound_call(request: Request):
    """Make an outbound call using Twilio."""
    try:
        data = await request.json()
        to_number = data.get('to_number')
        
        if not to_number:
            return {"error": "to_number is required"}
        
        # Create TwiML response for outbound call
        response = VoiceResponse()
        connect = Connect()
        connect.stream(url=f'wss://{request.url.hostname}/media-stream')
        response.append(connect)
        
        # Use Twilio API to make the call
        from twilio.rest import Client
        
        # You'd need to add these to your .env file
        # TWILIO_ACCOUNT_SID=your_account_sid
        # TWILIO_AUTH_TOKEN=your_auth_token
        # TWILIO_PHONE_NUMBER=your_twilio_phone_number
        
        # client = Client(
        #     os.getenv('TWILIO_ACCOUNT_SID'),
        #     os.getenv('TWILIO_AUTH_TOKEN')
        # )
        
        # call = client.calls.create(
        #     to=to_number,
        #     from_=os.getenv('TWILIO_PHONE_NUMBER'),
        #     twiml=str(response)
        # )
        
        return {"message": f"Call initiated to {to_number}", "twiml": str(response)}
        
    except Exception as e:
        logger.error(f"Error making outbound call: {e}")
        return {"error": str(e)}


@app.post("/trigger-call")
async def trigger_call(request: Request):
    """
    Webhook endpoint: POST here to trigger a call to your phone.
    """
    from twilio.rest import Client
    import os

    # Get your phone number and Twilio config from environment variables
    to_number = os.getenv('MY_PHONE_NUMBER')
    from_number = os.getenv('TWILIO_PHONE_NUMBER')
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')

    # The URL Twilio will request for call instructions (TwiML)
    twiml_url = os.getenv('TWIML_URL')

    client = Client(account_sid, auth_token)
    call = client.calls.create(
        to=to_number,
        from_=from_number,
        url=twiml_url
    )
    return {"message": f"Call triggered to {to_number}", "call_sid": call.sid}


# N8N Webhook Configuration
N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL', 'https://your-n8n-instance.com/webhook/directions')
WEBHOOK_TIMEOUT = 30

def extract_location_intent(user_message: str) -> Optional[str]:
    """Extract location/destination from user message using robust regex logic."""
    user_message = user_message.strip().lower()

    # Look for trigger phrases followed by anything that resembles a destination
    patterns = [
        r"(?:directions|navigate|route|take me|go|way)\s+(?:to\s+)?(.+?)(?:[\.\?!]|$)",
        r"how do I get to\s+(.+?)(?:[\.\?!]|$)",
        r"get me to\s+(.+?)(?:[\.\?!]|$)",
        r"head toward\s+(.+?)(?:[\.\?!]|$)",
        r"find\s+(.+?)(?:[\.\?!]|$)",
        r"locate\s+(.+?)(?:[\.\?!]|$)"
    ]

    for pattern in patterns:
        match = re.search(pattern, user_message, re.IGNORECASE)
        if match:
            # Strip potential trailing filler words or punctuation
            destination = re.sub(r"[\.\?!,;:\s]+$", "", match.group(1))
            return destination.strip()

    return None

async def send_to_n8n_webhook(destination: str) -> dict:
    """Send location request to n8n webhook and return response"""
    try:
        payload = {
            "intent": "directions",
            "destination": destination,
            "timestamp": str(asyncio.get_event_loop().time())
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                N8N_WEBHOOK_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=WEBHOOK_TIMEOUT)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "data": result,
                        "message": result.get("message", "Request processed successfully")
                    }
                else:
                    return {
                        "success": False,
                        "message": "I encountered an issue processing your request"
                    }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "message": "The request is taking longer than expected, please try again"
        }
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {
            "success": False,
            "message": "I'm having trouble processing that request right now"
        }

async def process_location_intent(user_message: str, openai_ws):
    """Process location intent and handle webhook communication"""
    destination = extract_location_intent(user_message)
    
    if destination:
        # Send immediate acknowledgment
        acknowledgment = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": f"I'll get directions to {destination} for you. Let me process that request..."
                    }
                ]
            }
        }
        await openai_ws.send(json.dumps(acknowledgment))
        await openai_ws.send(json.dumps({"type": "response.create"}))
        
        # Send to n8n webhook
        webhook_result = await send_to_n8n_webhook(destination)
        
        # Let the AI naturally respond based on the webhook result
        if webhook_result["success"]:
            context_message = f"The directions request to {destination} was processed successfully. The system returned: {webhook_result.get('data', {})}. Please acknowledge this success to the user in a natural, conversational way."
        else:
            context_message = f"There was an issue processing the directions request to {destination}. The error was: {webhook_result.get('message', 'Unknown error')}. Please inform the user about this issue in a natural, helpful way."
        
        # Send context to AI for natural response
        context_item = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": context_message
                    }
                ]
            }
        }
        await openai_ws.send(json.dumps(context_item))
        await openai_ws.send(json.dumps({"type": "response.create"}))
        
        return True
    
    return False

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    print("Client connected")
    await websocket.accept()

    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        await send_session_update(openai_ws)

        # Connection specific state
        stream_sid = None
        latest_media_timestamp = 0
        last_assistant_item = None
        mark_queue = []
        response_start_timestamp_twilio = None

        async def receive_from_twilio():
            """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
            nonlocal stream_sid, latest_media_timestamp
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data['event'] == 'media' and openai_ws.open:
                        latest_media_timestamp = int(data['media']['timestamp'])
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }
                        await openai_ws.send(json.dumps(audio_append))
                    elif data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        print(f"Incoming stream has started {stream_sid}")
                        response_start_timestamp_twilio = None
                        latest_media_timestamp = 0
                        last_assistant_item = None
                    elif data['event'] == 'mark':
                        if mark_queue:
                            mark_queue.pop(0)
                    elif data['event'] == 'stop':
                        logger.info("Twilio call ended. Closing connections.")
                        if openai_ws.open:
                            logger.info("Closing OpenAI WebSocket.")
                            await openai_ws.close()
                            await log_websocket_status(openai_ws)
                        return
            except WebSocketDisconnect:
                print("Client disconnected.")
                if openai_ws.open:
                    await openai_ws.close()
           
        async def log_websocket_status(ws):
            """Utility function to log the state of the WebSocket connection."""
            if ws.open:
                logger.info("OpenAI WebSocket is still open.")
            else:
                logger.info("OpenAI WebSocket is now closed.")

        async def send_to_twilio():
            """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
            nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    if response['type'] in LOG_EVENT_TYPES:
                        print(f"Received event: {response['type']}", response)

                    # Process user input for location intents
                    if response.get('type') == 'conversation.item.input_audio_transcription.completed':
                        transcript = response.get('transcript', '')
                        if transcript:
                            intent_handled = await process_location_intent(transcript, openai_ws)
                            if intent_handled:
                                continue  # Skip normal processing if intent was handled

                    if response.get('type') == 'response.audio.delta' and 'delta' in response:
                        audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                        audio_delta = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": audio_payload
                            }
                        }
                        await websocket.send_json(audio_delta)

                        if response_start_timestamp_twilio is None:
                            response_start_timestamp_twilio = latest_media_timestamp
                            if SHOW_TIMING_MATH:
                                print(f"Setting start timestamp for new response: {response_start_timestamp_twilio}ms")

                        # Update last_assistant_item safely
                        if response.get('item_id'):
                            last_assistant_item = response['item_id']

                        await send_mark(websocket, stream_sid)

                    # Trigger an interruption. Your use case might work better using `input_audio_buffer.speech_stopped`, or combining the two.
                    if response.get('type') == 'input_audio_buffer.speech_started':
                        print("Speech started detected.")
                        if last_assistant_item:
                            print(f"Interrupting response with id: {last_assistant_item}")
                            await handle_speech_started_event()
            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

        async def handle_speech_started_event():
            """Handle interruption when the caller's speech starts."""
            nonlocal response_start_timestamp_twilio, last_assistant_item
            print("Handling speech started event.")
            if mark_queue and response_start_timestamp_twilio is not None:
                elapsed_time = latest_media_timestamp - response_start_timestamp_twilio
                if SHOW_TIMING_MATH:
                    print(f"Calculating elapsed time for truncation: {latest_media_timestamp} - {response_start_timestamp_twilio} = {elapsed_time}ms")

                if last_assistant_item:
                    if SHOW_TIMING_MATH:
                        print(f"Truncating item with ID: {last_assistant_item}, Truncated at: {elapsed_time}ms")

                    truncate_event = {
                        "type": "conversation.item.truncate",
                        "item_id": last_assistant_item,
                        "content_index": 0,
                        "audio_end_ms": elapsed_time
                    }
                    await openai_ws.send(json.dumps(truncate_event))

                await websocket.send_json({
                    "event": "clear",
                    "streamSid": stream_sid
                })

                mark_queue.clear()
                last_assistant_item = None
                response_start_timestamp_twilio = None

        async def send_mark(connection, stream_sid):
            if stream_sid:
                mark_event = {
                    "event": "mark",
                    "streamSid": stream_sid,
                    "mark": {"name": "responsePart"}
                }
                await connection.send_json(mark_event)
                mark_queue.append('responsePart')

        await asyncio.gather(receive_from_twilio(), send_to_twilio())

async def send_initial_conversation_item(openai_ws):
    """Send initial conversation item if AI talks first."""
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Greet the user with 'Hello there! I am an AI voice assistant that will help you with any questions you may have. Please ask me anything you want to know.'"
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({"type": "response.create"}))

async def send_session_update(openai_ws):
    """Send session update to OpenAI WebSocket."""

    session_update = {
      "type": "session.update",
      "session": {
          "turn_detection": {"type": "server_vad"},
          "input_audio_format": "g711_ulaw",
          "output_audio_format": "g711_ulaw",
          "voice": VOICE,
          "instructions": SYSTEM_MESSAGE,
          "modalities": ["text", "audio"],
          "temperature": 0.8,
          "input_audio_transcription": {"model": "whisper-1"}
      }
    }
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))

    await send_initial_conversation_item(openai_ws)

if __name__ == "__main__":
  import uvicorn
  uvicorn.run(app, host="0.0.0.0", port=PORT)


