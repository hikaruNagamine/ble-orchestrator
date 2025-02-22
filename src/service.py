import asyncio
import json
from aiohttp import web
from .ble_controller import BLEController

class BLEService:
    def __init__(self):
        self.controller = BLEController()
        self.app = web.Application()
        self.app.router.add_post('/ble', self.handle_request)

    async def start(self):
        await self.controller.start()
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', 8080)
        await site.start()

    async def stop(self):
        await self.controller.stop()

    async def handle_request(self, request):
        try:
            data = await request.json()
            command = data.get('command')

            if command == 'get':
                timestamp = data.get('timestamp')
                result = await self.controller.get_scan_data(timestamp)
                return web.json_response({
                    'status': 'success',
                    'data': result
                })

            elif command == 'send':
                device = data.get('device', {})
                result = await self.controller.send_command(
                    device_address=device.get('address'),
                    command=device.get('command'),
                    parameters=device.get('parameters')
                )
                return web.json_response(result)

            else:
                return web.json_response({
                    'status': 'error',
                    'error': 'Invalid command'
                }, status=400)

        except Exception as e:
            return web.json_response({
                'status': 'error',
                'error': str(e)
            }, status=500) 