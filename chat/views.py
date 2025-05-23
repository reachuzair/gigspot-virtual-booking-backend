# views.py
from rest_framework import generics, permissions
from .models import ChatRoom
from .serializers import ChatRoomSerializer

class ChatRoomCreateView(generics.CreateAPIView):
    queryset = ChatRoom.objects.all()
    serializer_class = ChatRoomSerializer
    permission_classes = [permissions.IsAuthenticated]
