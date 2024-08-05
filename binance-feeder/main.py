import websocket
import os
import json
import requests
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

def get_popular_symbols(limit=10):

    binance_api_endpoint = os.getenv("BINANCE_API_ENDPOINT")

    response = requests.get(binance_api_endpoint+ "ticker/24hr")
    if response.status_code == 200:
        tickers = response.json()
        # Sort tickers by volume and get the top symbols
        sorted_tickers = sorted(tickers, key=lambda x: float(x['volume']), reverse=True)
        popular_symbols = [ticker['symbol'].lower() for ticker in sorted_tickers[:limit]]
        return popular_symbols
    else:
        print("Error fetching symbols")
        return []

def on_message(ws, message):
    message_obj = json.loads(message)
    print("Producing: " + message)
    
    serialized_value = serializer(value=message_obj, ctx=SerializationContext(topic=topic.name))
    
    try:
        producer.produce(topic=topic.name, key=message_obj['s'], value=serialized_value)
    except Exception as error:
        print("Error while producing:", error)

def on_error(ws, error):
    print(error)

def on_close(ws, close_status_code, close_msg):
    print("### closed ###")

def on_open(ws):
    print("WebSocket connection opened")
    symbols = get_popular_symbols()
    subscribe_message = {
        "method": "SUBSCRIBE",
        "params": [f"{symbol}@trade" for symbol in symbols],
        "id": 1
    }
    ws.send(json.dumps(subscribe_message))

def main():
    with producer: 
        binance_ws_endpoint = os.getenv("BINANCE_WS_ENDPOINT")
        
        websocket.enableTrace(False)
        ws = websocket.WebSocketApp(binance_ws_endpoint,
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
