import typing

import pymongo
import tabulate
from pymongo import MongoClient
from pymongo.collection import Collection

import ParadoxTrading.Engine
from ParadoxTrading.Engine.Event import SignalType, OrderType, ActionType, \
    DirectionType, FillEvent, OrderEvent, SignalEvent
from ParadoxTrading.Engine.Strategy import StrategyAbstract


class PortfolioPerStrategy:
    def __init__(self):
        # records for signal, order and fill
        self.signal_record: typing.List[SignalEvent] = []
        self.order_record: typing.List[OrderEvent] = []
        self.fill_record: typing.List[FillEvent] = []

        # cur order and position state
        self.position: typing.Dict[str, typing.Dict[str, int]] = {}
        self.unfilled_order: typing.Dict[int, OrderEvent] = {}

    def incPosition(self, _instrument: str, _type: str, _quantity: int = 1):
        """
        inc position of instrument

        :param _instrument: instrument to inc
        :param _type: long or short
        :param _quantity: how many
        :return:
        """
        assert _type == SignalType.LONG or _type == SignalType.SHORT
        assert _quantity > 0
        try:
            # try to add directly
            self.position[_instrument][_type] += _quantity
        except KeyError:
            # create if failed
            self.position[_instrument] = {
                SignalType.LONG: 0,
                SignalType.SHORT: 0,
            }
            self.position[_instrument][_type] = _quantity

    def decPosition(self, _instrument: str, _type: str, _quantity: int = 1):
        """
        dec position of instrument

        :param _instrument: instrument to inc
        :param _type: long or short
        :param _quantity: how many
        :return:
        """
        assert _type == SignalType.LONG or _type == SignalType.SHORT
        assert _quantity > 0
        assert _instrument in self.position.keys()
        assert self.position[_instrument][_type] >= _quantity
        self.position[_instrument][_type] -= _quantity
        assert self.position[_instrument][_type] >= 0

    def getPosition(self, _instrument: str, _type: str) -> int:
        """
        get _type position of instrument

        :param _instrument: which instrument
        :param _type: long or short
        :return: number of position
        """
        assert _type == SignalType.LONG or _type == SignalType.SHORT
        if _instrument in self.position.keys():
            return self.position[_instrument][_type]
        return 0

    def getLongPosition(self, _instrument: str) -> int:
        """
        get long position of instrument

        :param _instrument: which instrument
        :return: number of position
        """
        return self.getPosition(_instrument, SignalType.LONG)

    def getShortPosition(self, _instrument: str) -> int:
        """
        get short position of instrument

        :param _instrument: which instrument
        :return: number of position
        """
        return self.getPosition(_instrument, SignalType.SHORT)

    def getUnfilledOrder(self, _instrument: str, _action: int,
                         _direction: int) -> int:
        """
        get number of unfilled orders for _insturment

        :param _instrument: which instrument
        :param _action: open or close
        :param _direction: buy or sell
        :return: number of unfilled order
        """
        num = 0
        for order in self.unfilled_order.values():
            if order.instrument == _instrument and order.action == _action and \
                            order.direction == _direction:
                num += order.quantity

        return num

    def getOpenBuyUnfilledOrder(self, _instrument: str) -> int:
        """
        number of unfilled order which is OPEN and BUY

        :param _instrument:
        :return:
        """
        return self.getUnfilledOrder(_instrument, ActionType.OPEN,
                                     DirectionType.BUY)

    def getOpenSellUnfilledOrder(self, _instrument: str) -> int:
        """
        number of unfilled order which is OPEN and SELL

        :param _instrument:
        :return:
        """
        return self.getUnfilledOrder(_instrument, ActionType.OPEN,
                                     DirectionType.SELL)

    def getCloseBuyUnfilledOrder(self, _instrument: str) -> int:
        """
        number of unfilled order which is CLOSE and BUY

        :param _instrument:
        :return:
        """
        return self.getUnfilledOrder(_instrument, ActionType.CLOSE,
                                     DirectionType.BUY)

    def getCloseSellUnfilledOrder(self, _instrument: str) -> int:
        """
        number of unfilled order which is CLOSE and SELL

        :param _instrument:
        :return:
        """
        return self.getUnfilledOrder(_instrument, ActionType.CLOSE,
                                     DirectionType.SELL)

    def dealSignalEvent(self, _signal_event: SignalEvent):
        """
        deal signal event to set inner state

        :param _signal_event:
        :return:
        """
        self.signal_record.append(_signal_event)

    def dealOrderEvent(self, _order_event: OrderEvent):
        """
        deal order event to set inner state

        :param _order_event: order event generated by global portfolio
        :return:
        """
        assert _order_event.index not in self.unfilled_order.keys()
        self.order_record.append(_order_event)
        self.unfilled_order[_order_event.index] = _order_event

    def dealFillEvent(self, _fill_event: FillEvent):
        """
        deal fill event to set inner state

        :param _fill_event:
        :return:
        """
        assert _fill_event.index in self.unfilled_order.keys()
        self.fill_record.append(_fill_event)
        del self.unfilled_order[_fill_event.index]
        if _fill_event.action == ActionType.OPEN:
            if _fill_event.direction == DirectionType.BUY:
                self.incPosition(_fill_event.instrument, SignalType.LONG,
                                 _fill_event.quantity)
            elif _fill_event.direction == DirectionType.SELL:
                self.incPosition(_fill_event.instrument,
                                 SignalType.SHORT, _fill_event.quantity)
            else:
                raise Exception('unknown direction')
        elif _fill_event.action == ActionType.CLOSE:
            if _fill_event.direction == DirectionType.BUY:
                self.decPosition(_fill_event.instrument,
                                 SignalType.SHORT, _fill_event.quantity)
            elif _fill_event.direction == DirectionType.SELL:
                self.decPosition(_fill_event.instrument, SignalType.LONG,
                                 _fill_event.quantity)
            else:
                raise Exception('unknown direction')
        else:
            raise Exception('unknown action')

    def storeRecords(self, _name: str, _coll: Collection):
        """
        store records into mongodb

        :param _name:
        :param _coll:
        :return:
        """
        for d in self.signal_record + \
                self.order_record + \
                self.fill_record:
            d = d.toDict()
            d['strategy_name'] = _name
            _coll.insert_one(d)

    def __repr__(self) -> str:
        def action2str(_action: int) -> str:
            if _action == ActionType.OPEN:
                return 'open'
            elif _action == ActionType.CLOSE:
                return 'close'
            else:
                raise Exception()

        def direction2str(_direction: int) -> str:
            if _direction == DirectionType.BUY:
                return 'buy'
            elif _direction == DirectionType.SELL:
                return 'sell'
            else:
                raise Exception()

        ret = '@@@ POSITION @@@\n'

        table = []
        for k, v in self.position.items():
            table.append(
                [k, v[SignalType.LONG], v[SignalType.SHORT]])
        ret += tabulate.tabulate(table, ['instrument', 'LONG', 'SHORT'])

        ret += '\n@@@ ORDER @@@\n'

        table = []
        for k, v in self.unfilled_order.items():
            table.append([
                k, v.instrument, action2str(v.action),
                direction2str(v.direction), v.quantity
            ])
        ret += tabulate.tabulate(
            table, ['index', 'instrument', 'ACTION', 'DIRECTION', 'QUANTITY'])

        ret += '\n@@@ UNFILLED ORDER @@@\n'
        ret += str(sorted(self.unfilled_order.keys()))

        ret += '\n@@@ RECORD @@@\n'
        ret += ' - Signal: ' + str(len(self.signal_record)) + '\n'
        ret += ' - Order: ' + str(len(self.order_record)) + '\n'
        ret += ' - Fill: ' + str(len(self.fill_record)) + '\n'

        return ret


