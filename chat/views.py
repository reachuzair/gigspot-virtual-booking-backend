
from rest_framework import generics, permissions
from .models import ChatRoom, Message, MessageReadStatus
from .serializers import ChatRoomSerializer, MessageSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.utils.timezone import now
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from django.core.cache import cache
from django.shortcuts import get_object_or_404


User = get_user_model()

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


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_messages(request, room_id):
    try:
        room = ChatRoom.objects.get(id=room_id)
    except ChatRoom.DoesNotExist:
        return Response({"detail": "Chat room not found."}, status=404)

    if request.user not in room.participants.all():
        return Response({"detail": "You are not a participant of this chat room."}, status=403)

    page = int(request.query_params.get('page', 1))
    per_page = int(request.query_params.get('page_size', 20))

    cache_key = f"messages_{request.user.id}_room_{room_id}_page_{page}_per_{per_page}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return Response({
            "count": cached_data['count'],
            "next": cached_data['next'],
            "previous": cached_data['previous'],
            "results": cached_data['results'],
        })

    messages = Message.objects.filter(chat_room=room).order_by('-created_at')
    paginator = PageNumberPagination()
    paginator.page_size = per_page
    result_page = paginator.paginate_queryset(messages, request)

    serializer = MessageSerializer(result_page, many=True)
    paginated_response = paginator.get_paginated_response(serializer.data)

    # Cache the entire response payload
    cache.set(cache_key, {
        "count": paginated_response.data['count'],
        "next": paginated_response.data['next'],
        "previous": paginated_response.data['previous'],
        "results": paginated_response.data['results'],
    }, timeout=60 * 5)

    return paginated_response


class DeleteMessageView(APIView):
    
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        message_ids = request.data.get("message_ids", [])

        if not isinstance(message_ids, list) or not all(isinstance(i, int) for i in message_ids):
            return Response({"detail": "message_ids must be a list of integers."}, status=400)

        # Get messages sent by the user
        user_messages = Message.objects.filter(id__in=message_ids, sender=request.user)

        if not user_messages.exists():
            return Response({"detail": "No messages found to delete or you don't own them."}, status=404)

        deleted_count = user_messages.count()
        user_messages.delete()

        return Response({"detail": f"{deleted_count} messages deleted successfully."}, status=204)


class InboxView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # Get all rooms the user participates in
        rooms = ChatRoom.objects.filter(participants=user).distinct()

        room_list = []

        for room in rooms:
            # Get last message
            last_message = (
                room.messages.order_by("-created_at").first()
            )

            # Count unread messages
            unread_count = MessageReadStatus.objects.filter(
                message__chat_room=room,
                user=user,
                is_read=False
            ).count()

            # For private room, find the other participant
            other_user = None
            if room.room_type == 'private':
                others = room.participants.exclude(id=user.id)
                other_user = others.first().name if others.exists() else None

            room_list.append({
                "room_id": room.id,
                "room_name": room.name if room.name else f"Chat {room.id}",
                "room_type": room.room_type,
                "other_user": other_user,
                "last_message": {
                    "id": last_message.id,
                    "text": last_message.content.get("text", "") if last_message else "",
                    "sender": last_message.sender.name if last_message else "",
                    "timestamp": last_message.timestamp if last_message else None,
                } if last_message else None,
                "unread_count": unread_count,
            })

        return Response(room_list, status=200)

class MarkMessagesAsReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        message_ids = request.data.get("message_ids", [])

        if not isinstance(message_ids, list) or not all(isinstance(i, int) for i in message_ids):
            return Response({"detail": "message_ids must be a list of integers."}, status=400)

        user = request.user
        updated = 0

        messages = Message.objects.filter(id__in=message_ids)

        for message in messages:
            # Group chat or private chat with receiver
            if message.chat_room.room_type == "group":
                # Only update per-user status for group messages
                obj, created = MessageReadStatus.objects.update_or_create(
                    message=message,
                    user=user,
                    defaults={"is_read": True, "read_at": now()}
                )
                updated += 1

            elif message.receiver == user:
                # Private chat: update both per-message and per-user read status
                if not message.is_read:
                    message.is_read = True
                    message.save(update_fields=["is_read"])

                obj, created = MessageReadStatus.objects.update_or_create(
                    message=message,
                    user=user,
                    defaults={"is_read": True, "read_at": now()}
                )
                updated += 1

        return Response({"detail": f"{updated} messages marked as read."}, status=200)

