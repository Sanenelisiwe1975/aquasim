"""
Creates all required Kafka topics.
Run once before starting the engine:
  python scripts/init_kafka_topics.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")

TOPICS = [
    ("market_ticks",      4, 1),
    ("orderbook_updates", 4, 1),
    ("orders",            2, 1),
    ("trades",            2, 1),
    ("positions",         2, 1),
    ("pnl_updates",       2, 1),
    ("risk_events",       1, 1),
]

def main():
    client = KafkaAdminClient(bootstrap_servers=BOOTSTRAP)
    new_topics = [
        NewTopic(name=name, num_partitions=parts, replication_factor=repl)
        for name, parts, repl in TOPICS
    ]
    for topic in new_topics:
        try:
            client.create_topics([topic])
            print(f"Created topic: {topic.name}")
        except TopicAlreadyExistsError:
            print(f"Topic already exists: {topic.name}")
    client.close()
    print("Done.")

if __name__ == "__main__":
    main()
