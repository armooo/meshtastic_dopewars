import asyncio
from client import Payload


class BaseState:
    def __init__(self, game):
        self.game = game
        self._high_score_count = 0

    def print_state(self):
        state = self.game.client.player_state
        self.game.add_line('=Player')
        location_name = self.game.client.locations[state.locn]
        self.game.add_line(f'{state.date} -- {location_name}')
        self.game.add_line(f'Cash: ${state.cash} Debt: ${state.debt} Bank: ${state.bank}')
        self.game.add_line(f'Health: {state.health} Coat: {state.coatsize} Turn: {state.turn} Bitches: {state.bitches}')
        guns = []
        for gid, gcnt in enumerate(state.guns):
            gun = self.game.client.guns[gid]
            if gcnt:
                guns.append(f'{gun.name}: {gcnt}')
        self.game.add_line(' '.join(guns))
        drugs = []
        for did, (dcnt, dvalue) in enumerate(zip(state.drugs, state.drugs_value)):
            drug = self.game.client.drugs[did]
            if dcnt:
                self.game.add_line(f'{drug.name:10} {dcnt:2} ${dvalue}')

    async def h_message(self, event):
        for line in event.data.split('^'):
            self.game.add_line(line)

    async def game_event(self, event):
        if event.code == 'A':
            await self.h_message(event)
        elif event.code == 'J':
            self.print_state()
        elif event.code == 'G':
            name, id = event.data.split('^')
            self.game.add_line(f'{name} joined.')
        elif event.code == 'H':
            self.game.add_line(f'{event.data} left.')
        elif event.code == 'R':
            self._high_score_count = 0
        elif event.code == 'Q':
            if self._high_score_count > 9:
                return
            self._high_score_count += 1
            rank, rest = event.data.split('^', 1)
            rank = int(rank) + 1
            bold = rest[0]
            msg = rest[1:].replace('<', '').replace('>', '')
            print(msg)
            (score, date, name, *extra) = msg.split()
            self.game.add_line(f'#{rank} {score} {name}')

    def parse_input(self, user_inputin, options):
        parts = user_inputin.strip().split(None, 1)
        if not parts:
            return None, None
        option = parts[0].upper()
        if len(parts) == 2:
            arg = parts[1]
        else:
            arg = None
        if arg and not arg.strip():
            arg = None
        if not options or option in options:
            return option, arg
        return None, None

    async def user_input(self, user_input):
        if user_input.strip().upper() == 'QUIT':
            await self.game.client.send(Payload(code='g'))
            return True

    def print_locations(self):
        self.game.add_line('= Locations')
        for index, location in self.game.client.locations.items():
            self.game.add_line(f'{index:2} {location}')

    async def jet(self, option, arg):
        try:
            arg = int(arg)
        except (ValueError, TypeError):
            self.print_locations()
            self.game.add_line(self.JET_HELP)
            return

        if arg not in self.game.client.locations:
            self.game.add_line('You can\'t get there from here.')
            self.print_locations()
            self.game.add_line(self.JET_HELP)
            return

        await self.game.client.send(Payload(
            code='V',
            data=arg,
        ))


class StreetState(BaseState):
    INPUT_OPTIONS = '(B)uy, (S)ell, (J)et> '
    BUY_SELL_HELP = '{option} <drug index> <count>'
    JET_HELP = 'J <location index>'

    def print_drugs(self):
        self.game.add_line('=Drugs')
        for i, price in enumerate(self.game.client.drug_prices):
            if price == '':
                continue
            drug = self.game.client.drugs[i]
            self.game.add_line(f'{i:2}: {drug.name:8} ${price}')

    async def game_event(self, event):
        await BaseState.game_event(self, event)
        if event.code == 'K':
            self.print_drugs()
        if event.code in ('K', 'J'):
            self.game.add_line(self.INPUT_OPTIONS)

    async def buy_sell(self, option, arg):
        if not arg:
            self.game.add_line(self.BUY_SELL_HELP.format(**locals()))
            return
        try:
            index, cnt = arg.split(None, 1)
            index = int(index)
            cnt = int(cnt)
            if option == 'S':
                cnt = 0 - cnt
        except (ValueError, TypeError):
            self.game.add_line(self.BUY_SELL_HELP.format(**locals()))
            return
        if index not in self.game.client.drugs or not self.game.client.drug_prices[index]:
            self.game.add_line('I can\'t find that drug.')
            return
        await self.game.client.send(Payload(
            code='T',
            data=f'drug^{index}^{cnt}',
        ))

    async def user_input(self, user_input):
        if await BaseState.user_input(self, user_input):
            return
        option, arg =  self.parse_input(user_input, ['B', 'S', 'J'])
        if option is None:
            self.game.add_line('Invalid input')
            self.game.add_line(self.INPUT_OPTIONS)
        elif option in ('B', 'S'):
            await self.buy_sell(option, arg)
        elif option == 'J':
            await self.jet(option, arg)