class PortfolioAbstract:
    def __init__(self):
        # redirect to types
        self.order_index: int = 0  # cur unused order index
        self.engine: ParadoxTrading.Engine.EngineAbstract = None

        self.order_strategy_dict: typing.Dict[int, str] = {}
        self.strategy_portfolio_dict: typing.Dict[str,
                                                  PortfolioPerStrategy] = {}
        self.global_portfolio: PortfolioPerStrategy = PortfolioPerStrategy()

    def addStrategy(self, _strategy: StrategyAbstract):
        assert _strategy.name not in self.strategy_portfolio_dict.keys()
        self.strategy_portfolio_dict[_strategy.name] = PortfolioPerStrategy()

    def _setEngine(self,
                   _engine: 'ParadoxTrading.Engine.EngineAbstract'):
        """
        PROTECTED !!!

        :param _engine: ref to engine
        :return:
        """
        self.engine = _engine

    def incOrderIndex(self) -> int:
        """
        return cur index and inc order index

        :return: cur unused order index
        """
        tmp = self.order_index
        self.order_index += 1
        return tmp

    def addEvent(self, _order_event: OrderEvent, _strategy: str):
        """
        add event into engine's engine

        :param _order_event: order event object to be added
        :param _strategy:
        :return:
        """

        # check if it is valid
        assert _order_event.order_type is not None
        assert _order_event.action is not None
        assert _order_event.direction is not None
        assert _order_event.quantity > 0
        if _order_event.order_type == OrderType.LIMIT:
            assert _order_event.price is not None

        # map index to strategy
        self.order_strategy_dict[_order_event.index] = _strategy
        # add it into event queue
        self.engine.addEvent(_order_event)

    def storeRecords(
            self,
            _backtest_key: str,
            _mongo_host: str = 'localhost',
            _mongo_database: str = 'FutureBacktest', ):
        """
        store all strategies' records into mongodb

        :param _backtest_key:
        :param _mongo_host:
        :param _mongo_database:
        :return:
        """
        client = MongoClient(host=_mongo_host)
        db = client[_mongo_database]
        # clear old backtest records
        if _backtest_key in db.collection_names():
            db.drop_collection(_backtest_key)

        coll = db[_backtest_key]
        coll.create_index([
            ('strategy_name', pymongo.ASCENDING),
            ('type', pymongo.ASCENDING),
            ('tradingday', pymongo.ASCENDING),
            ('datetime', pymongo.ASCENDING),
        ])
        for k, v in self.strategy_portfolio_dict.items():
            v.storeRecords(k, coll)

        client.close()

    def dealSignal(self, _event: SignalEvent):
        """
        deal signal event from stategy

        :param _event: signal event to deal
        :return:
        """
        raise NotImplementedError('dealSignal not implemented')

    def dealFill(self, _event: FillEvent):
        """
        deal fill event from execute

        :param _event: fill event to deal
        :return:
        """
        raise NotImplementedError('dealFill not implemented')

    def getPortfolioByStrategy(self,
                               _strategy_name: str) -> PortfolioPerStrategy:
        """
        get the individual portfolio manager of strategy

        :param _strategy_name: key
        :return:
        """
        return self.strategy_portfolio_dict[_strategy_name]

    def getPortfolioByIndex(self, _index: int) -> PortfolioPerStrategy:
        return self.getPortfolioByStrategy(self.order_strategy_dict[_index])


