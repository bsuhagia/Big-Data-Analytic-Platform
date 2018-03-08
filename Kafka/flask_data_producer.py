# @Author: Hang Wu <Dukecat>
# @Date:   2017-02-13T21:20:41-05:00
# @Email:  wuhang0613@gmail.com
# @Last modified by:   Dukecat
# @Last modified time: 2017-02-18T14:52:33-05:00

import atexit
import logging
import json
import time
import datetime

#from googlefinance import getQuotes
from apscheduler.schedulers.background import BackgroundScheduler

from flask import (
    Flask,
    request,
    jsonify
)

from kafka import KafkaProducer
from kafka.errors import (
    KafkaError,
    KafkaTimeoutError
)

logger_format = '%(asctime)-15s %(message)s'
logging.basicConfig(format=logger_format)
logger = logging.getLogger('data-producer')
logger.setLevel(logging.INFO)

app = Flask(__name__)
app.config.from_envvar('ENV_CONFIG_FILE')
kafka_broker = app.config['CONFIG_KAFKA_ENDPOINT']
topic_name = app.config['CONFIG_KAFKA_TOPIC']

producer = KafkaProducer(
    bootstrap_servers=kafka_broker
)

schedule = BackgroundScheduler()
schedule.add_executor('threadpool')
schedule.start()

symbols = set()


def shutdown_hook():
    """
    a shutdown hook to be called before the shutdown
    """
    try:
        logger.info('Flushing pending messages to kafka, timeout is set to 10s')
        producer.flush(10)
        logger.info('Finish flushing pending messages to kafka')
    except KafkaError as kafka_error:
        logger.warn('Failed to flush pending messages to kafka, caused by: %s', kafka_error.message)
    finally:
        try:
            logger.info('Closing kafka connection')
            producer.close(10)
        except Exception as e:
            logger.warn('Failed to close kafka connection, caused by: %s', e.message)
    try:
        logger.info('shutdown scheduler')
        schedule.shutdown()
    except Exception as e:
        logger.warn('Failed to shutdown scheduler, caused by: %s', e.message)


def getQuotes(symbol):
    try:
        base = 'https://finance.google.com/finance?q='
        param = code
        suffix = '&output=json'
        url = base + param + suffix
        response = requests.get(url)
        if(response.status_code == 200):
            timestamp = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%dT%H:%MZ')
            fin_data = json.loads(response.content[6:-2].decode('unicode_escape'))
            send_data = {}
            send_data['StockSymbol'] = code
            send_data['LastTradePrice'] = fin_data['op']
            send_data['LastTradeDateTime'] = timestamp
            msg=json.dumps(send_data)
            return msg
    except HTTPError as e:
        logger.warn('Failed to get stock data for %s', e)
       # self.logger().error("Please enter correct stock code!")
            
def fetch_price(symbol):
    """
    helper function to retrieve stock data and send it to kafka
    :param symbol: symbol of the stock
    :return: None
    """
    logger.debug('Start to fetch stock price for %s', symbol)
    try:
        #getQuotes(symbol) cannot be used
        price = json.dumps(getQuotes(symbol))
        logger.debug('Retrieved stock info %s', price)
        producer.send(topic=topic_name, value=price, timestamp_ms=time.time())
        logger.info('Sent stock price for %s to Kafka', symbol)
    except KafkaTimeoutError as timeout_error:
        logger.warn('Failed to send stock price for %s to kafka, caused by: %s', (symbol, timeout_error.message))
    except Exception as e:
        logger.warn('Failed to fetch stock price for %s',e)


@app.route('/<symbol>/add', methods=['POST'])
def add_stock(symbol):
    if not symbol:
        return jsonify({
            'error': 'Stock symbol cannot be empty'
        }), 400
    if symbol in symbols:
        pass
    else:
        symbol = symbol.encode('utf-8')
        symbols.add(symbol)
        logger.info('Add stock retrieve job %s' % symbol)
        schedule.add_job(fetch_price, 'interval', [symbol], seconds=1, id=symbol)
    return jsonify(results=list(symbols)), 200



@app.route('/<symbol>/delete', methods=['POST'])
def del_stock(symbol):
    logger.info('remove the %s' %symbol)
    if not symbol:
        return jsonify({
            'error': 'Stock symbol cannot be empty'
        }), 400
    if symbol not in symbols:
        pass
    else:
        symbol = symbol.encode('utf-8')
        logger.info('remove the %s' %symbol)
        symbols.remove(symbol)
        schedule.remove_job(symbol)
    return jsonify(results=list(symbols)), 200

if __name__ == '__main__':
    atexit.register(shutdown_hook)
    app.run(host='0.0.0.0', port=app.config['CONFIG_APPLICATION_PORT'])
