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
from influxdb_client import InfluxDBClient

load_dotenv()

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)

# InfluxDB configuration
influxdb_host = os.getenv('INFLUXDB_HOST')
influxdb_token = os.getenv('INFLUXDB_TOKEN')
influxdb_org = os.getenv('INFLUXDB_ORG')
influxdb_database = os.getenv('INFLUXDB_DATABASE')
influxdb_measurement = os.getenv('INFLUXDB_MEASUREMENT_NAME', 'crypto-trades')

influx_client = InfluxDBClient(url=influxdb_host, token=influxdb_token, org=influxdb_org)

app = dash.Dash(__name__)
app.title = 'Crypto Prices'

app.layout = html.Div(className='container', children=[
    html.H1('Watch your money burn, real-time'),
    html.Div(className='dropdown-container', children=[
        dcc.Dropdown(
            id='symbol-dropdown',
            options=[],
            value=None,  # Default value
            placeholder='Select a symbol',
            className='dropdown'
        ),
    ]),
    html.Div(className='graph-container', children=[
        dcc.Graph(id='live-graph', animate=True),
    ]),
    dcc.Interval(
        id='graph-update',
        interval=1 * 1000,  # Update every second
        n_intervals=0
    ),
    html.Div(id='hidden-div', className='hidden-div')
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
    Output('symbol-dropdown', 'style'),
    Input('symbol-dropdown', 'value')
)
def hide_dropdown_on_select(value):
    if value:
        return {'display': 'none'}
    return {'display': 'block'}

@app.callback(
    Output('live-graph', 'figure'),
    [Input('graph-update', 'n_intervals'),
     Input('symbol-dropdown', 'value'),
     Input('live-graph', 'relayoutData')]
)
def update_graph_live(n, selected_symbol, relayout_data):
    global price_data

    if selected_symbol is None:
        return {'data': [], 'layout': go.Layout(title='No Data', xaxis=dict(title='Time'), yaxis=dict(title='Price'))}

    start_time = None
    end_time = None
    if relayout_data and 'xaxis.range[0]' in relayout_data and 'xaxis.range[1]' in relayout_data:
        start_time = relayout_data['xaxis.range[0]']
        end_time = relayout_data['xaxis.range[1]']

    if selected_symbol not in price_data:
        price_data[selected_symbol] = []

    # Fetch missing data from InfluxDB if necessary
    if start_time and end_time:
        missing_data = fetch_missing_data(selected_symbol, start_time, end_time)
        price_data[selected_symbol].extend(missing_data)
        price_data[selected_symbol].sort(key=lambda x: x['x'])

    data = [
        go.Scatter(
            x=[item['x'] for item in price_data[selected_symbol]],
            y=[item['y'] for item in price_data[selected_symbol]],
            mode='lines+markers'
        )
    ]
    return {'data': data, 'layout': go.Layout(title=f'{selected_symbol.upper()} Price', xaxis=dict(title='Time'), yaxis=dict(title='Price'), paper_bgcolor='#2b2b2b', plot_bgcolor='#2b2b2b', font=dict(color='#e0e0e0'))}

def fetch_missing_data(symbol, start_time, end_time):
    # Convert start_time and end_time to RFC3339 format
    start_time = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S.%fZ").isoformat() + "Z"
    end_time = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%S.%fZ").isoformat() + "Z"
    
    query = f'''from(bucket: "{influxdb_database}")
                |> range(start: {start_time}, stop: {end_time})
                |> filter(fn: (r) => r._measurement == "{influxdb_measurement}" and r.symbol == "{symbol}" and r._field == "price")'''
    
    tables = influx_client.query_api().query(query, org=influxdb_org)
    influx_data = []
    for table in tables:
        for record in table.records:
            influx_data.append({'x': record.get_time().strftime("%Y-%m-%dT%H:%M:%SZ"), 'y': record.get_value()})
    return influx_data

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
