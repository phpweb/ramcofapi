import json
import asyncio
from fastapi import Depends, BackgroundTasks, FastAPI
from config import Settings, get_settings
import bn_client as bn_client
import utils as utils
import redis_client as redis_client
import models as models

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


async def place_order(signal: models.Signal, background_tasks: BackgroundTasks):
    settings = get_settings()
    bn = bn_client.BinanceClientAsync(api_key=settings.api_key, secret_key=settings.api_secret)
    pair = signal.ticker_pair.upper()
    # if signal.side.upper() == 'SELL':
    # await cancel_st_tasks_and_open_orders(bn, pair)
    # To calculate buy quantity and trade FIAT symbol name.
    balance_symbol = utils.extract_balance_symbol_from_pair(pair)
    # To calculate sell quantity.
    ticker_symbol = utils.extract_ticker_symbol_from_pair(pair)
    # if the transaction sell is
    if signal.side.upper() == 'SELL':
        balance_symbol = ticker_symbol
    price, balance = await bn.get_price_and_balance(pair, balance_symbol)
    symbol_info = await get_symbol_info(bn, pair)
    # For testing
    quantity = 0.0
    if signal.side.upper() == 'BUY':
        balance = 30.00
        quantity = utils.calculate_quantity(balance, price, symbol_info['quantity_step_size'])

    if signal.side.upper() == 'SELL':
        stop_loss_order_id = redis_client.get_from_cache(f'{pair}_stop_loss_orderId')
        await bn.cancel_order(pair, stop_loss_order_id)
        quantity = utils.calculate_sell_quantity(balance, symbol_info['quantity_step_size'])

    if quantity:
        # If the side sell then cancel all open orders and st bg tasks

        # background_tasks.add_task(cancel_st_tasks_and_open_orders, bn, pair)
        # order = await bn.create_order(pair, signal.side.upper(), 90, 'LIMIT', float(price))
        order = await bn.create_order(pair, signal.side.upper(), quantity, 'LIMIT', float(price))
        # Check the status if it is filled
        order_status = await bn.query_order(pair, order['orderId'])
        cancel_order = None
        if order_status is not None:
            if order_status['status'] != 'FILLED':
                # Wait 2 seconds
                await asyncio.sleep(1)
                cancel_order = await bn.cancel_order(pair, order['orderId'])
                if cancel_order is not None:
                    await place_order(signal, background_tasks)
                    return
            if signal.side.upper() == 'BUY':
                placed_order = models.PlacedOrder(
                    id=order['orderId'],
                    price=order['price'],
                    quantity=order['origQty'],
                    status=order['status'],
                    symbol=pair
                )
                # redis_client.set_to_cache('placed_order', placed_order.json())
                # background_tasks.add_task(task_list, placed_order)
                background_tasks.add_task(place_stop_loss_order, signal.ticker_pair.upper(), order['price'],
                                          order['origQty'])
            print(order)
        # print(f'price = {price} balance = {balance}')
        return {
            'price': price,
            'balance': balance,
            'order': order,
            'cancel_order': cancel_order
        }
    else:
        return {'min_notional': 'Not enough quantity'}


@app.post("/signal/")
async def create_item(signal: models.Signal, background_tasks: BackgroundTasks):
    settings = get_settings()
    if signal.passphrase != settings.hook_secret:
        return {'no_neo': 'no way'}
    background_tasks.add_task(place_order, signal, background_tasks)
    return {'order': 'has been placed'}
    # return {'dont_buy': True}


async def get_symbol_info(bn, pair):
    await bn.open()
    symbol_info_from_redis = redis_client.get_from_cache(f'symbol_info_{pair}')
    symbol_info = None
    if symbol_info_from_redis is not None:
        symbol_info = json.loads(symbol_info_from_redis)
    else:
        symbol_info = await bn.get_symbol_exchange_info(pair)
        price_tick_size, quantity_step_size, min_notional = utils.get_price_tick_quantity_step_min_notional(symbol_info)
        symbol_info = {
            'price_tick_size': price_tick_size,
            'quantity_step_size': quantity_step_size,
            'min_notional': min_notional,
            'orderTypes': symbol_info['orderTypes']
        }
        redis_client.set_to_cache(key=f'symbol_info_{pair}', value=json.dumps(symbol_info))
    return symbol_info


async def place_order_limit_maker(symbol, bought_price, quantity):
    settings = get_settings()
    bn = bn_client.BinanceClientAsync(api_key=settings.api_key, secret_key=settings.api_secret)
    symbol_info_from_redis = redis_client.get_from_cache(f'symbol_info_{symbol}')
    symbol_info = json.loads(symbol_info_from_redis)
    quantity = utils.calculate_sell_quantity(quantity, symbol_info['quantity_step_size'])
    price = float(1 + 0.005) * float(bought_price)
    price = "{:0.0{}f}".format(price, symbol_info['price_tick_size'])
    order_limit_maker = await bn.order_limit_maker(symbol, 'SELL', quantity, price)
    print('waht is order_limit_maker')
    print(order_limit_maker)
    redis_client.set_to_cache(f'{symbol}_order_limit_maker_orderId', order_limit_maker['orderId'])
    return order_limit_maker


async def place_stop_loss_order(symbol, bought_price, quantity):
    settings = get_settings()
    bn = bn_client.BinanceClientAsync(api_key=settings.api_key, secret_key=settings.api_secret)
    symbol_info_from_redis = redis_client.get_from_cache(f'symbol_info_{symbol}')
    symbol_info = json.loads(symbol_info_from_redis)
    quantity = utils.calculate_sell_quantity(quantity, symbol_info['quantity_step_size'])
    price = float(1 - 0.004) * float(bought_price)
    price = "{:0.0{}f}".format(price, symbol_info['price_tick_size'])
    stop_price = price
    stop_loss_limit = await bn.order_stop_loss_limit(symbol, 'SELL', quantity, stop_price, price)
    print('waht is stop loss order')
    print(stop_loss_limit)
    redis_client.set_to_cache(f'{symbol}_stop_loss_orderId', stop_loss_limit['orderId'])
    return stop_loss_limit