class SimpleTickPortfolio(PortfolioAbstract):
    def __init__(self):
        super().__init__()

    def dealSignal(self, _event: SignalEvent):
        assert self.engine is not None

        portfolio = self.getPortfolioByStrategy(_event.strategy_name)

        # create order event
        order_event = OrderEvent(
            _index=self.incOrderIndex(),
            _instrument=_event.instrument,
            _tradingday=self.engine.getTradingDay(),
            _datetime=self.engine.getCurDatetime(),
            _order_type=OrderType.MARKET, )
        if _event.signal_type == SignalType.LONG:
            # whether there is short position to close
            if portfolio.getShortPosition(_event.instrument) - \
                    portfolio.getCloseBuyUnfilledOrder(_event.instrument) > 0:
                order_event.action = ActionType.CLOSE
            else:
                order_event.action = ActionType.OPEN

            # buy because of long
            order_event.direction = DirectionType.BUY
            order_event.quantity = 1
        elif _event.signal_type == SignalType.SHORT:
            # whether there is long position to close
            if portfolio.getLongPosition(_event.instrument) - \
                    portfolio.getCloseSellUnfilledOrder(_event.instrument) > 0:
                order_event.action = ActionType.CLOSE
            else:
                order_event.action = ActionType.OPEN

            # sell because of short
            order_event.direction = DirectionType.SELL
            order_event.quantity = 1
        else:
            raise Exception('unknown signal')

        portfolio.dealSignalEvent(_event)
        portfolio.dealOrderEvent(order_event)

        self.addEvent(order_event, _event.strategy_name)

    def dealFill(self, _event: FillEvent):
        self.getPortfolioByIndex(_event.index).dealFillEvent(_event)


class SimpleBarPortfolio(PortfolioAbstract):
    def __init__(self):
        super().__init__()

        self.price_index = 'closeprice'

    def setPriceIndex(self, _index: str):
        self.price_index = _index

    def dealSignal(self, _event: SignalEvent):
        portfolio = self.getPortfolioByStrategy(_event.strategy_name)

        order_event = OrderEvent(
            _index=self.incOrderIndex(),
            _instrument=_event.instrument,
            _tradingday=self.engine.getTradingDay(),
            _datetime=self.engine.getCurDatetime(),
            _order_type=OrderType.LIMIT,
        )
        if _event.signal_type == SignalType.LONG:
            if portfolio.getShortPosition(_event.instrument) - \
                    portfolio.getCloseSellUnfilledOrder(_event.instrument) > 0:
                order_event.action = ActionType.CLOSE
            else:
                order_event.action = ActionType.OPEN
            order_event.direction = DirectionType.BUY
        elif _event.signal_type == SignalType.SHORT:
            if portfolio.getShortPosition(_event.instrument) - \
                    portfolio.getCloseBuyUnfilledOrder(_event.instrument) > 0:
                order_event.action = ActionType.CLOSE
            else:
                order_event.action = ActionType.OPEN
            order_event.direction = DirectionType.SELL
        else:
            raise Exception('unknown signal')

        data = self.engine.getInstrumentData(_event.instrument)
        order_event.price = data.getColumn(self.price_index)[-1]

        portfolio.dealSignalEvent(_event)
        portfolio.dealOrderEvent(order_event)

        self.addEvent(order_event, _event.strategy_name)

    def dealFill(self, _event: FillEvent):
        self.getPortfolioByIndex(_event.index).dealFillEvent(_event)