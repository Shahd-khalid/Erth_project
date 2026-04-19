import json
from channels.generic.websocket import AsyncWebsocketConsumer

class CallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_link = self.scope['url_route']['kwargs']['session_link']
        self.room_group_name = f'session_{self.session_link}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')

        if message_type == 'incoming_call':
            caller = text_data_json.get('caller', 'القاضي')
            room_name = text_data_json.get('room_name')
            
            # Send message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'call_signal',
                    'signal': 'incoming_call',
                    'caller': caller,
                    'room_name': room_name
                }
            )
            
        elif message_type == 'end_call':
            # Send end call signal to everyone in the room
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'call_signal',
                    'signal': 'end_call'
                }
            )

    # Receive message from room group
    async def call_signal(self, event):
        signal = event['signal']
        
        message_data = {'type': signal}
        if signal == 'incoming_call':
            message_data['caller'] = event.get('caller')
            message_data['room_name'] = event.get('room_name')

        # Send message to WebSocket
        await self.send(text_data=json.dumps(message_data))
