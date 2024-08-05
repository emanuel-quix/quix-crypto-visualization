import dash
from dash import dcc, html
from dash.dependencies import Output, Input
import plotly.graph_objs as go
import os
import asyncio
import json
import logging
import sys
from dotenv import load_dotenv
from quixstreams import Application
import threading
from datetime import datetime

load_dotenv()

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)

app = dash.Dash(__name__)
app.layout = html.Div([
    html.H1('Real-time Crypto Prices'),
    dcc.Graph(id='live-graph', animate=True),
    dcc.Interval(
        id='graph-update',
        interval=1*1000,  # Update every second
        n_intervals=0
    )
])

# Initialize price data with the current time
price_data = []

async def process_message(payload):
    global price_data
    try:
        item = json.loads(payload)
        timestamp = datetime.fromtimestamp(item['timestamp'] / 1000)  # Convert Unix timestamp to datetime
        price_data.append({'x': timestamp, 'y': item['price']})

    except Exception as e:
        logger.error("Error processing message: %s", str(e))

async def consume_messages(quix_app):
    consumer = quix_app.get_consumer()
    input_topic = quix_app.topic(os.getenv("input")).name
    consumer.subscribe([input_topic])
    logger.info("Waiting for messages...")
    while True:
        msg = consumer.poll(timeout=1.0)
        if msg is not None:
            try:
                payload = msg.value().decode('utf-8')
                logger.info("Received message: %s", payload)
                await process_message(payload)
            except Exception as e:
                logger.error("Error processing message: %s", str(e))

@app.callback(Output('live-graph', 'figure'),
              Input('graph-update', 'n_intervals'))
def update_graph_live(n):
    global price_data
    data = [
        go.Scatter(
            x=[data['x'] for data in price_data],
            y=[data['y'] for data in price_data],
            mode='lines+markers'
        )
    ]
    return {'data': data, 'layout': go.Layout(title='BTC/USDT Price', xaxis=dict(title='Time'), yaxis=dict(title='Price'))}

def run_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def start_async_tasks():
    loop = asyncio.new_event_loop()
    threading.Thread(target=run_async_loop, args=(loop,)).start()
    quix_app = Application.Quix(
        consumer_group="crypto_visualization",
        auto_offset_reset="latest",
        auto_create_topics=True,
    )
    asyncio.run_coroutine_threadsafe(consume_messages(quix_app), loop)

if __name__ == '__main__':
    start_async_tasks()
    app.run_server(debug=True, use_reloader=False)
