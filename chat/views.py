
from rest_framework import generics, permissions
from .models import ChatRoom
from .serializers import ChatRoomSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model

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

