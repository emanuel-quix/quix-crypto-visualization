import dash
from dash import dcc, html
from dash.dependencies import Output, Input, State
import plotly.graph_objs as go
import os
import asyncio
import json
import logging
import sys
from dotenv import load_dotenv
from quixstreams import Application
import threading
import uuid

from datetime import datetime
from urllib.parse import urlparse, parse_qs

load_dotenv()

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)

app = dash.Dash(__name__)
app.layout = html.Div([
    html.H1('Real-time Crypto Prices'),
    dcc.Location(id='url', refresh=False),  # To read the URL query string
    dcc.Dropdown(
        id='symbol-dropdown',
        options=[],
        value=None,  # Default value
        placeholder='Select a symbol'
    ),
    dcc.Graph(id='live-graph', animate=True),
    dcc.Interval(
        id='graph-update',
        interval=1*1000,  # Update every second
        n_intervals=0
    )
])

# Initialize price data dictionary and symbol options list
price_data = {}
symbol_options = []

async def process_message(payload):
    global price_data, symbol_options
    try:
        item = json.loads(payload)
        symbol = item['symbol'].lower()
        datetime = item['datetime']

        if symbol not in price_data:
            price_data[symbol] = []
            symbol_options.append({'label': symbol.upper(), 'value': symbol})
        
        price_data[symbol].append({'x': datetime, 'y': item['price']})
        # Limit the number of points to avoid memory issues
        if len(price_data[symbol]) > 1000000:
            price_data[symbol] = price_data[symbol][-1000000:]
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

@app.callback(
    Output('symbol-dropdown', 'options'),
    Input('graph-update', 'n_intervals')
)
def update_dropdown_options(n):
    global symbol_options
    return symbol_options

@app.callback(
    [Output('symbol-dropdown', 'value'), Output('live-graph', 'figure')],
    [Input('url', 'href'), Input('graph-update', 'n_intervals'), Input('symbol-dropdown', 'value')]
)
def update_graph_live(url, n, selected_symbol):
    global price_data, symbol_options
    ctx = dash.callback_context

    if not ctx.triggered:
        return dash.no_update, dash.no_update

    if ctx.triggered[0]['prop_id'] == 'url.href':
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        symbol_from_query = query_params.get('symbol', [None])[0]
        if symbol_from_query and symbol_from_query.lower() in price_data:
            selected_symbol = symbol_from_query.lower()

    if selected_symbol is None or selected_symbol not in price_data:
        return selected_symbol, {'data': [], 'layout': go.Layout(title='No Data', xaxis=dict(title='Time'), yaxis=dict(title='Price'))}
    
    data = [
        go.Scatter(
            x=[data['x'] for data in price_data[selected_symbol]],
            y=[data['y'] for data in price_data[selected_symbol]],
            mode='lines+markers'
        )
    ]
    return selected_symbol, {'data': data, 'layout': go.Layout(title=f'{selected_symbol.upper()} Price', xaxis=dict(title='Time'), yaxis=dict(title='Price'))}

def run_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def start_async_tasks():
    loop = asyncio.new_event_loop()
    threading.Thread(target=run_async_loop, args=(loop,)).start()
    quix_app = Application.Quix(
        consumer_group=str(uuid.uuid4()),
        auto_offset_reset="latest",
        auto_create_topics=True,
    )
    asyncio.run_coroutine_threadsafe(consume_messages(quix_app), loop)

if __name__ == '__main__':
    start_async_tasks()
    port = int(os.getenv('PORT', 8050))
    app.run_server(debug=True, host='0.0.0.0', use_reloader=False, port=port)
