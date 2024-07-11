import sys
import asyncio
import functools
import random
import logging
import traceback
import argparse

from aiomeshtastic import get_client

from meshtastic.mesh_pb2 import ToRadio
from meshtastic.portnums_pb2 import PortNum

from client import Client
from game import MeshGame


class DMManager:
    def __init__(self, client):
        self.client = client
        self.queue = []
        self.event = asyncio.Event()
        self.inflight_packet_ids = set()

    async def send_dm(self, node_id, hops, msg):
        print(node_id, msg)
        self.queue.append((node_id, hops, msg))
        self.event.set()

    async def run(self):
        while True:
            await self.event.wait()
            try:
                if len(self.inflight_packet_ids) != 0:
                    continue
                (node_id, hops, msg) = self.queue.pop(0)
            except IndexError:
                continue
            finally:
                self.event.clear()

            packet_id = random.getrandbits(32)
            tr = ToRadio()
            tr.packet.decoded.portnum = PortNum.TEXT_MESSAGE_APP
            tr.packet.decoded.payload = msg.encode('utf-8')
            tr.packet.id = packet_id
            tr.packet.to = node_id
            tr.packet.want_ack = True
            tr.packet.hop_limit = hops
            tr.packet.hop_start = hops
            self.inflight_packet_ids.add(packet_id)
            await self.client.write(tr)

    def process_ack_nack(self, packet):
        if packet.decoded.request_id in self.inflight_packet_ids and packet.decoded.portnum == PortNum.ROUTING_APP:
            self.inflight_packet_ids.remove(packet.decoded.request_id)
            self.event.set()


class GameServer:

    INTRO = 'Welcome dopewars. Send START to begin a game and QUIT at anytime to stop.'


    def __init__(self, server, port):
        self.server = server
        self.port = port
        self.games = {}
        self.game_loops = set()

    def game_done(self, node_id, task):
        del self.games[node_id]
        exception = task.exception()
        if exception:
            traceback.print_exception(exception)
        self.game_loops.discard(task)

    async def process_messages(self, client, my_node_num, dm_manager):
            async for fr in client.read():
                if fr.HasField('packet') and fr.packet.to == my_node_num and fr.packet.decoded.portnum == PortNum.TEXT_MESSAGE_APP:
                    msg = fr.packet.decoded.payload.decode('utf-8')
                    node_id = getattr(fr.packet, 'from')
                    if node_id in self.games:
                        print('sending to game', node_id, msg)
                        self.games[node_id].user_input_queue.put_nowait(msg)
                    elif msg.strip().upper() == 'START' and node_id not in self.games:
                        print('starting game for', node_id)
                        game = MeshGame(
                                await Client.connect(self.server, self.port,  f'!{hex(node_id)[2:]}'),
                                functools.partial(dm_manager.send_dm, node_id, fr.packet.hop_start),
                        )
                        game_loop_task = asyncio.create_task(game.game_loop())
                        self.game_loops.add(game_loop_task)
                        game_loop_task.add_done_callback(functools.partial(self.game_done, node_id))
                        self.games[node_id] = game
                    else:
                        await dm_manager.send_dm(node_id, fr.packet.hop_start, self.INTRO)
                if fr.HasField('packet'):
                    dm_manager.process_ack_nack(fr.packet)

    async def run(self, connect_string):
        while True:
            try:
                async with get_client(connect_string) as client:
                    print(f'Connected to {connect_string}')
                    print('Loading device config')
                    config = await client.get_config()
                    for fr in config:
                        if fr.HasField('my_info'):
                            my_node_num = fr.my_info.my_node_num
                    print(f'Local node id: {my_node_num}')

                    dm_manager = DMManager(client)
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(dm_manager.run())
                        tg.create_task(self.process_messages(client, my_node_num, dm_manager))
            except ConnectionResetError:
                await asyncio.sleep(5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser('game_server')
    parser.add_argument('--device-connect-string', default='serial:///dev/ttyACM0')
    parser.add_argument('--dopewars-server', default='home.armooo.net')
    args = parser.parse_args()

    if ':' in args.dopewars_server:
        host, port = args.dopewars_server.split(':')
    else:
        host = args.dopewars_server
        port = 7902

    game_server = GameServer(host, port)
    asyncio.run(game_server.run(args.device_connect_string))
