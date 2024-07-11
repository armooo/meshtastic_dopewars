import asyncio
from dataclasses import dataclass, field


@dataclass
class Drug:
    name: str
    min: int
    max: int


@dataclass
class Gun:
    name: str
    price: int
    space: int
    damage: int


@dataclass
class OldPayload:
    code: str
    from_: str = ''
    to: str = ''
    ai: str = 'A'
    data: str = ''


@dataclass
class PlayerState:
    cash: int = 0
    debt: int = 0
    bank: int = 0
    bank: int = 0
    health: int = 0
    coatsize: int = 0
    locn: int = 0
    turn:  str = ''
    date: str = ''
    guns: list[int] = field(default_factory=list)
    drugs: list[int] = field(default_factory=list)
    drugs_value: list[int] = field(default_factory=list)
    bitches: int = 0


@dataclass
class Payload:
    code: str
    id: str = ''
    ai: str = 'A'
    data: str = ''


class Client:
    ABILITIES = '1110011'
    EVENTS = set([
        'A',
        'E',
        'F',
        'G',
        'H',
        'K',
        'L',
        'M',
        'N',
        'O',
        'm',
        'J',
        'S',
        'Q',
    ])

    def __init__(self, reader, writer):
        self._reader = reader
        self._writer = writer
        self.locations = {}
        self.guns = {}
        self.drug_prices = []
        self.drugs = {}
        self.users = {}
        self.last_player_state = PlayerState()
        self.player_state = PlayerState()

    async def old_send(self, payload):
        self._writer.write(f'{payload.from_}^{payload.to}^{payload.ai}{payload.code}{payload.data}\n'.encode('utf-8'))
        await self._writer.drain()

    async def old_read(self) -> OldPayload:
        line = await self._reader.readline()
        from_, to, line = line[:-1].decode('utf-8').split('^')
        ai = line[0]
        code = line[1]
        data = line[2:]
        return OldPayload(from_=from_, to=to, ai=ai, code=code, data=data)

    async def send(self, payload):
        self._writer.write(f'{payload.id}^{payload.ai}{payload.code}{payload.data}\n'.encode('utf-8'))
        await self._writer.drain()

    async def read(self) -> Payload:
        line = await self._reader.readline()
        id, line = line[:-1].decode('utf-8').split('^', 1)
        ai = line[0]
        code = line[1]
        data = line[2:]
        p = Payload(id=id, ai=ai, code=code, data=data)
        return p

    @staticmethod
    async def connect(host, port, name) -> 'Client':
        reader, writer = await asyncio.open_connection(host, port)
        client = Client(reader, writer)
        await client.old_send(OldPayload(code='r', data=Client.ABILITIES))
        await client.old_send(OldPayload(code='c', data=name))
        while True:
            old_packet = await client.old_read()
            if old_packet.code == 'r':
                for c, s in zip(Client.ABILITIES, old_packet.data):
                    if c == '1' and s != '1':
                        raise ValueError('I only know one set of rules')
                break
        return client


    def h_users(self, payload):
        name, id = payload.data.split('^')
        self.users[id] = name

    def h_data(self, payload):
        index, data = payload.data.split('^', 1)
        index = int(index)
        code = data[0]
        data = data[1:]
        if code == 'A':
            (location, *extra) = data.split('^')
            self.locations[index] = location
        elif code == 'B':
            (name, min, max, *extra) = data.split('^')
            self.drugs[index] = Drug(name, int(min), int(max))
        elif code == 'C':
            (name, price, space, damage, *extra) = data.split('^')
            self.guns[index] = Gun(name, int(price), int(space), int(damage))

    def h_join(self, payload):
        name, id = payload.split('^')
        self.users[id] = name

    def h_leave(self, payload):
        del self.users[payload.id]

    def h_rename(self, payload):
        self.users[payload.id] = payload.data

    def h_drug_prices(self, payload):
        self.drug_prices = payload.data.split('^')

    def h_update(self, payload):
        if payload.id != '':
            return
        fields = payload.data.split('^')

        cash = int(fields.pop(0))
        debt = int(fields.pop(0) or 0)
        bank = int(fields.pop(0) or 0)
        health = int(fields.pop(0))
        coatsize = int(fields.pop(0))

        locn = int(fields.pop(0))
        flags = fields.pop(0)
        turn = int(fields.pop(0))
        day = int(fields.pop(0))
        month = int(fields.pop(0))
        year = int(fields.pop(0))


        guns = [int(i) for i in fields[:len(self.guns)]]
        del fields[:len(self.guns)]

        drugs = [int(i) for i in fields[:len(self.drugs)]]
        del fields[:len(self.drugs)]

        drugs_value = [int(i or 0) for i in fields[:len(self.drugs)]]
        del fields[:len(self.drugs)]

        bitches = fields.pop(0)

        self.last_player_state = self.player_state
        self.player_state = PlayerState(
            cash=cash,
            debt=debt,
            bank=bank,
            health=health,
            coatsize=coatsize,
            locn=locn,
            turn=turn,
            date=f'{year}-{month}-{day}',
            guns=guns,
            drugs=drugs,
            drugs_value=drugs_value,
            bitches=bitches,
        )

    HANDLERS = {
        'B': h_users,
        'l': h_data,
        'G': h_join,
        'H': h_leave,
        'b': h_rename,
        'K': h_drug_prices,
        'J': h_update,
    }

    async def next_event(self) -> Payload:
        while True:
            payload = await self.read()
            if payload.code in self.HANDLERS:
                self.HANDLERS[payload.code](self, payload)

            if payload.code in self.EVENTS:
                return payload


