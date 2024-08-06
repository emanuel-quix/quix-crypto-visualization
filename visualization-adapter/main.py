import os
import quixstreams as qx
from dotenv import load_dotenv
from app_factory import get_app
from datetime import datetime

load_dotenv()

USE_LOCAL_KAFKA = os.getenv("use_local_kafka", False)

app = get_app(use_local_kafka=USE_LOCAL_KAFKA)

input_topic = app.topic(os.environ["input"])
output_topic = app.topic(os.environ["output"])

sdf = app.dataframe(topic=input_topic)

def to_visualization_format(row):    
    # Prepare the row data in a suitable format for visualization
    timestamp = row['T']
    symbol = row['s']
    price = row['p']

    return {
        'symbol': symbol,
        'timestamp': timestamp / 1000,
        'price': price,
        'datetime': datetime.fromtimestamp(timestamp / 1000).isoformat()
    }

sdf = sdf.apply(to_visualization_format, expand=False)

sdf = sdf.update(lambda value: print('Producing a message:', value))

sdf = sdf.to_topic(output_topic)

if __name__ == "__main__":
    app.run(sdf)
