from pydantic import BaseModel


class Signal(BaseModel):
    passphrase: str
    side: str
    exchange: str
    ticker_pair: str
    timeframe: str
    signaltype: str
    params: str
    time: str
    is_realtime: str
    current_price: str


class PlacedOrder(BaseModel):
    id: int
    price: str
    quantity: str
    status: str
    symbol: str