class QuestionState(BaseState):
    def __init__(self, game):
        BaseState.__init__(self, game)
        self.keys = []
        self.question = ''

    async def game_event(self, event):
        await BaseState.game_event(self, event)
        if event.code != 'O':
            return

        keys, question = event.data.split('^', 1)
        self.keys = [c for c in keys]
        self.question = question.replace('^', '\n')

        self.game.add_line(self.question)
        self.game.add_line(f'{"/".join(self.keys)} >')

    async def user_input(self, user_input):
        if await BaseState.user_input(self, user_input):
            return
        option, _ =  self.parse_input(user_input, self.keys)
        if option is None:
            self.game.add_line('Invalid input')
            self.game.add_line(f'{"/".join(self.keys)} >')
            return
        self.game.switch_to_street_state()
        await self.game.client.send(Payload(
            code='X',
            data=option,
        ))


class GunShopState(BaseState):
    PROMPT = '(B)uy, (S)ell, e(X)it >'
    BUY_SELL_HELP = '{option} <gun index> <count>'

    def __init__(self, game):
        BaseState.__init__(self, game)

    async def game_event(self, event):
        await BaseState.game_event(self, event)
        if event.code == 'L':
            self.game.add_line('=Gun Shop')
            for index, gun in self.game.client.guns.items():
                self.game.add_line(f'{index:2} {gun.name:25} ${gun.price:4} space: {gun.space} damage: {gun.damage}')
        if event.code in ('L', 'J'):
            self.game.add_line(self.PROMPT)

    async def buy_sell(self, option, arg):
        if not arg:
            self.game.add_line(self.BUY_SELL_HELP.format(**locals()))
            self.game.add_line(self.PROMPT)
            return
        try:
            index, cnt = arg.split(None, 1)
            index = int(index)
            cnt = int(cnt)
            if option == 'S':
                cnt = 0 - cnt
        except (ValueError, TypeError):
            self.game.add_line(self.BUY_SELL_HELP.format(**locals()))
            self.game.add_line(self.PROMPT)
            return
        if index not in self.game.client.guns:
            self.game.add_line('I can\'t find that gun.')
            self.game.add_line(self.PROMPT)
            return
        await self.game.client.send(Payload(
            code='T',
            data=f'gun^{index}^{cnt}',
        ))

    async def user_input(self, user_input):
        if await BaseState.user_input(self, user_input):
            return
        option, arg = self.parse_input(user_input, ['B', 'S', 'X'])
        if option in ('B', 'S'):
            await self.buy_sell(option, arg)
        elif option == 'X':
            self.game.switch_to_street_state()
            await self.game.client.send(Payload(code='U'))
        else:
            self.game.add_line(self.PROMPT)


class LoanSharkState(BaseState):
    PROMPT = '(P)ay, e(X)it >'
    PAY_HELP = 'P <amount>'

    async def game_event(self, event):
        await BaseState.game_event(self, event)
        if event.code == 'M':
            state = self.game.client.player_state
            self.game.add_line('=Loan Shark')
            self.game.add_line(f'Debt: ${state.debt} Cash: ${state.cash}')
        if event.code in ('M', 'J'):
            self.game.add_line(self.PROMPT)

    async def pay(self, option, arg):
        try:
            arg = int(arg)
        except (ValueError, TypeError):
            self.game.add_line(self.PAY_HELP.format(**locals()))
            self.game.add_line(self.PROMPT)
            return
        await self.game.client.send(Payload(
            code='W',
            data=arg,
        ))

    async def user_input(self, user_input):
        option, arg = self.parse_input(user_input, ['P', 'X'])
        if option == 'P':
            await self.pay(option, arg)
        elif option == 'X':
            self.game.switch_to_street_state()
            await self.game.client.send(Payload(code='U'))
        else:
            self.game.add_line(self.PROMPT)


class BankState(BaseState):
    PROMPT = '(D)eposit, (W)ithdraw, e(X)it >'
    DEPOSIT_HELP = '{option} <amount>'

    async def game_event(self, event):
        await BaseState.game_event(self, event)
        if event.code == 'N':
            state = self.game.client.player_state
            self.game.add_line('=Bank')
            self.game.add_line(f'Balance: ${state.bank} Cash: ${state.cash}')
        if event.code in ('N', 'J'):
            self.game.add_line(self.PROMPT)

    async def deposit(self, option, arg):
        try:
            arg = int(arg)
        except (ValueError, TypeError):
            self.game.add_line(self.DEPOSIT_HELP.format(**locals()))
            self.game.add_line(self.PROMPT)
            return
        if option == 'W':
            arg = 0 - arg
        await self.game.client.send(Payload(
            code='Y',
            data=arg,
        ))

    async def user_input(self, user_input):
        if await BaseState.user_input(self, user_input):
            return
        option, arg = self.parse_input(user_input, ['D', 'W', 'X'])
        if option in ('D', 'W'):
            await self.deposit(option, arg)
        elif option == 'X':
            self.game.switch_to_street_state()
            await self.game.client.send(Payload(code='U'))
        else:
            self.game.add_line(self.PROMPT)


