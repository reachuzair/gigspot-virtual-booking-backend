from django.urls import path
from .views import add_to_cart, list_cart_items, remove_from_cart

urlpatterns = [
    path('add/', add_to_cart, name='add_to_cart'),
    path('list/', list_cart_items, name='list_cart_items'),
    path('remove/', remove_from_cart, name='remove_from_cart'),
]
