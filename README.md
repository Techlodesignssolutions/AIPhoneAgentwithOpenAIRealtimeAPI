# AIPhoneAgentwithOpenAIRealtimeAPI

**OpenAI Realtime Voice Assistant with Twilio Integration**

This project demonstrates how to create an AI voice assistant that uses Twilio and the OpenAI Realtime API to handle phone calls in real time. The assistant is built using Python and FastAPI and can answer questions with a conversational, bubbly tone.

**Overview**

The code uses the following resources to function effectively:

Twilio's Python Guide: [Voice AI Assistant with OpenAI Realtime API]( https://www.twilio.com/en-us/blog/voice-ai-assistant-openai-realtime-api-python)

Twilio Python GitHub Repo Sample: [GitHub - Speech Assistant Sample](https://github.com/twilio-samples/speech-assistant-openai-realtime-api-python)

**Documentation Links**

Understanding the functionality of the code and the services it interacts with is crucial. Here are some useful documentation links:

Twilio Media Stream Events: [WebSocket Messages to Twilio](https://www.twilio.com/docs/voice/media-streams/websocket-messages)

Twilio Markup Language (TwiML): [TwiML Documentation](https://www.twilio.com/docs/voice/twiml)

OpenAI Realtime API: [OpenAI Realtime API Overview](https://platform.openai.com/docs/guides/realtime/overview)

OpenAI RealtimeEvents: [Realtime Events Documentation](https://platform.openai.com/docs/api-reference/realtime)

**How to Use Environment Variables**

For better security, secrets like the OPENAI_API_KEY should be stored in an .env file. Here's how to set it up:

Create a .env file in the root directory of the project.

Add the following key-value pairs:

```
OPENAI_API_KEY=your_openai_api_key_here
PORT=5050  # or any other port you want to use
```

The dotenv library will load these variables at runtime.

**How the Code Works**

**Setting Up a WebSocket**

The WebSocket is established between Twilio and OpenAI's Realtime API:

Starting a WebSocket: The websockets.connect() function is used to create a secure WebSocket connection to the OpenAI Realtime API. The Authorization and OpenAI-Beta headers are provided for authentication and to enable the beta features.

Sending Session Updates: Once the WebSocket is connected, session settings like audio formats, voice parameters, and instructions are sent to configure the conversation.

**Sending and Receiving Audio to Twilio**

Receiving from Twilio: The receive_from_twilio() function listens for audio data from Twilio's Media Stream. It extracts the audio payload from incoming messages and sends it to the OpenAI Realtime API.

Sending to Twilio: The send_to_twilio() function listens for responses from the OpenAI API. When audio data is received, it's encoded and sent back to Twilio in the required format.

Streaming Setup: The handle_media_stream WebSocket endpoint handles incoming audio from Twilio, connects to the OpenAI Realtime API, and ensures data flows between both services.

**Handling Interruptions**

The code handles interruptions gracefully:

When the caller starts speaking (input_audio_buffer.speech_started), the assistant's response is truncated to avoid overlap.

The handle_speech_started_event() function calculates the elapsed time and sends a truncate event to the OpenAI API, clearing the assistant's audio response and preparing for the caller's next input.

**Getting Started**

Install Dependencies:

```sh
pip install -r requirements.txt
```

Run the Application:

```sh
python your_script_name.py
```

The server will run on http://0.0.0.0:PORT, where PORT is specified in your .env file.

**Set up ngrok so Twilio can access your local server**
![image](https://github.com/user-attachments/assets/510ecf96-ae94-4519-ab7d-6527f84df8b2)

Instructions on how to setup ngrok - [Ngrok Setup](https://ngrok.com/docs/getting-started/)


**Add your Url and /incoming-call endpoint to an Active number of your choosing in Twilio**
![image](https://github.com/user-attachments/assets/9e5b1235-bc3c-41f6-af4b-590bf36ff0eb)



**Example Replit Template**

You can easily fork and run this project on Replit using this link:

[Replit Template](https://replit.com/@AlozieIgbokwe2/OpenAI-Realtime-Assisstant)

Feel free to use and customize the template for your own project needs.