class FightState(BaseState):
    def __init__(self, game):
        BaseState.__init__(self, game)
        self.prompt = ''
        self.options = []
        state = self.game.client.player_state
        self.player_line = f'Player -- health: {state.health} bitches: {state.bitches}'
        self.other_line = ''

    async def game_event(self, event):
        if event.code != 'J':
            await BaseState.game_event(self, event)
        if event.code != 'm':
            return
        # "attack"^"defend"^<health>^<bitches>^"bitchname"^<killed>^<armpct>^(fightpoint)(runhere)(loot)(canfire)^"text

        attack, defend, health, bitches, bitchname, killed, armpct, flags, msg = event.data.split('^')
        fightpoint = flags[0]
        runhere = int(flags[1])
        loot = int(flags[2])
        canfire = int(flags[3])

        options = ['S']
        prompt = ['(S)tand']
        if runhere:
            options.append('R')
            prompt.append('(R)un')
        else:
            options.append('J')
            prompt.append('(J)et')
        if canfire:
            options.append('F')
            prompt.append('(F)ire')

        self.options = options
        self.prompt = ', '.join(prompt) + '> '

        if not defend:
            self.player_line = f'Player -- health: {health} {bitchname}: {bitches}'
        else:
            self.other_line = f'{defend} -- health: {health} {bitchname}: {bitches}'


        self.game.add_line('=Fight')
        self.game.add_line(self.player_line)
        self.game.add_line(self.other_line)
        self.game.add_line(msg)

        if attack:
            self.game.add_line(self.prompt)

        if fightpoint == 'D':
            self.game.switch_to_street_state()

    async def user_input(self, user_input):
        if await BaseState.user_input(self, user_input):
            return
        option, arg = self.parse_input(user_input, self.options)
        if option is None:
            self.game.add_line('Invalid input')
            self.game.add_line(self.prompt)
        elif option in ('F', 'S', 'R'):
            await self.game.client.send(Payload(code='n', data=option))
        elif option == 'J':
            await self.jet(option, arg)
        else:
            self.game.add_line(self.prompt)


class Game:
    def __init__(self, client):
        self.client = client
        self._lines = []
        self._stop = False

    def add_line(self, line):
        self._lines.append(line)

    async def flush_lines(self):
        pass

    def switch_to_street_state(self):
        self._mode = StreetState(self)

    async def game_loop(self):
        self.switch_to_street_state()
        while not self._stop:
            event = await self.client.next_event()
            if event.code == 'I':
                self._mode = StreetState(self)
            elif event.code == 'O':
                self._mode = QuestionState(self)
            elif event.code == 'L':
                self._mode = GunShopState(self)
            elif event.code == 'M':
                self._mode = LoanSharkState(self)
            elif event.code == 'N':
                self._mode = BankState(self)
            elif event.code == 'm':
                if not isinstance(self._mode, FightState):
                    self._mode = FightState(self)
            elif event.code == 'S':
                await self.flush_lines()
                if event.data == 'end':
                    self._stop = True
            await self._mode.game_event(event)

            if event.code not in ('Q'):
                await self.flush_lines()

    async def user_input(self, user_input):
        await self._mode.user_input(user_input)
        await self.flush_lines()


class ConsoleGame(Game):
    async def flush_lines(self):
        for line in self._lines:
            print(line)
        del self._lines[:]

    async def read_user_input(self):
        while not self._stop:
            user_input = await asyncio.to_thread(input)
            #user_input = await loop.run_in_executor(None, input)
            await self.user_input(user_input)
            await self.flush_lines()

    async def game_loop(self):
        async with asyncio.TaskGroup() as tg:
            tg.create_task(Game.game_loop(self))
            self._user_input_task = tg.create_task(self.read_user_input())


class MeshGame(Game):
    def __init__(self, client, send_pm):
        Game.__init__(self, client)
        self._send_pm = send_pm
        self.user_input_queue = asyncio.Queue()


    async def read_from_queue(self):
        while not self._stop:
            try:
                async with asyncio.timeout(5):
                    user_input = await self.user_input_queue.get()
            except TimeoutError:
                pass
            else:
                await self.user_input(user_input)

    async def game_loop(self):
        async with asyncio.TaskGroup() as tg:
            tg.create_task(Game.game_loop(self))
            tg.create_task(self.read_from_queue())

    async def flush_lines(self):
        msg = ""
        for line in self._lines:
            if 1 + len(line) + len(msg) > 230:
                await self._send_pm(msg)
                msg = ""
            msg += "\n"
            msg += line
        if msg.strip():
            await self._send_pm(msg)
        del self._lines[:]



async def test():
    from client import Client
    c = await Client.connect('localhost', 7902, 'armooo')
    g = ConsoleGame(c)
    await g.game_loop()

if __name__ == '__main__':
    asyncio.run(test())
