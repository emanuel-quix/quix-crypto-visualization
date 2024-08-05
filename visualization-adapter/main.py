import os
import quixstreams as qx
from dotenv import load_dotenv
from app_factory import get_app
import json

load_dotenv()

USE_LOCAL_KAFKA = os.getenv("use_local_kafka", False)

app = get_app(use_local_kafka=USE_LOCAL_KAFKA)

input_topic = app.topic(os.environ["input"])
output_topic = app.topic(os.environ["output"])

sdf = app.dataframe(topic=input_topic)

def to_visualization_format(row):    
    # Prepare the row data in a suitable format for visualization
    timestamp = row['t']
    symbol = row['s']
    price = row['p']
    volume = row['v']
    
    return {
        'symbol': symbol,
        'timestamp': timestamp,
        'price': price,
        'volume': volume
    }

sdf = sdf.apply(to_visualization_format, expand=False)

sdf = sdf.update(lambda value: print('Producing a message:', value))

def produce_to_output_topic(row):
    serialized_value = json.dumps(row)
    output_topic.send(serialized_value)

sdf = sdf.foreach(produce_to_output_topic)

if __name__ == "__main__":
    app.run(sdf)
