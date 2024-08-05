import websocket
import os
import json
from dotenv import load_dotenv
from quixstreams.models.serializers.quix import JSONSerializer, SerializationContext
from app_factory import get_app

load_dotenv()

# Define a serializer for messages, using JSON Serializer for ease
serializer = JSONSerializer()

# Get environment variables
USE_LOCAL_KAFKA = os.getenv("use_local_kafka", False)

# Create an Application.
app = get_app(use_local_kafka=USE_LOCAL_KAFKA)

topic_name = os.environ["TRADES_TOPIC"]
topic = app.topic(topic_name)

# Create a pre-configured Producer object.
# Producer is already setup to use Quix brokers.
# It will also ensure that the topics exist before producing to them if
# Application.Quix is initialized with "auto_create_topics=True".
producer = app.get_producer()

def on_message(ws, message):
    message_obj = json.loads(message)
    print("Producing: " + message)

    data = {
        'symbol': message_obj['s'],
        'timestamp': message_obj['T'],
        'price': message_obj['p'],
        'volume': message_obj['q']
    }
    
    serialized_value = serializer(value=data, ctx=SerializationContext(topic=topic.name))
    
    try:
        producer.produce(topic=topic.name, key=message_obj['s'], value=serialized_value)
    except Exception as error:
        print("Error while producing:", error)

def on_error(ws, error):
    print(error)

def on_close(ws, arg1, arg2):
    print("### closed ###")

def on_open(ws):
    print("WebSocket connection opened")
    subscribe_message = {
        "method": "SUBSCRIBE",
        "params": ["btcusdt@trade"],
        "id": 1
    }
    ws.send(json.dumps(subscribe_message))

def main():
    with producer: 
        binance_endpoint = os.getenv("BINANCE_ENDPOINT")
        
        websocket.enableTrace(False)
        ws = websocket.WebSocketApp(binance_endpoint,
                                    on_message=on_message,
                                    on_error=on_error,
                                    on_close=on_close)
        ws.on_open = on_open
        ws.run_forever()
        ws.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Exiting.")
