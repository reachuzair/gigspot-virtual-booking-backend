
from rest_framework import generics, permissions
from .models import ChatRoom, Message
from .serializers import ChatRoomSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator


User = get_user_model()

class ChatRoomCreateView(generics.CreateAPIView):
    queryset = ChatRoom.objects.all()
    serializer_class = ChatRoomSerializer
    permission_classes = [permissions.IsAuthenticated]

class CreateChatRoomView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        room_type = request.data.get('room_type')  # "private" or "group"
        user_ids = request.data.get('user_ids', [])
        room_name = request.data.get('name', '')

        if room_type not in ['private', 'group']:
            return Response({'detail': 'Invalid room_type.'}, status=400)

        if room_type == 'private':
            if len(user_ids) != 1:
                return Response({'detail': 'Private chat must include exactly one other user.'}, status=400)

            other_user_id = user_ids[0]
            other_user = User.objects.filter(id=other_user_id).first()
            if not other_user:
                return Response({'detail': 'User not found.'}, status=404)

            # Check if private room already exists between the two users
            existing_rooms = ChatRoom.objects.filter(
                room_type='private',
                participants=request.user
            ).filter(
                participants=other_user
            ).distinct()

            if existing_rooms.exists():
                room = existing_rooms.first()
                return Response({'room_id': room.id, 'detail': 'Private chat already exists.'}, status=200)

            # Create new private room
            room = ChatRoom.objects.create(room_type='private')
            room.participants.add(request.user, other_user)

        else:  # group
            if not user_ids:
                return Response({'detail': 'Group chat must include at least one user.'}, status=400)

            users = User.objects.filter(id__in=user_ids)
            room = ChatRoom.objects.create(room_type='group', name=room_name or 'Group Chat')
            room.participants.add(request.user, *users)

        return Response({
            'room_id': room.id,
            'room_type': room.room_type,
            'name': room.name,
            'participants': list(room.participants.values('id', 'name'))
        }, status=201)


class MessageListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, room_id):
        try:
            room = ChatRoom.objects.get(id=room_id)
        except ChatRoom.DoesNotExist:
            return Response({"detail": "Chat room not found."}, status=404)

        if request.user not in room.participants.all():
            return Response({"detail": "You are not a participant of this chat room."}, status=403)

        messages = Message.objects.filter(chat_room=room).order_by('-created_at')

        # Optional: pagination
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('page_size', 20))
        paginator = Paginator(messages, per_page)
        page_obj = paginator.get_page(page)

        serialized_messages = [{
            'id': msg.id,
            'sender_id': msg.sender.id,
            'sender_username': msg.sender.name,
            'receiver_id': msg.receiver.id if msg.receiver else None,
            'content': msg.content,
            'timestamp': msg.timestamp,
            'is_read': msg.is_read,
        } for msg in page_obj]

        return Response({
            "messages": serialized_messages,
            "total": paginator.count,
            "page": page,
            "pages": paginator.num_pages,
        })

class DeleteMessageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, message_id):
        try:
            message = Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            return Response({"detail": "Message not found."}, status=404)

        if message.sender != request.user:
            return Response({"detail": "You can only delete your own messages."}, status=403)

        message.delete()
        return Response({"detail": "Message deleted successfully."}, status=204)
